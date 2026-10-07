"""``client.classifiers`` - creating a classifier, labelling images through it,
and the reports the classifier service posts back."""

import asyncio
import time
import uuid

import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.datasets.single_image import SINGLE_IMAGE_TYPE, ensure_single_image_type
from backend.dataroom.models.classifier import Classifier, ClassifierApplyRun, ClassifierTraining


async def _wait_for_examples(DataRoom, slug_version, side, expected_count, timeout=15.0):
    """Poll until the labelled images show up in the image-level ``datasets`` denorm.

    Adding images to a dataset hands OpenSearch an async update_by_query, so the
    write lands some time after the response — asserting immediately is a race
    (same reason ``datasets_add_images_test`` polls).
    """
    deadline = time.monotonic() + timeout
    examples = []
    while time.monotonic() < deadline:
        examples = await DataRoom.classifiers.examples(slug_version, side)
        if len(examples) >= expected_count:
            return examples
        await asyncio.sleep(0.25)
    return examples


@pytest.fixture()
def single_image_type():
    return ensure_single_image_type()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_classifier_round_trip(DataRoom, single_image_type):
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    pos = await DataRoom.datasets.create(name='Pos', slug=f'{slug}-pos', type=SINGLE_IMAGE_TYPE)
    neg = await DataRoom.datasets.create(name='Neg', slug=f'{slug}-neg', type=SINGLE_IMAGE_TYPE)

    classifier = await DataRoom.classifiers.create(
        name='Studio shots',
        slug=slug,
        extra_pos_datasets=[pos['slug_version']],
        extra_neg_datasets=[neg['slug_version']],
        embedding_space='vitb14_reg',
    )
    assert classifier['slug_version'] == f'{slug}/1'
    assert classifier['extra_pos_datasets'] == [pos['slug_version']]
    assert classifier['main_pos_dataset'] == f'{slug}-positives/1'

    assert (await DataRoom.classifiers.get(f'{slug}/1'))['name'] == 'Studio shots'
    listed = await DataRoom.classifiers.list(slug=slug)
    assert [c['slug_version'] for c in listed] == [f'{slug}/1']

    await DataRoom.classifiers.update(f'{slug}/1', description='Lit on white.')
    assert (await DataRoom.classifiers.get(f'{slug}/1'))['description'] == 'Lit on white.'

    await DataRoom.classifiers.lock(f'{slug}/1')
    assert (await DataRoom.classifiers.get(f'{slug}/1'))['is_frozen'] is True
    second = await DataRoom.classifiers.new_version(f'{slug}/1')
    assert second['slug_version'] == f'{slug}/2'
    assert second['is_frozen'] is False
    await DataRoom.classifiers.unlock(f'{slug}/1')

    # Deleting one version leaves the others alone.
    await DataRoom.classifiers.delete(f'{slug}/1')
    assert [c['slug_version'] for c in await DataRoom.classifiers.list(slug=slug)] == [f'{slug}/2']
    await DataRoom.classifiers.delete(f'{slug}/2')
    assert await DataRoom.classifiers.list(slug=slug) == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_add_examples_labels_images(DataRoom, single_image_type, image_logo, image_girl):
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    await DataRoom.classifiers.create(name='Studio', slug=slug)

    result = await DataRoom.classifiers.add_examples(f'{slug}/1', 'pos', [image_logo.id, image_girl.id])
    assert result == {'added': 2, 'removed': 0}
    assert (await DataRoom.classifiers.get(f'{slug}/1'))['counts']['pos'] == 2

    examples = await _wait_for_examples(DataRoom, f'{slug}/1', 'pos', 2)
    assert sorted(image['id'] for image in examples) == sorted([image_logo.id, image_girl.id])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_makes_the_owned_datasets(DataRoom, single_image_type):
    """A bare create is a usable classifier: it owns a bucket per side."""
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    classifier = await DataRoom.classifiers.create(name='Studio', slug=slug)
    assert classifier['main_pos_dataset'] == f'{slug}-positives/1'
    assert classifier['main_neg_dataset'] == f'{slug}-negatives/1'


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_examples_span_owned_and_borrowed_sets(DataRoom, single_image_type, image_logo, image_girl):
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    extra = await DataRoom.datasets.create(name='Extra', slug=f'{slug}-extra', type=SINGLE_IMAGE_TYPE)
    await DataRoom.datasets.add_images(extra['slug_version'], [image_girl.id])
    await DataRoom.classifiers.create(name='Studio', slug=slug, extra_pos_datasets=[extra['slug_version']])
    await DataRoom.classifiers.add_examples(f'{slug}/1', 'pos', [image_logo.id])

    counts = (await DataRoom.classifiers.get(f'{slug}/1'))['counts']
    assert counts['main_pos'] == 1
    assert counts['extra_pos'] == 1
    examples = await _wait_for_examples(DataRoom, f'{slug}/1', 'pos', 2)
    assert sorted(image['id'] for image in examples) == sorted([image_logo.id, image_girl.id])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_service_reports_a_training_and_an_apply_run(DataRoom, single_image_type, image_logo, image_girl):
    """The service's side of the loop through the client: training, run, scores."""
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    await DataRoom.classifiers.create(name='Studio', slug=slug)
    classifier = await sync_to_async(Classifier.objects.get)(slug_version=f'{slug}/1')
    training = await sync_to_async(ClassifierTraining.objects.create)(classifier=classifier, n_pos=2, n_neg=2)

    trained = await DataRoom.classifiers.report_training(
        f'{slug}/1',
        str(training.id),
        status='trained',
        model_id='abc123',
        metrics={'val_auc': 0.97},
        code_version='query-head-1',
        labels_version=f'vitb14_reg:{slug}-negatives/1,{slug}-positives/1',
    )
    assert trained['status'] == 'trained'
    assert trained['model_id'] == 'abc123'
    assert trained['metrics']['val_auc'] == 0.97
    # the service's view of what it ran, kept for Dataroom's staleness checks
    assert trained['code_version'] == 'query-head-1'
    assert trained['labels_version'] == f'vitb14_reg:{slug}-negatives/1,{slug}-positives/1'

    run = await sync_to_async(ClassifierApplyRun.objects.create)(
        classifier=classifier, training=training, target_type='dataset', target_value=f'{slug}-positives/1'
    )
    running = await DataRoom.classifiers.report_run(f'{slug}/1', str(run.id), status='running', total=2)
    assert (running['status'], running['total']) == ('running', 2)

    written = await DataRoom.classifiers.add_scores(
        f'{slug}/1', {image_logo.id: 0.91, image_girl.id: 0.12, 'gone': 0.5}, run_id=str(run.id)
    )
    assert written == {'written': 2, 'missing': ['gone']}
    scored = await DataRoom.images.get(image_logo.id, fields=['classifications'])
    assert scored['classifications'] == {f'{slug}/1': 0.91}

    completed = await DataRoom.classifiers.report_run(f'{slug}/1', str(run.id), status='completed', processed=2)
    assert (completed['status'], completed['processed']) == ('completed', 2)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_add_scores_splits_into_server_sized_chunks(DataRoom, single_image_type, image_logo, image_girl, mocker):
    """A run scores more images than the endpoint takes in one call."""
    mocker.patch('dataroom_client.resources.classifiers.SCORES_CHUNK', 1)
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    await DataRoom.classifiers.create(name='Studio', slug=slug)

    written = await DataRoom.classifiers.add_scores(f'{slug}/1', {image_logo.id: 0.91, image_girl.id: 0.12})
    assert written == {'written': 2, 'missing': []}
    for image_id, expected in ((image_logo.id, 0.91), (image_girl.id, 0.12)):
        scored = await DataRoom.images.get(image_id, fields=['classifications'])
        assert scored['classifications'] == {f'{slug}/1': expected}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_report_run_leaves_out_what_it_is_not_told(DataRoom, single_image_type):
    """A mid-run report carries the total alone; the status stays where it was."""
    slug = f'clf-{uuid.uuid4().hex[:6]}'
    await DataRoom.classifiers.create(name='Studio', slug=slug)
    classifier = await sync_to_async(Classifier.objects.get)(slug_version=f'{slug}/1')
    training = await sync_to_async(ClassifierTraining.objects.create)(classifier=classifier)
    run = await sync_to_async(ClassifierApplyRun.objects.create)(
        classifier=classifier, training=training, target_type='dataset', target_value=f'{slug}-positives/1'
    )

    reported = await DataRoom.classifiers.report_run(f'{slug}/1', str(run.id), total=7)
    assert reported['total'] == 7
    assert reported['status'] == 'launched'
