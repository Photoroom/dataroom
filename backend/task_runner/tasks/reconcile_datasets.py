"""Periodic reconciliation of DatasetMembership.os_synced=False rows.

Catches the case where PG committed but the OS write of the ``OSImage.datasets``
denorm did not land: the inline write failed, the process died between PG commit
and the mark-synced step, or the add-images path handed OpenSearch an async task
whose outcome nobody observed.

That last case is routine, not exceptional: ``add_images_to_dataset`` always
leaves its rows ``os_synced=False`` because it cannot know the async task
succeeded. So this task normally has work to do after every add, and it re-SETs
the value the async task already wrote — idempotent, but a real re-index of every
doc, not a free no-op. What it buys is that a failed async task can never leave
Postgres and OpenSearch permanently disagreeing.

Imports are inside the function on purpose: Dask workers initialize Django
lazily via DjangoSetupPlugin (see backend/task_runner/run.py), same pattern as
the other task modules.
"""

import logging

logger = logging.getLogger('task_runner')


def reconcile_datasets_periodic():
    """Drive every unsynced DatasetMembership (in non-deleted groups) to OS."""
    from backend.dataroom.management.commands.reconcile_datasets import reconcile_dataset
    from backend.dataroom.models.dataset import DatasetMembership

    unsynced_dataset_ids = list(
        DatasetMembership.objects.filter(os_synced=False, group__deleted_at__isnull=True)
        .values_list('dataset_id', flat=True)
        .distinct()
        .order_by('dataset_id')
    )
    if not unsynced_dataset_ids:
        return

    total = 0
    for did in unsynced_dataset_ids:
        total += reconcile_dataset(did)
    logger.info(f"reconcile_datasets: synced {total} membership(s) across {len(unsynced_dataset_ids)} dataset(s)")
