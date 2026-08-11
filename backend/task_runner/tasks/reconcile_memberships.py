"""Periodic reconciliation of Membership.os_synced=False rows.

Catches the rare case where PG committed but the inline OS write failed
(or the process died between PG commit and the mark-synced step). In a
healthy system this task does no OS writes — the feed query against the
partial index returns no group ids.

Imports are inside the function on purpose: Dask workers initialize
Django lazily via DjangoSetupPlugin (see backend/task_runner/run.py),
same pattern as the other task modules.
"""

import logging

logger = logging.getLogger('task_runner')


def reconcile_memberships_periodic():
    """Drive every unsynced Membership (in non-deleted groups) to OS."""
    from backend.dataroom.groups.os_sync import refresh_images
    from backend.dataroom.management.commands.reconcile_memberships import reconcile_group
    from backend.dataroom.models.group import Membership

    unsynced_group_ids = list(
        Membership.objects.filter(os_synced=False, group__deleted_at__isnull=True)
        .values_list('group_id', flat=True)
        .distinct()
        .order_by('group_id')
    )
    if not unsynced_group_ids:
        return

    total = 0
    for gid in unsynced_group_ids:
        total += reconcile_group(gid)
    refresh_images()
    logger.info(f"reconcile_memberships: synced {total} membership(s) across {len(unsynced_group_ids)} group(s)")
