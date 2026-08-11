"""The ``single_image`` GroupType: a Group that wraps exactly one image.

``Dataset``s collect whole Groups, so a dataset of individual images needs each
image wrapped in a ``single_image`` group (one image, role ``single_image``).
One such group exists per image and is reused across every dataset that image
belongs to, so the group set stays at most one-per-image.
"""

from django.db import transaction

from backend.dataroom.datasets.os_sync import sync_single_image_denorm
from backend.dataroom.models.dataset import Dataset, DatasetMembership
from backend.dataroom.models.group import Group, GroupType, GroupTypeRole, Membership, Role

SINGLE_IMAGE_TYPE = 'single_image'
SINGLE_IMAGE_ROLE = 'single_image'


class SingleImageGroupNameConflictError(Exception):
    """Some other group already has the name we need for an image's wrapper group.

    Each image is wrapped in a single_image group named after the image id, and group
    names are unique among active groups whatever their type. So if a group of another
    type already holds that name, the wrapper cannot be created. Adopting the existing
    group instead would put a wrong-typed group in the dataset, so we refuse.
    """

    def __init__(self, conflicts):
        """conflicts: an iterable of (image_id, group_type) pairs."""
        self.conflicts = sorted(conflicts)
        clashes = ', '.join(f"'{image_id}' (a '{group_type}' group)" for image_id, group_type in self.conflicts)
        super().__init__(
            f'Adding an image creates a group named after it, and these names are already taken '
            f'by groups of another type: {clashes}. Rename those groups, or add the images to '
            f'this dataset through groups of their own.'
        )


def ensure_single_image_type() -> GroupType:
    """Idempotently create the ``single_image`` GroupType and its ``single_image`` role."""
    role, _ = Role.objects.get_or_create(
        name=SINGLE_IMAGE_ROLE, defaults={'description': 'The single image in a group.'}
    )
    gt, _ = GroupType.objects.get_or_create(
        name=SINGLE_IMAGE_TYPE,
        defaults={'description': 'A group wrapping exactly one image (role: single_image).'},
    )
    GroupTypeRole.objects.get_or_create(group_type=gt, role=role, defaults={'is_required': True})
    return gt


def groups_for_images(image_ids: list[str]) -> dict[str, Group]:
    """Bulk get-or-create the single_image group for each image (name == image_id).

    Postgres only, in a handful of bulk queries instead of a get_or_create per image.
    Reuses existing active groups (never duplicates), bulk-creates the missing ones, and
    creates or revives one live ``(group, image, single_image)`` membership each (left
    ``os_synced=False`` for the caller's post-commit OS write). Returns {image_id: Group}.
    The ``single_image`` GroupType must already exist — it does whenever a single_image
    dataset does, since Dataset.type is a PROTECTed FK.
    """
    # Groups: reuse existing active ones, bulk-create the rest.
    active = dict(type_id=SINGLE_IMAGE_TYPE, deleted_at__isnull=True)
    groups = {g.name: g for g in Group.objects.filter(name__in=image_ids, **active)}
    missing = [image_id for image_id in image_ids if image_id not in groups]
    if missing:
        Group.objects.bulk_create(
            [Group(name=image_id, type_id=SINGLE_IMAGE_TYPE) for image_id in missing],
            ignore_conflicts=True,  # a concurrent add may have created the same group
        )
        groups = {g.name: g for g in Group.objects.filter(name__in=image_ids, **active)}
    # A row can still be missing for two reasons. Either an active group of ANOTHER type
    # already owns that name (names are globally unique among active groups, so our
    # bulk_create was silently skipped by ignore_conflicts) — reusing it would put a
    # wrong-typed group in a single_image dataset, so refuse. Or a concurrent
    # soft-delete/revive raced us, which the per-row fallback settles.
    still_missing = [image_id for image_id in image_ids if image_id not in groups]
    if still_missing:
        conflicts = list(
            Group.objects.filter(name__in=still_missing, deleted_at__isnull=True)
            .exclude(type_id=SINGLE_IMAGE_TYPE)
            .values_list('name', 'type_id')
        )
        if conflicts:
            raise SingleImageGroupNameConflictError(conflicts)
        for image_id in still_missing:
            # type_id is part of the lookup: never adopt a group of another type.
            groups[image_id], _ = Group.objects.get_or_create(
                name=image_id, type_id=SINGLE_IMAGE_TYPE, deleted_at__isnull=True
            )

    # Memberships: one live (group, image, single_image) row each — create missing, revive soft-deleted.
    group_ids = [groups[image_id].id for image_id in image_ids]
    existing = {m.group_id: m for m in Membership.objects.filter(group_id__in=group_ids, role=SINGLE_IMAGE_ROLE)}
    to_create, revive_pks = [], []
    for image_id in image_ids:
        group = groups[image_id]
        membership = existing.get(group.id)
        if membership is None:
            to_create.append(Membership(group=group, image_id=image_id, role=SINGLE_IMAGE_ROLE, os_synced=False))
        elif membership.deleted_at is not None:
            revive_pks.append(membership.pk)
    if to_create:
        Membership.objects.bulk_create(to_create, ignore_conflicts=True)
    if revive_pks:
        Membership.objects.filter(pk__in=revive_pks).update(deleted_at=None, os_synced=False)
    return groups


def add_images_to_dataset(dataset: Dataset, image_ids: list[str]) -> int:
    """Add images to a single_image dataset by wrapping each in its single_image group.

    All Postgres work (bulk group + membership creation, dataset membership) happens in one
    transaction; every OpenSearch write happens *after* it commits, batched into as few
    update_by_query calls as possible, so the PG transaction is never held open across a
    network call. Reuses existing single_image groups (never duplicates). Caller ensures
    the dataset is single_image and not frozen.

    The OpenSearch write is a bulk update addressed by _id and we wait for it, so the
    rows can honestly be marked os_synced: we saw it land. It used to be fire-and-forget,
    which meant nobody could claim the write succeeded and the reconciler had to re-write
    every doc to confirm it.

    Only the images whose Postgres rows actually changed are written. This call is
    idempotent, so re-adding images already in the dataset is a normal thing to do - and
    it used to issue a scripted update for every one of them. Those updates all no-op'd,
    but a no-op is not free: OpenSearch must load the document's _source to evaluate the
    script before it can discover there is nothing to do, and a scripted update rewrites
    the whole document anyway. On an index whose vectors live on s3vector that load is a
    per-document S3 fetch, so a re-add of 1000 images cost 1000 S3 round trips to write
    nothing at all.
    """
    image_ids = list(dict.fromkeys(image_ids))  # de-dupe, preserve order
    # The GroupType is not ensured here: this dataset IS of type single_image and
    # Dataset.type is a PROTECTed FK, so the row exists. Membership.role is a plain
    # char field, so the Role row is not needed to write memberships either.
    with transaction.atomic():
        groups = groups_for_images(image_ids)
        group_ids = [groups[image_id].id for image_id in image_ids]
        num_updated = dataset.add_groups(group_ids)

    # os_synced=False is precisely "Postgres moved, OpenSearch has not caught up", set by
    # groups_for_images on a new/revived membership and by add_groups on a new/revived
    # dataset membership. An image with neither is already correct in OpenSearch, in both
    # denorms - so writing it again would only pay for the privilege of changing nothing.
    stale_group_ids = set(
        Membership.objects.filter(group_id__in=group_ids, role=SINGLE_IMAGE_ROLE, os_synced=False).values_list(
            'group_id', flat=True
        )
    ) | set(
        DatasetMembership.objects.filter(dataset=dataset, group_id__in=group_ids, os_synced=False).values_list(
            'group_id', flat=True
        )
    )
    changed_images = [image_id for image_id in image_ids if groups[image_id].id in stale_group_ids]
    if not changed_images:
        return num_updated

    # OpenSearch phase, after the PG commit: one bulk update per 1000 images, writing
    # both the group denorm and the datasets denorm. If it raises, the rows stay
    # os_synced=False and the reconciler repairs them.
    gid_by_image = {image_id: groups[image_id].os_encoded_id for image_id in changed_images}
    sync_single_image_denorm(gid_by_image, SINGLE_IMAGE_ROLE)
    changed_group_ids = [groups[image_id].id for image_id in changed_images]
    Membership.objects.filter(group_id__in=changed_group_ids, role=SINGLE_IMAGE_ROLE, os_synced=False).update(
        os_synced=True
    )
    dataset.memberships.filter(group_id__in=changed_group_ids, deleted_at__isnull=True).update(os_synced=True)
    return num_updated
