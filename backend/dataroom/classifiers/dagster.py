"""The classifier runner, a Dagster deployment on ml-platform.

The integration is three calls over Dagster's HTTP APIs, all from here:

- ``addDynamicPartition`` (GraphQL): a classifier version or a set becomes a
  partition key before anything runs for it.
- ``POST /report_asset_observation/`` (REST): the version's labelled sets go
  onto the external ``labels`` asset, with ``Classifier.labels_version`` as the
  data version. Dagster reads the version's staleness from that.
- ``launchPipelineExecution`` (GraphQL): a job run, with the partition key as
  the ``dagster/partition`` tag and the Dataroom record ids in the run config.

The runs call back over our REST API (trainings/{id}/report, runs/{id}/report,
scores). One Dagster serves every Dataroom: each deployment has its own asset
graph there, ``dataroom/<env>/...`` in group ``dataroom_<env>``, and
DEPLOYMENT_ENV picks ours. Settings are documented in config/settings/base.py.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
from ddtrace import tracer
from django.conf import settings

from backend.dataroom.classifiers.runner import RunnerError, RunnerNotConfiguredError

if TYPE_CHECKING:
    from backend.dataroom.models.classifier import Classifier, ClassifierApplyRun, ClassifierTraining

LAUNCH_MUTATION = """
mutation LaunchRun($executionParams: ExecutionParams!) {
  launchPipelineExecution(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess { run { runId } }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on PythonError { message }
  }
}
"""

ADD_PARTITION_MUTATION = """
mutation AddPartition($repositorySelector: RepositorySelector!, $partitionsDefName: String!, $partitionKey: String!) {
  addDynamicPartition(
    repositorySelector: $repositorySelector, partitionsDefName: $partitionsDefName, partitionKey: $partitionKey
  ) {
    __typename
    ... on PythonError { message }
    ... on UnauthorizedError { message }
  }
}
"""

RUN_STATUS_QUERY = """
query RunStatus($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run { status }
  }
}
"""

# The kinds of set an apply run can target; the key's first segment.
SET_KINDS = ('dataset', 'tag', 'source', 'query')


def _access_headers() -> dict[str, str]:
    # without these a Dagster behind Cloudflare Access answers with a 302 and no run is created
    client_id = settings.DAGSTER_CF_ACCESS_CLIENT_ID
    client_secret = settings.DAGSTER_CF_ACCESS_CLIENT_SECRET
    if not client_id or not client_secret:
        return {}
    return {'CF-Access-Client-Id': client_id, 'CF-Access-Client-Secret': client_secret}


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One POST to Dagster's webserver, GraphQL or REST, with the Access token."""
    try:
        with httpx.Client() as client:
            response = client.post(url, json=payload, headers=_access_headers(), timeout=30)
            # no follow_redirects, a 302 is the Access login page and would look like a successful call
            response.raise_for_status()
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.is_redirect:
            raise RunnerError(
                f'Dagster redirected to {exc.response.headers.get("location", "?")}, '
                'Cloudflare Access rejected the service token'
            ) from exc
        raise RunnerError(f'classifier service unreachable: {exc}') from exc
    body: dict[str, Any] = response.json() if response.content else {}
    return body


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    if not settings.DAGSTER_GRAPHQL_URL:
        raise RunnerNotConfiguredError('DAGSTER_GRAPHQL_URL is not configured')
    body = _post_json(settings.DAGSTER_GRAPHQL_URL, {'query': query, 'variables': variables})
    if body.get('errors'):
        raise RunnerError(str(body['errors']))
    return body['data']


def _rest_url(path: str) -> str:
    """The webserver's REST endpoints live next to /graphql."""
    if not settings.DAGSTER_GRAPHQL_URL:
        raise RunnerNotConfiguredError('DAGSTER_GRAPHQL_URL is not configured')
    base = settings.DAGSTER_GRAPHQL_URL.rstrip('/')
    if base.endswith('/graphql'):
        base = base[: -len('/graphql')]
    return f'{base}/{path.lstrip("/")}'


# SUCCESS is not here: a run that ended well reported back on its own
_DEAD_STATUSES = {'FAILURE': 'failed', 'CANCELED': 'canceled'}


# --- keys: how Dagster names what we launch ------------------------------------
#
# The asset side (ml-platform, dagster_ml.classifier.assets) builds the same
# strings; the two have to agree or a run lands on the wrong partition.


def _env() -> str:
    return settings.DEPLOYMENT_ENV


def asset_key(name: str) -> list[str]:
    return ['dataroom', _env(), name]


def job_name(name: str) -> str:
    return f'dataroom_{_env()}_{name}'


def op_name(asset: str) -> str:
    """An asset's op, which is what run config addresses: the key joined by __."""
    return '__'.join(asset_key(asset))


def partitions_def(name: str) -> str:
    return f'dataroom_{_env()}_{name}'


def classifier_key(classifier: Classifier) -> str:
    return classifier.slug_version


def set_key(target_type: str, target_value: str) -> str:
    """The partition key of one image selection.

    Every kind is named by something Dataroom already treats as a name: a
    dataset's slug_version, a tag, a source, a saved query's slug. All of them
    are short, stable and free of the ``|`` that joins the dimensions of a
    two-dimensional key, so the key carries the whole selection and no part of
    it has to travel in the run config.
    """
    if target_type not in SET_KINDS:
        raise RunnerError(f'unknown target_type {target_type!r}; expected one of {SET_KINDS}')
    if not target_value:
        raise RunnerError(f'a {target_type} target needs a value')
    if '|' in target_value:
        raise RunnerError(f"a target name cannot contain '|', which joins the dimensions of a key: {target_value!r}")
    return f'{target_type}/{target_value}'


def target_key(classifier: Classifier, target_type: str, target_value: str) -> str:
    """classifier x set, as Dagster spells a two-dimensional key: dimension
    values joined by ``|`` in alphabetical order of dimension name."""
    return f'{classifier_key(classifier)}|{set_key(target_type, target_value)}'


def _run_tags(classifier: Classifier, author: Any, partition_key: str) -> dict[str, str]:
    """Run tags for the Dagster runs page. dagster/partition is what Dagster
    itself reads the run's partition from."""
    tags = {'dataroom/classifier': classifier.slug_version, 'dagster/partition': partition_key}
    if settings.DEPLOYMENT_ENV:
        tags['dataroom/env'] = settings.DEPLOYMENT_ENV
    email = getattr(author, 'email', '')
    if email:
        tags['triggered_by'] = email
    return tags


class DagsterRunner:
    @tracer.wrap()
    def report_labels(self, classifier: Classifier) -> str:
        """Tell Dagster what this version trains on: an observation of the
        ``labels`` asset, data version ``labels_version``. Returns the version.

        Called on every change to the labelled sets and before every launch.
        Reporting the same version twice changes nothing on Dagster's side.
        """
        key = classifier_key(classifier)
        version = classifier.labels_version()
        labels = classifier.labelled_datasets()
        self._register_partition('classifiers', key)
        _post_json(
            _rest_url('/report_asset_observation/'),
            {
                'asset_key': asset_key('labels'),
                'partition': key,
                'data_version': version,
                'description': f'labelled sets of {classifier.slug_version}',
                'metadata': {
                    'pos_datasets': labels['pos'],
                    'neg_datasets': labels['neg'],
                    'val_dataset': labels['val'],
                    'embedding_space': labels['embedding_space'],
                },
            },
        )
        return version

    @tracer.wrap()
    def launch_train(self, classifier: Classifier, training: ClassifierTraining) -> str:
        """One run of the train job, partition = the classifier version."""
        self.report_labels(classifier)
        key = classifier_key(classifier)
        return self._launch_run(
            job_name('train_classifier'),
            {'ops': {op_name('trained_classifier'): {'config': {'training_id': str(training.id)}}}},
            tags=_run_tags(classifier, training.author, key),
        )

    @tracer.wrap()
    def launch_apply(self, classifier: Classifier, apply_run: ClassifierApplyRun, model_id: str) -> str:
        """One run of the apply job, partition = classifier x set."""
        self.report_labels(classifier)
        self._register_partition('sets', set_key(apply_run.target_type, apply_run.target_value))
        # What to score is the partition key; the config says only which model
        # and which Dataroom record to report onto.
        config = {'config': {'apply_run_id': str(apply_run.id), 'model_id': model_id}}
        return self._launch_run(
            job_name('apply_classifier'),
            {'ops': {op_name('target_embeddings'): config, op_name('classified_images'): config}},
            tags=_run_tags(
                classifier, apply_run.author, target_key(classifier, apply_run.target_type, apply_run.target_value)
            ),
        )

    @tracer.wrap()
    def dead_run_error(self, run_id: str) -> str | None:
        """Why the run will never report back, None while it still may."""
        data = _graphql(RUN_STATUS_QUERY, {'runId': run_id})
        result: dict[str, Any] = data['runOrError']
        if result['__typename'] != 'Run':
            return 'The classifier runner no longer knows this run.'
        ended = _DEAD_STATUSES.get(result['status'])
        if ended is None:
            return None
        return f'The run ended as {ended} on the classifier runner without reporting a result.'

    def run_url(self, run_id: str) -> str | None:
        if not settings.DAGSTER_PUBLIC_URL or not run_id:
            return None
        return f"{settings.DAGSTER_PUBLIC_URL.rstrip('/')}/runs/{run_id}"

    def _selector(self) -> dict[str, str]:
        return {
            'repositoryLocationName': settings.DAGSTER_LOCATION_NAME,
            'repositoryName': settings.DAGSTER_REPOSITORY_NAME,
        }

    def _register_partition(self, dimension: str, key: str) -> None:
        """Make a key exist on one of our dynamic partition definitions.
        Adding one that exists is answered with DuplicateDynamicPartitionError,
        which is the outcome we wanted."""
        data = _graphql(
            ADD_PARTITION_MUTATION,
            {
                'repositorySelector': self._selector(),
                'partitionsDefName': partitions_def(dimension),
                'partitionKey': key,
            },
        )
        result: dict[str, Any] = data['addDynamicPartition']
        if result['__typename'] not in ('AddDynamicPartitionSuccess', 'DuplicateDynamicPartitionError'):
            raise RunnerError(f'registering partition {key!r}: {result.get("message") or result["__typename"]}')

    def _launch_run(self, job: str, run_config: dict[str, Any], tags: dict[str, str] | None = None) -> str:
        """Launch a job on the classifier service; returns the Dagster run id."""
        data = _graphql(
            LAUNCH_MUTATION,
            {
                'executionParams': {
                    'selector': {**self._selector(), 'jobName': job},
                    'runConfigData': json.dumps(run_config),
                    'executionMetadata': {
                        'tags': [{'key': key, 'value': value} for key, value in (tags or {}).items()]
                    },
                }
            },
        )
        result: dict[str, Any] = data['launchPipelineExecution']
        if result['__typename'] != 'LaunchRunSuccess':
            detail = result.get('errors') or result.get('message') or result['__typename']
            raise RunnerError(f'launching {job} failed: {detail}')
        return result['run']['runId']
