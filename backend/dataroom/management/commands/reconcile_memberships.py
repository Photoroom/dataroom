"""Reconcile Memberships whose os_synced=False with the OpenSearch denorm.

In normal operation the API path keeps Postgres and OpenSearch in sync
in-line: PG writes flip ``Membership.os_synced=False``, the OS write
runs after PG commits, and on success the touched rows are marked
``os_synced=True``. If the OS write fails (network blip, OS down, the
process is killed between commit and the mark-synced step), the rows
stay ``False`` and this command's job is to drive them to OS and flip
the flag.

Soft-deleted groups are handled separately by ``cleanup_deleted_groups``
— we filter to ``group__deleted_at__isnull=True`` to keep
responsibilities clean.

Run manually:
    python manage.py reconcile_memberships

Or via the periodic ``reconcile_memberships_task`` registered with the
task runner (see backend/task_runner/tasks/reconcile_memberships.py).
"""

import logging
from collections import defaultdict

from django.core.management.base import BaseCommand

from backend.dataroom.datasets.os_sync import recompute_datasets_for_images
from backend.dataroom.groups.os_sync import apply_delta_to_images, refresh_images
from backend.dataroom.models.group import Membership

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Drive every Membership with os_synced=False to the OpenSearch "
        "denorm, then flip the flag. Skips memberships in soft-deleted "
        "groups (cleanup_deleted_groups handles those)."
    )

    def handle(self, *args, **options):
        # Reconcile one group at a time so the OS deltas stay small and
        # bounded; this also matches the periodic task's per-group work
        # unit so the two share their core logic.
        unsynced_group_ids = list(
            Membership.objects.filter(os_synced=False, group__deleted_at__isnull=True)
            .values_list('group_id', flat=True)
            .distinct()
            .order_by('group_id')
        )
        self.stdout.write(f"Reconciling {len(unsynced_group_ids)} group(s)...")
        for gid in unsynced_group_ids:
            n = reconcile_group(gid)
            self.stdout.write(f"  group {gid}: synced {n} membership(s)")
        if unsynced_group_ids:
            refresh_images()
        self.stdout.write(self.style.SUCCESS("Done."))


def reconcile_group(group_id) -> int:
    """Drive one group's unsynced memberships to OS, mark them synced.

    Returns the number of memberships flipped to os_synced=True. The
    reconciliation:

    - reads the row pks + state at the start of the call (a snapshot);
    - per-image, computes the (add, remove) delta from PG truth
      (active rows -> add, soft-deleted rows -> remove);
    - applies via ``apply_delta_to_images`` bucketed by (add, remove)
      signature — same machinery the inline path uses, so OS scripts
      stay idempotent;
    - marks only the pks we observed as synced. Rows touched by a
      concurrent writer after our snapshot keep ``os_synced=False`` and
      get caught on the next pass.
    """
    rows = list(
        Membership.objects.filter(group_id=group_id, os_synced=False).values(
            'id', 'group__type_id', 'image_id', 'role', 'deleted_at'
        )
    )
    if not rows:
        return 0

    gid = f"{rows[0]['group__type_id']}::{group_id}"
    delta: dict = defaultdict(lambda: {'add': [], 'remove': []})
    for r in rows:
        if r['deleted_at'] is None:
            delta[r['image_id']]['add'].append(r['role'])
        else:
            delta[r['image_id']]['remove'].append(r['role'])

    # Bucket by (add-set, remove-set) so each image hits OS exactly once
    # this pass — same anti-race technique as _apply_os_delta.
    buckets = defaultdict(list)
    for image_id, ops in delta.items():
        key = (tuple(sorted(ops['add'])), tuple(sorted(ops['remove'])))
        buckets[key].append(image_id)
    for (add_roles, remove_roles), image_ids in buckets.items():
        apply_delta_to_images(image_ids, gid, add_roles, remove_roles)

    # The same membership changes can shift these images' dataset denorm (this
    # group's dataset memberships), so re-derive it from PG truth too.
    # Refresh first so the datasets update_by_query doesn't race the group-denorm
    # write above on the same docs (conflicts:proceed would silently drop it).
    if delta:
        refresh_images()
        recompute_datasets_for_images(list(delta.keys()))

    pks = [r['id'] for r in rows]
    Membership.objects.filter(pk__in=pks).update(os_synced=True)
    return len(pks)
