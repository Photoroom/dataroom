"""Dataroom's Dagster code location: the classifier pipelines.

Dagster's code-location server loads this package (``dagster api grpc
--package-name dataroom``) and serves whatever ``defs`` holds.

One asset graph per Dataroom deployment, built by ``build_env``: keys
``dataroom/<env>/<name>``, group ``dataroom_<env>``, jobs
``dataroom_<env>_train_classifier`` and ``dataroom_<env>_apply_classifier``,
resource ``dataroom_<env>``. A run's environment is in its asset key and
nowhere in its config, so nothing has to be configured at launch to keep one
deployment's runs out of another's.

``smoke`` proves the location loads and a run can execute. The classifier
assets import torch at module load, so an import error or an OOM there takes
the whole location down and ``smoke`` is the probe that says whether the
server is alive at all.
"""

import dagster as dg

from dataroom.classifier.assets import ENVS, build_env
from dataroom.classifier.dataroom import DataroomResource


_assets: list = []
_jobs: list = []
for _env in ENVS:
    _env_assets, _env_jobs = build_env(_env)
    _assets += _env_assets
    _jobs += _env_jobs

defs = dg.Definitions(
    assets=_assets,
    jobs=_jobs,
    # One resource per deployment rather than one configured at launch: which
    # Dataroom a run talks to follows from the job it is, not from its config.
    resources={f"dataroom_{env}": DataroomResource(env=env) for env in ENVS},
)
