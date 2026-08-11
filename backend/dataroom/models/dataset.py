from django.db import connection, models, transaction
from django.utils import timezone

from backend.common.base_model import BaseModel
from backend.dataroom.models.group import Group, GroupType

# Caps both group ids per add/remove-groups request and image ids per add-images
# request. Sized to the s3vector write tax: the denorm write costs ~30-190 ms per
# IMAGE (an S3 round trip each, bounded by the cluster's write threads) and runs
# inside the HTTP request, which gunicorn SIGKILLs at 120 s. 100 images fits the
# smallest cluster with wide margin. The group path is still denominated in groups,
# so 100 groups of N images can exceed the same budget N-fold.
DATASET_UPDATE_GROUPS_LIMIT = 100


class DatasetVersionTypeMismatchError(ValueError):
    """A new version of a slug was created with a different GroupType than its siblings."""

    def __init__(self, slug, existing_type, requested_type):
        self.slug = slug
        self.existing_type = existing_type
        self.requested_type = requested_type
        super().__init__(
            f"Dataset '{slug}' is of type '{existing_type}'. Every version of a slug shares one "
            f"type, so a new version cannot be '{requested_type}'. Use a different slug."
        )


class DatasetVersionManager(models.Manager):
    """Slug-keyed, model-agnostic version manager: auto-increments ``version``
    per ``slug`` on create. Originally shared with the (now removed) image-Dataset."""

    def get_next_version(self, slug):
        version = 1
        latest = self.filter(slug=slug).order_by('-version').first()
        if latest:
            version = latest.version + 1
        return version

    def create(self, *args, **kwargs):
        slug = kwargs.get('slug')
        if not slug:
            raise ValueError('slug is required')

        with transaction.atomic():
            # lock the table to get latest version number, without race conditions
            self.select_for_update().filter(slug=slug)
            latest = self.filter(slug=slug).order_by('-version').first()
            if latest:
                # `type` is immutable on a dataset, and a version is not an escape hatch:
                # a slug names one collection, and every version of it collects the same
                # kind of Group. Without this, `POST /datasets/` with an existing slug and
                # a new type silently changes what the dataset holds.
                requested = kwargs.get('type_id') or getattr(kwargs.get('type'), 'name', None)
                if requested is not None and requested != latest.type_id:
                    raise DatasetVersionTypeMismatchError(slug, latest.type_id, requested)
            version = self.get_next_version(slug)
            return super().create(*args, **kwargs, version=version)

    def filter_by_slug_versions(self, slug_versions):
        return self.filter(slug_version__in=slug_versions)


class Dataset(BaseModel):
    """A versioned, freezable collection of Groups of one immutable GroupType.

    The image-``Dataset`` is a collection of images denormalized into OpenSearch;
    a ``Dataset`` instead collects whole ``Group`` rows of a single
    ``GroupType`` and stores membership purely in Postgres (see
    ``DatasetMembership``). No OpenSearch denorm, no ``os_synced``
    reconciliation — the items are real PG rows.

    ``type`` is fixed at creation and never editable (the API serializer makes it
    read-only on update), mirroring how ``Group.type`` is immutable.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    version = models.PositiveIntegerField()
    slug_version = models.CharField(max_length=110, unique=True)
    type = models.ForeignKey(GroupType, on_delete=models.PROTECT, related_name='datasets')
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    is_frozen = models.BooleanField(default=False)
    cover_image_id = models.CharField(max_length=255, blank=True, default='')

    # DatasetVersionManager is slug-keyed and model-agnostic: reusing it here
    # keeps Dataset versions independent from image-Dataset versions.
    objects = DatasetVersionManager()

    def __str__(self):
        return self.slug_version

    class Meta:
        ordering = ('slug', '-version')
        constraints = [models.UniqueConstraint(fields=['slug', 'version'], name='dataset_slug_version_idx')]

    def save(self, *args, **kwargs):
        if not self.version:
            self.version = Dataset.objects.get_next_version(self.slug)
        self.slug_version = self.get_slug_version()
        super().save(*args, **kwargs)

    def get_slug_version(self):
        return f'{self.slug}/{self.version}'

    def freeze(self):
        self.is_frozen = True
        self.save()

    def unfreeze(self):
        self.is_frozen = False
        self.save()

    def active_groups(self):
        """Active member Groups (membership not soft-deleted, group not deleted)."""
        return Group.objects.filter(
            dataset_memberships__dataset=self,
            dataset_memberships__deleted_at__isnull=True,
            deleted_at__isnull=True,
        )

    def add_groups(self, group_ids) -> int:
        """Add groups to the dataset; revive previously-removed memberships.

        Returns the number of groups that became active members (newly inserted
        or revived). Callers must validate that each group exists and matches
        ``self.type`` — see DatasetViewSet.groups.
        """
        if self.is_frozen:
            raise ValueError('Dataset is frozen')

        group_ids = list(dict.fromkeys(group_ids))  # de-dupe, preserve order
        existing = {m.group_id: m for m in self.memberships.filter(group_id__in=group_ids)}
        # New rows default os_synced=False; the caller drives the OS write and
        # flips them True (or the reconciler does after a failure).
        to_create = [DatasetMembership(dataset=self, group_id=gid) for gid in group_ids if gid not in existing]
        revive_ids = [gid for gid, m in existing.items() if m.deleted_at is not None]

        # batch_size: a copy adds every group of the source at once (no cap), so this is
        # one giant INSERT otherwise.
        if to_create:
            DatasetMembership.objects.bulk_create(to_create, batch_size=5000)
        if revive_ids:
            self.memberships.filter(group_id__in=revive_ids).update(deleted_at=None, os_synced=False)
        return len(to_create) + len(revive_ids)

    def remove_groups(self, group_ids) -> int:
        """Soft-delete the dataset's memberships for these groups. Returns the
        number of rows removed."""
        if self.is_frozen:
            raise ValueError('Dataset is frozen')
        # os_synced=False so the OS write (drop this dataset from the groups'
        # images) is driven by the caller, or retried by the reconciler.
        return self.memberships.filter(group_id__in=group_ids, deleted_at__isnull=True).update(
            deleted_at=timezone.now(), os_synced=False
        )

    def copy_groups_from(self, source: 'Dataset') -> int:
        """Copy active member groups from another same-type dataset into this one.

        Set-based ``INSERT ... SELECT``: the membership rows are copied directly inside
        Postgres, without building a DatasetMembership object per row (which was the
        largest single cost of a copy - ~0.5s per 5000 in profiling). New rows are
        os_synced=False, like add_groups', so the caller drives the OS denorm write.

        Only safe because copy always targets a brand-new dataset (DatasetViewSet.copy),
        so there are no existing memberships to collide with - no revive/dedup to do.
        Returns the number of rows copied.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dataroom_datasetmembership
                    (id, dataset_id, group_id, deleted_at, os_synced, date_created, date_updated)
                SELECT gen_random_uuid(), %s, group_id, NULL, false, now(), now()
                FROM dataroom_datasetmembership
                WHERE dataset_id = %s AND deleted_at IS NULL
                """,
                [self.id, source.id],
            )
            return cursor.rowcount


class DatasetMembership(BaseModel):
    """A Group's membership in a Dataset, stored in Postgres.

    Removals soft-delete (``deleted_at`` set) and a re-add revives the same row,
    mirroring the convention in ``group.Membership``.

    ``os_synced`` is False whenever Postgres has changed and the denormalized
    ``OSImage.datasets`` field (this dataset's ``slug_version`` on the images of
    this group) may not yet reflect it. The API path flips it back to True once
    the inline OS write returns; the periodic reconciler picks up any rows still
    False after a failure or crash. (The other half of the denorm — an image's
    group membership changing — rides on ``group.Membership.os_synced``.)
    """

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='dataset_memberships')
    deleted_at = models.DateTimeField(null=True, blank=True)
    os_synced = models.BooleanField(default=False)

    class Meta:
        constraints = [
            # One row per (dataset, group), unconditional so a re-add revives the
            # same soft-deleted row rather than colliding.
            models.UniqueConstraint(fields=('dataset', 'group'), name='dataset_membership_uniq'),
        ]
        indexes = [
            # Backs the active-member listing and the group_count annotation.
            models.Index(fields=['dataset', 'deleted_at']),
            # Reconciler feed query: distinct datasets/groups with at least one
            # unsynced row. Partial so the index stays tiny — in steady state
            # almost every row is os_synced=True.
            models.Index(
                fields=['dataset'],
                condition=models.Q(os_synced=False),
                name='dataset_unsynced_idx',
            ),
        ]
        ordering = ('date_created',)

    def __str__(self):
        return f'{self.group_id}@{self.dataset_id}'
