"""Reconcile DatasetMemberships whose os_synced=False with the OS denorm.

In normal operation the API path keeps Postgres and the ``OSImage.datasets``
denorm in sync in-line: PG writes flip ``DatasetMembership.os_synced=False``,
the OS recompute runs after PG commits, and on success the touched rows are
marked ``os_synced=True``. If the OS write fails (network blip, OS down, the
process is killed between commit and the mark-synced step), the rows stay
``False`` and this command drives them to OS and flips the flag.

Memberships of soft-deleted *groups* are skipped — when a group is deleted its
image memberships are scrubbed by the group cleanup path, which recomputes the
affected images' datasets via ``group.Membership.os_synced``.

Run manually:
    python manage.py reconcile_datasets

Or via the periodic task (see backend/task_runner/tasks/reconcile_datasets.py).
"""

import logging

from django.core.management.base import BaseCommand

from backend.dataroom.datasets.os_sync import recompute_datasets_for_groups
from backend.dataroom.models.dataset import DatasetMembership

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Drive every DatasetMembership with os_synced=False to the "
        "OSImage.datasets denorm, then flip the flag. Skips memberships in "
        "soft-deleted groups (the group cleanup path handles those)."
    )

    def handle(self, *args, **options):
        dataset_ids = list(
            DatasetMembership.objects.filter(os_synced=False, group__deleted_at__isnull=True)
            .values_list('dataset_id', flat=True)
            .distinct()
            .order_by('dataset_id')
        )
        self.stdout.write(f"Reconciling {len(dataset_ids)} dataset(s)...")
        for did in dataset_ids:
            n = reconcile_dataset(did)
            self.stdout.write(f"  dataset {did}: synced {n} membership(s)")
        self.stdout.write(self.style.SUCCESS("Done."))


def reconcile_dataset(dataset_id) -> int:
    """Drive one dataset's unsynced memberships to OS, mark them synced.

    Reads the unsynced rows at the start (a snapshot), recomputes the affected
    groups' images from PG truth (same primitive the inline path uses, so it
    stays idempotent), then marks only the observed pks synced. Rows touched by
    a concurrent writer after the snapshot stay False for the next pass.
    """
    rows = list(
        DatasetMembership.objects.filter(
            dataset_id=dataset_id, os_synced=False, group__deleted_at__isnull=True
        ).values_list('id', 'group_id')
    )
    if not rows:
        return 0

    group_ids = [r[1] for r in rows]
    recompute_datasets_for_groups(group_ids)

    pks = [r[0] for r in rows]
    DatasetMembership.objects.filter(pk__in=pks).update(os_synced=True)
    return len(pks)
