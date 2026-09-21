"""The runner behind the classifier train/apply actions.

Results never come through here: whatever executes the work reports back over
the classifier REST endpoints (trainings/{id}/report, runs/{id}/report, scores).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from backend.dataroom.classifiers.dagster import DagsterRunner


class RunnerError(Exception):
    """The runner could not do what was asked (unreachable, rejected launch)."""


class RunnerNotConfiguredError(RunnerError):
    """The runner is not configured in this deployment; classifier actions 503."""


def get_runner() -> DagsterRunner:
    """The deployment's configured runner (CLASSIFIER_RUNNER setting)."""
    # dagster.py imports the exceptions above
    from backend.dataroom.classifiers.dagster import DagsterRunner

    name: str = settings.CLASSIFIER_RUNNER
    if name == 'dagster':
        return DagsterRunner()
    raise ImproperlyConfigured(f'unknown CLASSIFIER_RUNNER {name!r}; known: dagster')
