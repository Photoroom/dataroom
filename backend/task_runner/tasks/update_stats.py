import logging

logger = logging.getLogger('task_runner')


def update_count_stats():
    from backend.dataroom.models.stats import Stats

    Stats.objects.update_count_stats()


def update_queue_stats():
    from backend.dataroom.models.stats import Stats

    Stats.objects.update_queue_stats()
