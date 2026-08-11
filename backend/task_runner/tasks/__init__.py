from backend.task_runner.task_config import PeriodicTaskConfig, QueuedTaskConfig
from backend.task_runner.tasks.delete_images import (
    get_images_marked_as_duplicates,
    get_images_marked_for_deletion,
    image_delete_duplicates,
    image_delete_marked_for_deletion,
)
from backend.task_runner.tasks.r2_migration import r2_migration_fetch_files, r2_migration_get_all_files
from backend.task_runner.tasks.reconcile_datasets import reconcile_datasets_periodic
from backend.task_runner.tasks.reconcile_memberships import reconcile_memberships_periodic
from backend.task_runner.tasks.update_datadog import update_datadog_dashboard
from backend.task_runner.tasks.update_images import (
    get_images_without_duplicate_state,
    get_images_without_embedding,
    get_images_without_thumbnail,
    image_mark_duplicates,
    image_update_coca_embedding,
    image_update_thumbnail,
)
from backend.task_runner.tasks.update_stats import update_count_stats, update_queue_stats

delete_duplicates_task = QueuedTaskConfig(
    task_function=image_delete_duplicates,
    queue_feed_function=get_images_marked_as_duplicates,
    desired_queue_size=500,
    workers=6,
)

delete_marked_for_deletion_task = QueuedTaskConfig(
    task_function=image_delete_marked_for_deletion,
    queue_feed_function=get_images_marked_for_deletion,
    desired_queue_size=500,
    workers=2,
)

update_thumbnail_task = QueuedTaskConfig(
    task_function=image_update_thumbnail,
    queue_feed_function=get_images_without_thumbnail,
    desired_queue_size=500,
    workers=6,
)

update_coca_embedding_task = QueuedTaskConfig(
    task_function=image_update_coca_embedding,
    queue_feed_function=get_images_without_embedding,
    desired_queue_size=500,
    workers=4,
)

mark_duplicates_task = QueuedTaskConfig(
    task_function=image_mark_duplicates,
    queue_feed_function=get_images_without_duplicate_state,
    desired_queue_size=500,
    workers=12,
)

update_datadog_dashboard_task = PeriodicTaskConfig(
    task_function=update_datadog_dashboard,
    interval_seconds=60 * 15,
)

update_count_stats_task = PeriodicTaskConfig(
    task_function=update_count_stats,
    interval_seconds=60 * 2,
)

update_queue_stats_task = PeriodicTaskConfig(
    task_function=update_queue_stats,
    interval_seconds=60 * 2,
)

reconcile_memberships_task = PeriodicTaskConfig(
    task_function=reconcile_memberships_periodic,
    # Every 5 minutes. Only failed inline OS writes land here, so healthy runs are
    # no-ops via the partial index; a minute of polling bought nothing.
    interval_seconds=300,
)

reconcile_datasets_task = PeriodicTaskConfig(
    task_function=reconcile_datasets_periodic,
    # Every 5 minutes. Unlike the memberships reconciler, healthy runs are NOT no-ops:
    # add_images_to_dataset writes OS asynchronously and cannot confirm the write, so it
    # leaves its rows unsynced for this task to drive and flip. A longer interval batches
    # several adds into one recompute per dataset; the async write has already landed the
    # right value within ~1s, so nothing user-visible waits on this.
    interval_seconds=300,
)

r2_migration_task = QueuedTaskConfig(
    task_function=r2_migration_fetch_files,
    queue_feed_function=r2_migration_get_all_files,
    queue_feed_interval_seconds=0.3,
    desired_queue_size=500,
    workers=2,
)
