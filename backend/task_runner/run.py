import argparse
import logging
import os
import time
from threading import Thread

from dask.distributed import Client, LocalCluster, WorkerPlugin

from backend.task_runner.task_config import PeriodicTaskConfig, QueuedTaskConfig
from backend.task_runner.tasks import (
    delete_duplicates_task,
    delete_marked_for_deletion_task,
    mark_duplicates_task,
    # update_coca_embedding_task,
    update_count_stats_task,
    update_queue_stats_task,
    update_thumbnail_task,
)
from backend.task_runner.tasks.utils import TaskResult

logger = logging.getLogger('task_runner')
logger.setLevel(logging.INFO)


def init_django(settings_name):
    # initialize Django and settings
    from django.apps import apps

    if not apps.ready:
        settings_module = f"backend.config.settings.{settings_name}"
        logger.info(f"Initializing Django with settings module {settings_module}...")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
        import django

        django.setup()


class DjangoSetupPlugin(WorkerPlugin):
    def __init__(self, settings_name):
        super().__init__()
        self.settings_name = settings_name

    def setup(self, worker):
        init_django(settings_name=self.settings_name)


def start_local_cluster(workers=None, threads=None):
    logger.info(f"Starting local Dask cluster with {workers} workers and {threads} threads")
    cluster = LocalCluster(
        n_workers=workers,
        threads_per_worker=threads,
        processes=True,
        memory_limit='14GB',
        timeout=300,
        scheduler_kwargs={
            'idle_timeout': None,
            'allowed_failures': 3,
            'worker_ttl': '30m',
        },
        death_timeout=60,
        lifetime_restart=True,
        resources={'MEMORY_GB': 14},
    )
    logger.info("Local Dask cluster started")

    # Add small delay to ensure cluster is ready
    time.sleep(2)

    client = Client(
        cluster,
        timeout="600s",
        heartbeat_interval="120s",
        set_as_default=True,
        name='task-runner',
        direct_to_workers=True,
    )

    # Wait for workers to connect
    client.wait_for_workers(n_workers=len(cluster.workers))
    logger.info(f"All {len(cluster.workers)} workers connected successfully")

    return client


def init_dask_client(settings_name, workers=None, threads=None):
    try:
        client = start_local_cluster(workers=workers, threads=threads)
        client.register_plugin(DjangoSetupPlugin(settings_name))
        logger.info(f"Dask dashboard available at: {client.dashboard_link}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Dask client: {e}")
        raise


def start_periodic_tasks(client, tasks: list[PeriodicTaskConfig] | None = None):
    # Start periodic tasks
    if tasks is None:
        tasks = []

    def start_periodic_task(task):
        def schedule_next():
            start_time = time.time()
            logger.info(f"Running periodic task: {task.name}")
            future = client.submit(
                task.task_function,
                pure=False,
            )

            def on_done(f):
                duration = time.time() - start_time
                try:
                    f.result()  # This will raise any exceptions that occurred
                    logger.info(f"Periodic task completed: {task.name} in {duration:.2f}s")
                except Exception as e:
                    logger.error(f"Periodic task failed: {task.name}, error: {e}")
                client.loop.call_later(task.interval_seconds - duration, schedule_next)

            future.add_done_callback(on_done)

        schedule_next()

    threads = []
    for task in tasks:
        if not isinstance(task, PeriodicTaskConfig):
            raise ValueError(f"Task is not a PeriodicTaskConfig: {task}")

        task_thread = Thread(
            target=start_periodic_task,
            kwargs=dict(
                task=task,
            ),
        )
        task_thread.start()
        threads.append(task_thread)


def start_queued_tasks(client, tasks: list[QueuedTaskConfig] | None = None):
    # Start queue-based tasks
    if tasks is None:
        tasks = []

    def start_queued_task(task):
        futures = []
        next_kwargs = {}
        while True:
            # Monitor worker status
            n_workers = len(client.scheduler_info()['workers'])
            if n_workers == 0:
                logger.error(f"No workers available for {task.name}, waiting for workers to reconnect...")
                time.sleep(5)  # Wait before retrying
                continue

            # Clean up completed futures and explicitly cancel any failed ones
            current_futures = []
            for f in futures:
                if f.done():
                    if f.status == 'error':
                        f.cancel()
                else:
                    current_futures.append(f)
            futures = current_futures

            queue_size = len(futures)
            logger.info(f'Queue size for {task.name}: {queue_size} (workers: {n_workers})')

            if queue_size < task.desired_queue_size:
                # retrieve new items and submit tasks
                try:
                    task_result = task.queue_feed_function(**next_kwargs)
                    if isinstance(task_result, TaskResult):
                        items = task_result.result
                        next_kwargs = task_result.next_kwargs
                    else:
                        items = task_result
                    logger.info(f'Got {len(items)} items for {task.name}')
                    if items:
                        # task submission
                        try:
                            new_futures = client.map(
                                task.task_function,
                                items,
                                retries=task.retries,
                                resources={'MEMORY_GB': 2},
                            )
                            futures.extend(new_futures)
                        except Exception as e:
                            logger.error(f"Failed to submit tasks for {task.name}: {e!s}")
                    else:
                        logger.info(f'No items to process for {task.name}')
                except Exception as e:
                    logger.error(f'Error fetching items for {task.name}: {e}')

            time.sleep(task.queue_feed_interval_seconds)

    threads = []
    for task in tasks:
        if not isinstance(task, QueuedTaskConfig):
            raise ValueError(f"Task is not a QueuedTaskConfig: {task}")

        task_thread = Thread(
            target=start_queued_task,
            kwargs=dict(
                task=task,
            ),
        )
        task_thread.start()
        threads.append(task_thread)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--settings',
        type=str,
        default='prod',
        required=False,
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        required=False,
    )
    parser.add_argument(
        '--threads',
        type=int,
        default=None,
        required=False,
    )
    args = parser.parse_args()
    init_django(args.settings)

    periodic_tasks = [
        update_count_stats_task,
        update_queue_stats_task,
    ]
    queued_tasks = [
        delete_duplicates_task,
        delete_marked_for_deletion_task,
        update_thumbnail_task,
        # update_coca_embedding_task,
        mark_duplicates_task,
    ]

    workers = args.workers or os.getenv("DASK_WORKERS", None)
    if isinstance(workers, str):
        try:
            workers = int(workers)
        except ValueError:
            workers = None
    threads = args.threads or os.getenv("DASK_THREADS", None)
    if isinstance(threads, str):
        try:
            threads = int(threads)
        except ValueError:
            threads = None

    client = init_dask_client(settings_name=args.settings, workers=workers, threads=threads)

    start_periodic_tasks(client, periodic_tasks)
    start_queued_tasks(client, queued_tasks)

    # keep the main program running indefinitely
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('Shut down.')
        exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info('Shut down.')
        exit(0)
