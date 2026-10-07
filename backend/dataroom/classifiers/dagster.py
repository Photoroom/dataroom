"""Starts classifier runs on Dagster and reports their datasets to it.

Partitions: training ``cats/2``, scoring ``cats/2|dataset/shop/3``.
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

# a set's partition key starts with one of these, e.g. 'dataset/shop/3'
SET_KINDS = ('dataset', 'tag', 'source', 'query')


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        with httpx.Client() as client:
            response = client.post(url, json=payload, headers=settings.DAGSTER_HTTP_HEADERS, timeout=30)
            # a redirect means an auth proxy rejected the request, so do not follow it
            response.raise_for_status()
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.is_redirect:
            raise RunnerError(
                f'Dagster redirected to {exc.response.headers.get("location", "?")}, check DAGSTER_HTTP_HEADERS'
            ) from exc
        raise RunnerError(f'classifier service unreachable: {exc}') from exc
    body: dict[str, Any] = response.json() if response.content else {}
    return body


def _url(path: str) -> str:
    if not settings.DAGSTER_URL:
        raise RunnerNotConfiguredError('DAGSTER_URL is not configured')
    return f"{settings.DAGSTER_URL.rstrip('/')}{path}"


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    body = _post_json(_url('/graphql'), {'query': query, 'variables': variables})
    if body.get('errors'):
        raise RunnerError(str(body['errors']))
    return body['data']


# run ended without sending a result
_DEAD_STATUSES = {'FAILURE': 'failed', 'CANCELED': 'canceled'}


# Names of our assets, jobs and partitions in Dagster, e.g. job 'dataroom_dev_train_classifier'.
# They must match build_env in dagster/dataroom/classifier/assets.py.


def _env() -> str:
    return settings.DEPLOYMENT_ENV


def asset_key(name: str) -> list[str]:
    return ['dataroom', _env(), name]


def job_name(name: str) -> str:
    return f'dataroom_{_env()}_{name}'


def op_name(asset: str) -> str:
    """E.g. 'dataroom__dev__trained_classifier'. The run config uses this name to configure a step."""
    return '__'.join(asset_key(asset))


def partitions_def(name: str) -> str:
    return f'dataroom_{_env()}_{name}'


def classifier_key(classifier: Classifier) -> str:
    return classifier.slug_version


def set_key(target_type: str, target_value: str) -> str:
    """Partition key of an image group, e.g. 'dataset/shop/3' or 'query/small-imgs'."""
    if target_type not in SET_KINDS:
        raise RunnerError(f'unknown target_type {target_type!r}; expected one of {SET_KINDS}')
    if not target_value:
        raise RunnerError(f'a {target_type} target needs a value')
    if '|' in target_value:
        raise RunnerError(f"a target name cannot contain '|', which joins the dimensions of a key: {target_value!r}")
    return f'{target_type}/{target_value}'


def target_key(classifier: Classifier, target_type: str, target_value: str) -> str:
    """E.g. 'cats/2|dataset/shop/3'. Dagster expects the classifier first, then the set, joined by '|'."""
    return f'{classifier_key(classifier)}|{set_key(target_type, target_value)}'


def _run_tags(classifier: Classifier, author: Any, partition_key: str) -> dict[str, str]:
    """Tags shown on the Dagster run. Dagster reads the run's partition from 'dagster/partition'."""
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
        """Tells Dagster which datasets this version trains on. Sending the same data again changes nothing."""
        key = classifier_key(classifier)
        version = classifier.labels_version()
        labels = classifier.labelled_datasets()
        self._register_partition('classifiers', key)
        _post_json(
            _url('/report_asset_observation/'),
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
        self.report_labels(classifier)
        key = classifier_key(classifier)
        return self._launch_run(
            job_name('train_classifier'),
            {'ops': {op_name('trained_classifier'): {'config': {'training_id': str(training.id)}}}},
            tags=_run_tags(classifier, training.author, key),
        )

    @tracer.wrap()
    def launch_apply(self, classifier: Classifier, apply_run: ClassifierApplyRun, model_id: str) -> str:
        self.report_labels(classifier)
        self._register_partition('sets', set_key(apply_run.target_type, apply_run.target_value))
        # the partition key already says which images to score
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
        """Returns why the run will never send a result, or None if it still can."""
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
        """Adds a key to a dynamic partition list in Dagster.

        dimension 'classifiers' -> dataroom_<env>_classifiers, e.g. cats/2
        dimension 'sets'        -> dataroom_<env>_sets, e.g. dataset/shop/3
        A scoring key like cats/2|dataset/shop/3 needs both parts added.
        A key added before gives DuplicateDynamicPartitionError, which we ignore.
        """
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
