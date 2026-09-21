"""/api/classifiers/{slug}/{v}/train|apply|scores — the classifier-service loop.

Dataroom launches runs on the classifier service through the runner
abstraction; these tests mock the DagsterRunner's GraphQL transport at its
import site (the house pattern for outbound HTTP) and play the service's
callbacks by hand, so the whole loop — views -> runner -> payload — is
exercised without a Dagster in the room.
"""

import io
import json
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
import requests
from django.conf import settings
from pytest_django.fixtures import SettingsWrapper
from pytest_mock import MockerFixture

from backend.api.classifiers.serializers import ensure_val_dataset
from backend.dataroom.choices import ApplyRunStatus, TrainingStatus
from backend.dataroom.datasets.single_image import add_images_to_dataset
from backend.dataroom.models.classifier import Classifier, ClassifierApplyRun, ClassifierTraining
from backend.dataroom.models.latents import LatentType
from backend.users.models.token import Token
from backend.dataroom.models.os_image import OSImage


@pytest.fixture()
def api_url(live_server: Any) -> str:
    return live_server.url + '/api'


@pytest.fixture()
def headers(token: Token) -> dict[str, str]:
    return {'Authorization': f'Token {token.key}'}


@pytest.fixture()
def dagster_graphql(mocker: MockerFixture, settings: SettingsWrapper) -> MagicMock:
    """The DagsterRunner's transports. GraphQL answers by query: partitions
    register, launches get run-123, run status comes from ``answers``. The
    REST side (the labels observation) is ``.rest``. Launch payload
    assertions read the calls back via launched_job() and friends."""
    settings.DAGSTER_GRAPHQL_URL = 'http://dagster.test/graphql'
    answers: dict[str, Any] = {
        'addDynamicPartition': {'__typename': 'AddDynamicPartitionSuccess'},
        'launchPipelineExecution': {'__typename': 'LaunchRunSuccess', 'run': {'runId': 'run-123'}},
        'runOrError': {'__typename': 'Run', 'status': 'STARTED'},
    }

    def answer(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        for field, value in answers.items():
            if field in query:
                return {field: value}
        raise AssertionError(f'unexpected GraphQL query: {query}')

    graphql = mocker.patch('backend.dataroom.classifiers.dagster._graphql', side_effect=answer)
    graphql.answers = answers
    graphql.rest = mocker.patch('backend.dataroom.classifiers.dagster._post_json', return_value={})
    return graphql


def _calls(graphql_mock: MagicMock, field: str) -> list[dict[str, Any]]:
    """The variables of every GraphQL call of one kind, oldest first."""
    return [call.args[1] for call in graphql_mock.call_args_list if field in call.args[0]]


def launched_job(graphql_mock: MagicMock) -> tuple[str, dict[str, Any]]:
    """The (job_name, run_config) of the last launch sent over GraphQL."""
    params = _calls(graphql_mock, 'launchPipelineExecution')[-1]['executionParams']
    return params['selector']['jobName'], json.loads(params['runConfigData'])


def launched_tags(graphql_mock: MagicMock) -> dict[str, str]:
    """The run tags of the last launch sent over GraphQL."""
    tags = _calls(graphql_mock, 'launchPipelineExecution')[-1]['executionParams']['executionMetadata']['tags']
    return {tag['key']: tag['value'] for tag in tags}


def launch_count(graphql_mock: MagicMock) -> int:
    return len(_calls(graphql_mock, 'launchPipelineExecution'))


def registered_partitions(graphql_mock: MagicMock) -> set[tuple[str, str]]:
    """Every (partitions def, key) registered so far."""
    return {(v['partitionsDefName'], v['partitionKey']) for v in _calls(graphql_mock, 'addDynamicPartition')}


def reported_labels(graphql_mock: MagicMock) -> list[dict[str, Any]]:
    """Every labels observation posted to Dagster's REST endpoint, oldest first."""
    observations = []
    for call in graphql_mock.rest.call_args_list:
        url, payload = call.args
        assert url == 'http://dagster.test/report_asset_observation/'
        observations.append(payload)
    return observations


def op(asset: str) -> str:
    return f'dataroom__{settings.DEPLOYMENT_ENV}__{asset}'


def job(name: str) -> str:
    return f'dataroom_{settings.DEPLOYMENT_ENV}_{name}'


@pytest.fixture()
def classifier(api_url: str, headers: dict[str, str], all_images: list[OSImage], user: Any) -> Classifier:
    """A classifier with 4 labelled examples per side (the minimum), one of
    each held out: training measures itself on the held-out set and refuses
    to start without one."""
    response = requests.post(f'{api_url}/classifiers/', json={'slug': 'studio', 'name': 'Studio'}, headers=headers)
    response.raise_for_status()
    classifier = Classifier.objects.get(slug_version='studio/1')
    image_ids = [image.id for image in all_images]
    add_images_to_dataset(classifier.main_pos_dataset, image_ids[:4])
    add_images_to_dataset(classifier.main_neg_dataset, image_ids[4:8])
    add_images_to_dataset(ensure_val_dataset(classifier, user), [image_ids[0], image_ids[4]])
    return classifier


def _image(image_id: str, user: Any) -> OSImage:
    image = OSImage(
        id=image_id,
        author=user.email,
        source='test',
        image=f'images/{image_id}/original.png',
        image_hash=f'sha256:{image_id}',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=1.0,
        aspect_ratio_fraction='1:1',
    )
    image.create()
    return image


@pytest.fixture()
def all_images(user: Any) -> list[OSImage]:
    """Bare indexed images: enough for dataset membership and score writes."""
    return [_image(f'img-{i:02d}', user) for i in range(8)]


def test_train_launches_dagster_run_and_creates_record(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    response = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['status'] == 'training'
    assert data['dagster_run_id'] == 'run-123'
    assert data['n_pos'] == data['n_neg'] == 4

    assert launch_count(dagster_graphql) == 1
    job_name, run_config = launched_job(dagster_graphql)
    # The env is in the job's and the assets' names, so nothing in the run
    # config says which Dataroom to call back into.
    assert job_name == job('train_classifier')
    assert run_config == {'ops': {op('trained_classifier'): {'config': {'training_id': data['id']}}}}
    tags = launched_tags(dagster_graphql)
    assert tags['dataroom/classifier'] == 'studio/1'
    assert tags['dagster/partition'] == 'studio/1'
    assert tags['triggered_by']  # the requesting user's email

    # Before the launch: the version is a partition, and its labelled sets are
    # on the labels asset, so the run trains on what Dataroom pinned.
    assert (f'dataroom_{settings.DEPLOYMENT_ENV}_classifiers', 'studio/1') in registered_partitions(dagster_graphql)
    labels = reported_labels(dagster_graphql)[-1]
    assert labels['asset_key'] == ['dataroom', settings.DEPLOYMENT_ENV, 'labels']
    assert labels['partition'] == 'studio/1'
    assert labels['data_version'] == ':studio-negatives/1,studio-positives/1,studio-validation/1'
    assert labels['metadata'] == {
        'pos_datasets': ['studio-positives/1'],
        'neg_datasets': ['studio-negatives/1'],
        'val_dataset': 'studio-validation/1',
        'embedding_space': '',
    }
    assert data['labels_version'] == labels['data_version']

    # A trained version keeps its labels: it and its datasets are locked.
    classifier.refresh_from_db()
    assert classifier.is_frozen
    assert all(dataset.is_frozen for dataset in classifier.owned_datasets())


def test_train_needs_examples_on_both_sides(api_url: str, headers: dict[str, str], dagster_graphql: MagicMock) -> None:
    requests.post(f'{api_url}/classifiers/', json={'slug': 'empty', 'name': 'Empty'}, headers=headers)
    response = requests.post(f'{api_url}/classifiers/empty/1/train/', json={}, headers=headers)
    assert response.status_code == 400
    assert 'at least 4' in response.text
    assert launch_count(dagster_graphql) == 0  # creating it reported its labels, nothing ran


def test_train_draws_the_default_hold_out_when_none_was_sampled(api_url: str, headers: dict[str, str], dagster_graphql: MagicMock, user: Any) -> None:
    """The runner picks the model by held-out precision and refuses a version
    without one. Rather than bouncing the user, Train draws the default 20%
    per side and keeps it, so the set is fixed for every later retrain."""
    requests.post(f'{api_url}/classifiers/', json={'slug': 'noval', 'name': 'No val'}, headers=headers).raise_for_status()
    classifier = Classifier.objects.get(slug_version='noval/1')
    image_ids = [_image(f'noval-{i:02d}', user).id for i in range(20)]
    add_images_to_dataset(classifier.main_pos_dataset, image_ids[:10])
    add_images_to_dataset(classifier.main_neg_dataset, image_ids[10:])

    response = requests.post(f'{api_url}/classifiers/noval/1/train/', json={}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()['n_val'] == 4  # 20% of 10 per side
    classifier.refresh_from_db()
    assert classifier.val_dataset.slug_version == 'noval-validation/1'
    # The runner is told about the new labelled set before the run launches.
    labels = reported_labels(dagster_graphql)[-1]
    assert labels['partition'] == 'noval/1'
    assert labels['metadata']['val_dataset'] == 'noval-validation/1'
    assert response.json()['labels_version'] == ':noval-negatives/1,noval-positives/1,noval-validation/1'
    assert launch_count(dagster_graphql) == 1


def test_train_cannot_draw_a_hold_out_for_a_locked_version(api_url: str, headers: dict[str, str], dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    requests.post(f'{api_url}/classifiers/', json={'slug': 'locked', 'name': 'Locked'}, headers=headers).raise_for_status()
    classifier = Classifier.objects.get(slug_version='locked/1')
    image_ids = [image.id for image in all_images]
    add_images_to_dataset(classifier.main_pos_dataset, image_ids[:4])
    add_images_to_dataset(classifier.main_neg_dataset, image_ids[4:8])
    requests.post(f'{api_url}/classifiers/locked/1/lock/', headers=headers).raise_for_status()

    response = requests.post(f'{api_url}/classifiers/locked/1/train/', json={}, headers=headers)
    assert response.status_code == 400
    assert 'locked' in response.text
    assert launch_count(dagster_graphql) == 0


def test_train_unconfigured_service_is_503(api_url: str, headers: dict[str, str], classifier: Classifier, settings: SettingsWrapper) -> None:
    settings.DAGSTER_GRAPHQL_URL = None
    response = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers)
    assert response.status_code == 503
    assert ClassifierTraining.objects.count() == 0


def test_report_flips_training_to_trained(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    training_id = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).json()['id']

    response = requests.post(
        f'{api_url}/classifiers/studio/1/trainings/{training_id}/report/',
        json={'status': 'trained', 'model_id': 'abc123', 'metrics': {'val_auc': 0.97, 'n_pos': 4, 'n_neg': 4}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'trained'
    assert data['model_id'] == 'abc123'
    assert data['metrics']['val_auc'] == 0.97

    listed = requests.get(f'{api_url}/classifiers/studio/1/trainings/', headers=headers).json()
    assert [t['status'] for t in listed] == ['trained']


def test_unchanged_examples_reuse_the_training_unless_forced(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    """The caching rule: same labelled datasets + a trained model = no retrain."""
    training_id = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).json()['id']
    requests.post(
        f'{api_url}/classifiers/studio/1/trainings/{training_id}/report/',
        json={'status': 'trained', 'model_id': 'abc123'},
        headers=headers,
    ).raise_for_status()

    again = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers)
    assert again.status_code == 200  # not 201: nothing was launched
    assert again.json()['id'] == training_id
    assert launch_count(dagster_graphql) == 1

    # Forcing is how you retrain a version whose datasets were edited in place.
    forced = requests.post(f'{api_url}/classifiers/studio/1/train/', json={'force': True}, headers=headers)
    assert forced.status_code == 201
    assert forced.json()['forced'] is True
    assert launch_count(dagster_graphql) == 2


def test_report_keeps_the_example_counts_the_training_was_given(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    """The service reports what it learned from, which is smaller than what it
    was given: it holds a validation split back. Those are different numbers,
    and letting the smaller one land on n_pos/n_neg would leave the training
    permanently short of the classifier's own counts, so the page would keep
    saying the annotations had changed and the cache below would never hit."""
    training_id = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).json()['id']

    reported = requests.post(
        f'{api_url}/classifiers/studio/1/trainings/{training_id}/report/',
        json={
            'status': 'trained',
            'model_id': 'abc123',
            'metrics': {'n_pos': 3, 'n_neg': 3, 'n_val_pos': 1},
            'code_version': 'query-head-1',
        },
        headers=headers,
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()['n_pos'] == reported.json()['n_neg'] == 4
    assert reported.json()['metrics']['n_pos'] == 3
    assert reported.json()['code_version'] == 'query-head-1'
    assert reported.json()['labels_version'] == ':studio-negatives/1,studio-positives/1,studio-validation/1'  # at launch

    again = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers)
    assert again.status_code == 200  # the cache still recognises the same examples
    assert again.json()['id'] == training_id


def test_apply_needs_a_trained_model(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    response = requests.post(
        f'{api_url}/classifiers/studio/1/apply/',
        json={'target_type': 'dataset', 'target_value': 'studio-positives/1'},
        headers=headers,
    )
    assert response.status_code == 400
    assert 'no trained model' in response.text


def test_apply_targets_one_named_set(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    """No 'all', no 'annotations': a run is one partition of one set."""
    for body in ({'target_type': 'all'}, {'target_type': 'annotations'}, {'target_type': 'dataset'}):
        response = requests.post(f'{api_url}/classifiers/studio/1/apply/', json=body, headers=headers)
        assert response.status_code == 400, body
    assert launch_count(dagster_graphql) == 0


def test_apply_launches_run_and_scores_flow_back(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    training_id = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).json()['id']
    requests.post(
        f'{api_url}/classifiers/studio/1/trainings/{training_id}/report/',
        json={'status': 'trained', 'model_id': 'abc123'},
        headers=headers,
    ).raise_for_status()

    response = requests.post(
        f'{api_url}/classifiers/studio/1/apply/',
        json={'target_type': 'dataset', 'target_value': 'studio-positives/1'},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run['status'] == 'launched'
    assert run['model_id'] == 'abc123'
    job_name, run_config = launched_job(dagster_graphql)
    assert job_name == job('apply_classifier')
    for asset in ('target_embeddings', 'classified_images'):
        assert run_config['ops'][op(asset)]['config'] == {'apply_run_id': run['id'], 'model_id': 'abc123'}
    # classifier × set, as Dagster spells a two-dimensional key
    assert launched_tags(dagster_graphql)['dagster/partition'] == 'studio/1|dataset/studio-positives/1'
    assert (f'dataroom_{settings.DEPLOYMENT_ENV}_sets', 'dataset/studio-positives/1') in registered_partitions(
        dagster_graphql
    )
    # the labels go up again before every launch, so the run's view of the version is current
    assert reported_labels(dagster_graphql)[-1]['partition'] == 'studio/1'

    # The service reports the total, then posts scores in batches.
    requests.post(
        f'{api_url}/classifiers/studio/1/runs/{run["id"]}/report/',
        json={'status': 'running', 'total': 3},
        headers=headers,
    ).raise_for_status()
    scores = {'img-00': 0.91, 'img-01': 0.12, 'img-02': 0.55}
    response = requests.post(
        f'{api_url}/classifiers/studio/1/scores/',
        json={'scores': scores, 'run_id': run['id']},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {'written': 3, 'missing': []}

    for image_id, expected in scores.items():
        image = OSImage.objects.get(image_id)
        assert image.classifications == {'studio/1': expected}

    requests.post(
        f'{api_url}/classifiers/studio/1/runs/{run["id"]}/report/',
        json={'status': 'completed', 'processed': 3},
        headers=headers,
    ).raise_for_status()
    listed = requests.get(f'{api_url}/classifiers/studio/1/runs/', headers=headers).json()
    assert listed[0]['status'] == 'completed'
    assert listed[0]['processed'] == 3
    assert listed[0]['total'] == 3


def test_a_query_target_is_named_by_its_slug_in_the_key(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock) -> None:
    """A saved query has a slug, which the images API resolves, so the key
    names it and nothing about the target travels in the run config."""
    training_id = requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).json()['id']
    requests.post(
        f'{api_url}/classifiers/studio/1/trainings/{training_id}/report/',
        json={'status': 'trained', 'model_id': 'abc123'},
        headers=headers,
    ).raise_for_status()

    response = requests.post(
        f'{api_url}/classifiers/studio/1/apply/',
        json={'target_type': 'query', 'target_value': 'cats-on-sofas'},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert launched_tags(dagster_graphql)['dagster/partition'] == 'studio/1|query/cats-on-sofas'
    _job, run_config = launched_job(dagster_graphql)
    assert 'target_value' not in run_config['ops'][op('classified_images')]['config']


def test_training_locks_the_version(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    """A trained version has one set of labels. Labelling on continues in a
    new version, which reports its own labels."""
    requests.post(f'{api_url}/classifiers/studio/1/train/', json={}, headers=headers).raise_for_status()

    response = requests.post(
        f'{api_url}/classifiers/studio/1/label/',
        json={'image_ids': [all_images[0].id], 'side': 'negative'},
        headers=headers,
    )
    assert response.status_code == 400
    assert 'locked' in response.text

    response = requests.post(f'{api_url}/classifiers/studio/1/new-version/', json={}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()['slug_version'] == 'studio/2'
    labels = reported_labels(dagster_graphql)[-1]
    assert labels['partition'] == 'studio/2'
    assert labels['metadata']['pos_datasets'] == ['studio-positives/2']


def test_changing_the_labelled_sets_reports_them(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, user: Any) -> None:
    """Dagster learns about a change to the labelled sets when it happens,
    not at the next launch, so the trained head shows as stale right away."""
    # A version without a held-out set: the first draw creates the validation
    # dataset, one more labelled set, and that is reported right away.
    requests.post(f'{api_url}/classifiers/', json={'slug': 'fresh', 'name': 'Fresh'}, headers=headers).raise_for_status()
    fresh = Classifier.objects.get(slug_version='fresh/1')
    extra = [_image(f'fresh-{i:02d}', user).id for i in range(20)]
    add_images_to_dataset(fresh.main_pos_dataset, extra[:10])
    add_images_to_dataset(fresh.main_neg_dataset, extra[10:])
    before = len(reported_labels(dagster_graphql))
    requests.post(
        f'{api_url}/classifiers/fresh/1/holdout/', json={'mode': 'random', 'fraction': 0.2}, headers=headers
    ).raise_for_status()
    labels = reported_labels(dagster_graphql)[before:]
    assert [observation['metadata']['val_dataset'] for observation in labels] == ['fresh-validation/1']
    assert labels[-1]['data_version'] == ':fresh-negatives/1,fresh-positives/1,fresh-validation/1'

    # Editing the version reports again; a new backbone is part of the version.
    requests.patch(
        f'{api_url}/classifiers/studio/1/', json={'embedding_space': 'vitl14'}, headers=headers
    ).raise_for_status()
    assert reported_labels(dagster_graphql)[-1]['data_version'].startswith('vitl14:')


def test_scores_merge_across_classifiers(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    """Two classifiers scoring the same image must not clobber each other."""
    requests.post(f'{api_url}/classifiers/', json={'slug': 'other', 'name': 'Other'}, headers=headers)
    requests.post(
        f'{api_url}/classifiers/studio/1/scores/', json={'scores': {'img-00': 0.9}}, headers=headers
    ).raise_for_status()
    requests.post(
        f'{api_url}/classifiers/other/1/scores/', json={'scores': {'img-00': 0.2}}, headers=headers
    ).raise_for_status()

    image = OSImage.objects.get('img-00')
    assert image.classifications == {'studio/1': 0.9, 'other/1': 0.2}


def test_scores_skip_unknown_images(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    response = requests.post(
        f'{api_url}/classifiers/studio/1/scores/',
        json={'scores': {'img-00': 0.5, 'img-nope': 0.5}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {'written': 1, 'missing': ['img-nope']}


def test_classifications_visible_via_images_api(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    requests.post(
        f'{api_url}/classifiers/studio/1/scores/', json={'scores': {'img-00': 0.77}}, headers=headers
    ).raise_for_status()
    response = requests.get(f'{api_url}/images/?fields=id,classifications', headers=headers)
    by_id = {image['id']: image for image in response.json()['results']}
    assert by_id['img-00']['classifications'] == {'studio/1': 0.77}


def test_dead_dagster_run_is_marked_failed_by_sync(classifier: Classifier, dagster_graphql: MagicMock) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from backend.task_runner.tasks.expire_dead_classifier_runs import expire_dead_classifier_runs_periodic

    training = ClassifierTraining.objects.create(classifier=classifier, dagster_run_id='run-dead')
    ClassifierTraining.objects.filter(id=training.id).update(date_updated=timezone.now() - timedelta(minutes=5))
    apply_run = ClassifierApplyRun.objects.create(
        classifier=classifier,
        training=training,
        target_type='dataset',
        target_value='studio-positives/1',
        dagster_run_id='run-dead',
    )
    ClassifierApplyRun.objects.filter(id=apply_run.id).update(date_updated=timezone.now() - timedelta(minutes=5))

    dagster_graphql.answers['runOrError'] = {'__typename': 'Run', 'status': 'FAILURE'}
    expire_dead_classifier_runs_periodic()

    training.refresh_from_db()
    apply_run.refresh_from_db()
    assert training.status == TrainingStatus.FAILED
    assert apply_run.status == ApplyRunStatus.FAILED
    assert 'without reporting' in training.error
    assert 'failed' in training.error


def test_classifications_score_filter(api_url: str, headers: dict[str, str], classifier: Classifier, dagster_graphql: MagicMock, all_images: list[OSImage]) -> None:
    """The threshold-as-search-filter: classifier + operator + score."""
    requests.post(
        f'{api_url}/classifiers/studio/1/scores/',
        json={'scores': {'img-00': 0.9, 'img-01': 0.6, 'img-02': 0.2}},
        headers=headers,
    ).raise_for_status()

    def count(params):
        return requests.get(f'{api_url}/images/count/?{params}', headers=headers).json()['count']

    assert count('classifications=studio/1__gte:0.5') == 2
    assert count('classifications=studio/1__gte:0.85') == 1
    assert count('classifications=studio/1__lte:0.5') == 1
    assert count('classifications=studio/1__gt:0.9') == 0
    assert count('classifications=studio/1__eq:0.6') == 1
    assert count('has_classifications=studio/1') == 3
    assert count('lacks_classifications=studio/1') == len(all_images) - 3

    response = requests.get(f'{api_url}/images/?classifications=studio/1__gte:0.5&fields=id', headers=headers)
    assert {image['id'] for image in response.json()['results']} == {'img-00', 'img-01'}

    # malformed filters are a 400, not a silent empty result
    response = requests.get(f'{api_url}/images/count/?classifications=studio/1__между:0.5', headers=headers)
    assert response.status_code == 400
    response = requests.get(f'{api_url}/images/count/?classifications=studio/1:high', headers=headers)
    assert response.status_code == 400


def _grow(classifier: Classifier, user: Any, per_side: int) -> None:
    """Label `per_side` more images onto each side, so a draw has room to take
    some without dropping either side below the training minimum."""
    extra = [_image(f'grow-{i:02d}', user).id for i in range(per_side * 2)]
    add_images_to_dataset(classifier.main_pos_dataset, extra[:per_side])
    add_images_to_dataset(classifier.main_neg_dataset, extra[per_side:])


def test_holdout_refuses_to_starve_a_side(api_url: str, headers: dict[str, str], classifier: Classifier) -> None:
    """The fixture sits at the minimum per side, so nothing can be held back."""
    response = requests.post(
        f'{api_url}/classifiers/studio/1/holdout/',
        json={'mode': 'random', 'fraction': 0.2},
        headers=headers,
    )
    assert response.status_code == 400
    assert 'fewer than the 4 per side' in response.text


def test_holdout_samples_each_side(api_url: str, headers: dict[str, str], classifier: Classifier, user: Any) -> None:
    _grow(classifier, user, per_side=6)  # 10 per side

    response = requests.post(
        f'{api_url}/classifiers/studio/1/holdout/',
        json={'mode': 'random', 'fraction': 0.2},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['val_pos'] == body['val_neg'] == 2
    # The fixture already held one out per side; a draw replaces the set, so
    # the net growth is two whatever the sample happened to keep.
    assert body['added'] - body['removed'] == 2

    after = requests.get(f'{api_url}/classifiers/studio/1/', headers=headers).json()
    assert after['val_dataset'] == 'studio-validation/1'
    assert after['counts']['val_pos'] == after['counts']['val_neg'] == 2


def test_embedding_latent_round_trip(api_url: str, headers: dict[str, str], all_images: list[OSImage]) -> None:
    """What the classifier service does per image: upload the token table as a
    float16 .npy latent, find images by its presence, read the array back."""
    LatentType.objects.get_or_create(name='vitb14_reg_518_features')
    tokens = np.random.default_rng(0).normal(size=(4, 768)).astype(np.float16)
    buffer = io.BytesIO()
    np.save(buffer, tokens)
    files = {
        'json': (None, '{}', 'text/plain'),
        'latent_json_0': (None, json.dumps({'latent_type': 'vitb14_reg_518_features'}), 'text/plain'),
        'latent_0': ('vitb14_reg_518_features.npy', buffer.getvalue(), 'application/octet-stream'),
    }
    response = requests.put(f'{api_url}/images/img-00/', files=files, headers=headers)
    assert response.status_code == 200, response.text
    OSImage.objects.refresh()  # a latent-only update leaves the refresh to refresh_interval

    def count(**params: str) -> int:
        return requests.get(f'{api_url}/images/count/', params=params, headers=headers).json()['count']

    assert count(has_latents='vitb14_reg_518_features') == 1
    assert count(lacks_latents='vitb14_reg_518_features') == len(all_images) - 1

    image = requests.get(
        f'{api_url}/images/img-00/?fields=id,latents&return_latents=vitb14_reg_518_features', headers=headers
    ).json()
    assert [latent['latent_type'] for latent in image['latents']] == ['vitb14_reg_518_features']
    assert image['latents'][0]['file_direct_url']
    stored = np.load(OSImage.objects.get(id='img-00').latents.latents['vitb14_reg_518_features'].file_object)
    assert stored.dtype == np.float16
    assert stored.shape == (4, 768)
    assert stored[0].tolist() == tokens[0].tolist()
