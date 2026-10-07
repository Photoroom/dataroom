"""Mark trainings and apply runs whose Dagster run died as failed.

Healthy runs report their own result. Every tick this picks the rows still in a non
terminal state, asks Dagster for each run's status, and fails the ones that ended
without reporting or that Dagster no longer knows."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings

# models are imported inside the functions, run.py imports tasks before django.setup()

logger = logging.getLogger(__name__)

# a run launched seconds ago may not be in Dagster's run storage yet
MIN_AGE = timedelta(minutes=2)


def expire_dead_classifier_runs_periodic() -> None:
    from django.utils import timezone

    from backend.dataroom.choices import ApplyRunStatus, TrainingStatus
    from backend.dataroom.classifiers.runner import get_runner
    from backend.dataroom.models.classifier import ClassifierApplyRun, ClassifierTraining

    if not settings.DAGSTER_URL:
        return
    runner = get_runner()

    cutoff = timezone.now() - MIN_AGE
    stale_filter = {'date_updated__lt': cutoff}

    for training in ClassifierTraining.objects.filter(status=TrainingStatus.TRAINING, **stale_filter):
        _sync_row(runner, training, TrainingStatus.FAILED)

    non_terminal = (ApplyRunStatus.LAUNCHED, ApplyRunStatus.RUNNING)
    for apply_run in ClassifierApplyRun.objects.filter(status__in=non_terminal, **stale_filter):
        _sync_row(runner, apply_run, ApplyRunStatus.FAILED)


def _sync_row(runner, row, failed_status: str) -> None:
    from backend.dataroom.classifiers.runner import RunnerError

    error = 'The classifier runner no longer knows this run.'
    if row.dagster_run_id:
        try:
            error = runner.dead_run_error(row.dagster_run_id)
        except RunnerError as exc:
            logger.warning('expire_dead_classifier_runs: could not reach the runner: %s', exc)
            return
        if error is None:
            return
    row.status = failed_status
    row.error = error
    row.save(update_fields=['status', 'error', 'date_updated'])
    logger.info('expire_dead_classifier_runs: marked %s as failed (%s)', row, error)
