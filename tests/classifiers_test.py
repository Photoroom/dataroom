"""/api/classifiers/ — versioned classifier definitions.

A classifier records *which datasets hold its examples*, nothing more: no model,
no training, no scores. Each one owns a main positive and negative dataset,
created with it and hidden from the datasets list, and may borrow extra ones
that somebody else curates.
"""

import pytest
import requests

from backend.dataroom.datasets.single_image import ensure_single_image_type
from backend.dataroom.models.classifier import Classifier
from backend.dataroom.models.dataset import Dataset
from backend.dataroom.models.group import GroupType


@pytest.fixture()
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture()
def headers(token):
    return {'Authorization': f'Token {token.key}'}


@pytest.fixture()
def single_image_type():
    return ensure_single_image_type()


@pytest.fixture()
def pos_dataset(single_image_type):
    return Dataset.objects.create(slug='studio-pos', name='Studio positives', type=single_image_type)


@pytest.fixture()
def neg_dataset(single_image_type):
    return Dataset.objects.create(slug='studio-neg', name='Studio negatives', type=single_image_type)


def _create(api_url, headers, **overrides):
    payload = {'slug': 'studio-shots', 'name': 'Studio shots', **overrides}
    return requests.post(f'{api_url}/classifiers/', json=payload, headers=headers)


def test_create_makes_the_two_owned_datasets(api_url, headers, single_image_type):
    """A bare create is a usable classifier: it owns a bucket per side."""
    response = _create(api_url, headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['main_pos_dataset'] == 'studio-shots-positives/1'
    assert data['main_neg_dataset'] == 'studio-shots-negatives/1'
    assert data['extra_pos_datasets'] == []
    assert data['counts']['pos'] == 0
    assert Dataset.objects.get(slug='studio-shots-positives').type_id == single_image_type.name


def test_owned_datasets_are_internal_and_hidden_from_the_list(api_url, headers):
    """Forty datasets nobody curates directly is noise; they belong to the
    classifier and are edited through it."""
    _create(api_url, headers).raise_for_status()

    assert Dataset.objects.get(slug='studio-shots-positives').is_internal is True
    listed = requests.get(f'{api_url}/datasets/?search=studio-shots', headers=headers).json()['results']
    assert listed == []
    # Asked for explicitly, they show up — and are always retrievable by id, so
    # links from the classifier resolve.
    listed = requests.get(f'{api_url}/datasets/?search=studio-shots&include_internal=true', headers=headers).json()
    assert {d['slug'] for d in listed['results']} == {'studio-shots-positives', 'studio-shots-negatives'}
    assert requests.get(f'{api_url}/datasets/studio-shots-positives/1/', headers=headers).status_code == 200


def test_extra_datasets_are_borrowed_by_slug_version(api_url, headers, pos_dataset, neg_dataset):
    response = _create(
        api_url,
        headers,
        extra_pos_datasets=[pos_dataset.slug_version],
        extra_neg_datasets=[neg_dataset.slug_version],
        embedding_space='vitb14_reg',
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['extra_pos_datasets'] == [pos_dataset.slug_version]
    assert data['extra_neg_datasets'] == [neg_dataset.slug_version]
    assert data['embedding_space'] == 'vitb14_reg'


def test_counts_split_main_from_extra(api_url, headers, pos_dataset, image_logo, image_girl):
    requests.post(
        f'{api_url}/datasets/{pos_dataset.slug_version}/images/',
        json={'image_ids': [image_logo.id]},
        headers=headers,
    ).raise_for_status()
    created = _create(api_url, headers, extra_pos_datasets=[pos_dataset.slug_version]).json()
    requests.post(
        f'{api_url}/datasets/{created["main_pos_dataset"]}/images/',
        json={'image_ids': [image_girl.id]},
        headers=headers,
    ).raise_for_status()

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert counts['main_pos'] == 1
    assert counts['extra_pos'] == 1
    assert counts['pos'] == 2


def test_an_owned_dataset_cannot_be_borrowed_as_an_extra(api_url, headers):
    _create(api_url, headers).raise_for_status()
    response = requests.post(
        f'{api_url}/classifiers/',
        json={'slug': 'other', 'name': 'Other', 'extra_pos_datasets': ['studio-shots-positives/1']},
        headers=headers,
    )
    assert response.status_code == 400
    assert 'belongs to a classifier' in response.text


def test_extra_sets_must_be_single_image_datasets(api_url, headers):
    other_type = GroupType.objects.create(name='photoshoot', description='A shoot of several images.')
    dataset = Dataset.objects.create(slug='shoots', name='Shoots', type=other_type)
    response = _create(api_url, headers, extra_pos_datasets=[dataset.slug_version])
    assert response.status_code == 400
    assert 'single_image' in response.text


def test_a_dataset_cannot_be_positive_and_negative(api_url, headers, pos_dataset):
    response = _create(
        api_url, headers, extra_pos_datasets=[pos_dataset.slug_version], extra_neg_datasets=[pos_dataset.slug_version]
    )
    assert response.status_code == 400
    assert 'both a positive and a negative' in response.text


def test_reusing_a_slug_is_refused_and_points_at_new_version(api_url, headers):
    """Creating over an existing slug used to make a version that SHARED the
    first one's example datasets — so locking either one froze the other's."""
    _create(api_url, headers).raise_for_status()
    second = _create(api_url, headers)
    assert second.status_code == 400, second.text
    assert 'new-version' in second.text
    assert Classifier.objects.filter(slug='studio-shots').count() == 1


def test_update_attaches_extra_datasets(api_url, headers, pos_dataset):
    _create(api_url, headers).raise_for_status()
    response = requests.patch(
        f'{api_url}/classifiers/studio-shots/1/',
        json={'extra_pos_datasets': [pos_dataset.slug_version]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()['extra_pos_datasets'] == [pos_dataset.slug_version]


def test_locking_freezes_the_owned_datasets_only(api_url, headers, image_logo, pos_dataset):
    """A lock has to reach the classifier's own datasets, or labelling would
    keep changing what the locked version means — but not a borrowed one, which
    belongs to whoever curates it."""
    created = _create(api_url, headers, extra_pos_datasets=[pos_dataset.slug_version]).json()
    requests.post(f'{api_url}/classifiers/studio-shots/1/lock/', headers=headers).raise_for_status()

    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['is_frozen'] is True
    assert requests.get(f'{api_url}/datasets/{created["main_pos_dataset"]}/', headers=headers).json()['is_frozen']
    assert not requests.get(f'{api_url}/datasets/{pos_dataset.slug_version}/', headers=headers).json()['is_frozen']

    response = requests.post(
        f'{api_url}/datasets/{created["main_pos_dataset"]}/images/',
        json={'image_ids': [image_logo.id]},
        headers=headers,
    )
    assert response.status_code == 400
    assert 'frozen' in response.text

    response = requests.patch(f'{api_url}/classifiers/studio-shots/1/', json={'name': 'Nope'}, headers=headers)
    assert response.status_code == 400
    assert 'new-version' in response.text


def test_unlock_reopens_both(api_url, headers):
    created = _create(api_url, headers).json()
    requests.post(f'{api_url}/classifiers/studio-shots/1/lock/', headers=headers).raise_for_status()
    requests.post(f'{api_url}/classifiers/studio-shots/1/unlock/', headers=headers).raise_for_status()

    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['is_frozen'] is False
    assert not requests.get(f'{api_url}/datasets/{created["main_pos_dataset"]}/', headers=headers).json()['is_frozen']


def test_new_version_copies_the_owned_sets_and_references_the_extras(
    api_url, headers, image_logo, image_girl, pos_dataset
):
    created = _create(api_url, headers, extra_pos_datasets=[pos_dataset.slug_version]).json()
    requests.post(
        f'{api_url}/datasets/{created["main_pos_dataset"]}/images/',
        json={'image_ids': [image_logo.id]},
        headers=headers,
    ).raise_for_status()
    requests.post(f'{api_url}/classifiers/studio-shots/1/lock/', headers=headers).raise_for_status()

    response = requests.post(f'{api_url}/classifiers/studio-shots/1/new-version/', headers=headers)
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['slug_version'] == 'studio-shots/2'
    # Its own copy of the owned set, carrying the images over...
    assert second['main_pos_dataset'] == 'studio-shots-positives/2'
    assert second['counts']['main_pos'] == 1
    # ...and the borrowed one referenced, not duplicated.
    assert second['extra_pos_datasets'] == [pos_dataset.slug_version]
    assert Dataset.objects.filter(slug=pos_dataset.slug).count() == 1

    # Labelling the new version leaves the locked one exactly as it was.
    requests.post(
        f'{api_url}/datasets/studio-shots-positives/2/images/',
        json={'image_ids': [image_girl.id]},
        headers=headers,
    ).raise_for_status()
    assert requests.get(f'{api_url}/classifiers/studio-shots/2/', headers=headers).json()['counts']['main_pos'] == 2
    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']['main_pos'] == 1


def test_new_version_can_start_from_empty_examples(api_url, headers, image_logo, pos_dataset):
    """Relabelling from scratch, without losing the classifier's history."""
    created = _create(api_url, headers, extra_pos_datasets=[pos_dataset.slug_version]).json()
    requests.post(
        f'{api_url}/datasets/{created["main_pos_dataset"]}/images/',
        json={'image_ids': [image_logo.id]},
        headers=headers,
    ).raise_for_status()

    response = requests.post(
        f'{api_url}/classifiers/studio-shots/1/new-version/', json={'copy_examples': False}, headers=headers
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['main_pos_dataset'] == 'studio-shots-positives/2'
    assert second['counts']['main_pos'] == 0
    # Borrowed sets are references, so they come along either way.
    assert second['extra_pos_datasets'] == [pos_dataset.slug_version]
    # ...and the source is untouched.
    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']['main_pos'] == 1


def test_new_version_drops_the_extra_datasets_not_named(api_url, headers, pos_dataset, neg_dataset):
    """Carrying a borrowed set over is a choice per dataset: a new version often
    exists precisely to stop training on one of them."""
    _create(
        api_url,
        headers,
        extra_pos_datasets=[pos_dataset.slug_version],
        extra_neg_datasets=[neg_dataset.slug_version],
    ).raise_for_status()

    response = requests.post(
        f'{api_url}/classifiers/studio-shots/1/new-version/',
        json={'extra_pos_datasets': [], 'extra_neg_datasets': [neg_dataset.slug_version]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['extra_pos_datasets'] == []
    assert second['extra_neg_datasets'] == [neg_dataset.slug_version]
    # The source keeps what it had, and nobody's dataset was deleted.
    first = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()
    assert first['extra_pos_datasets'] == [pos_dataset.slug_version]
    assert Dataset.objects.filter(slug=pos_dataset.slug).exists()


def test_new_version_refuses_extras_the_source_does_not_have(api_url, headers, pos_dataset):
    """Naming a dataset here means 'keep this one', so an unknown one is a
    mistake rather than a quiet attach."""
    _create(api_url, headers).raise_for_status()
    response = requests.post(
        f'{api_url}/classifiers/studio-shots/1/new-version/',
        json={'extra_pos_datasets': [pos_dataset.slug_version]},
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert 'is not an additional dataset' in response.text


def test_new_version_takes_a_note_of_its_own(api_url, headers):
    """The description says what the classifier is; the note says what this
    version is, and does not follow into the next one."""
    _create(api_url, headers).raise_for_status()
    second = requests.post(
        f'{api_url}/classifiers/studio-shots/1/new-version/',
        json={'version_note': 'relabelling the hard negatives'},
        headers=headers,
    ).json()
    assert second['version_note'] == 'relabelling the hard negatives'
    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['version_note'] == ''

    third = requests.post(f'{api_url}/classifiers/studio-shots/2/new-version/', headers=headers).json()
    assert third['version_note'] == ''


def test_the_note_stays_editable_on_a_locked_version(api_url, headers):
    """A lock protects what the version trains on. What it was FOR is usually
    only clear once it is finished, so the note is exempt — everything else on
    a locked version is still refused."""
    _create(api_url, headers).raise_for_status()
    requests.post(f'{api_url}/classifiers/studio-shots/1/lock/', headers=headers).raise_for_status()

    response = requests.patch(
        f'{api_url}/classifiers/studio-shots/1/', json={'version_note': 'our baseline'}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()['version_note'] == 'our baseline'

    refused = requests.patch(f'{api_url}/classifiers/studio-shots/1/', json={'name': 'Nope'}, headers=headers)
    assert refused.status_code == 400
    assert 'new-version' in refused.text


def _label(api_url, headers, image_ids, side, slug_version='studio-shots/1'):
    return requests.post(
        f'{api_url}/classifiers/{slug_version}/label/',
        json={'image_ids': image_ids, 'side': side},
        headers=headers,
    )


def test_labelling_the_other_way_moves_the_image_rather_than_copying_it(api_url, headers, image_logo):
    """One image, one side. Adding to each dataset independently used to leave
    the image in both, so training saw it as an example and a counter-example."""
    _create(api_url, headers).raise_for_status()
    assert _label(api_url, headers, [image_logo.id], 'positive').json() == {'added': 1, 'removed': 0}

    response = _label(api_url, headers, [image_logo.id], 'negative')
    assert response.status_code == 200, response.text
    assert response.json() == {'added': 1, 'removed': 1}

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['main_pos'], counts['main_neg']) == (0, 1)


def test_labelling_none_takes_the_image_off_both_sides(api_url, headers, image_logo):
    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()

    assert _label(api_url, headers, [image_logo.id], 'none').json() == {'added': 0, 'removed': 1}
    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['main_pos'], counts['main_neg']) == (0, 0)


def test_relabelling_the_same_side_changes_nothing(api_url, headers, image_logo):
    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()

    assert _label(api_url, headers, [image_logo.id], 'positive').json() == {'added': 0, 'removed': 0}
    assert requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']['main_pos'] == 1


def test_labelling_leaves_a_borrowed_dataset_alone(api_url, headers, image_logo, pos_dataset):
    """The extras belong to whoever curates them: labelling here must not reach
    into someone else's dataset to take an image out of it."""
    requests.post(
        f'{api_url}/datasets/{pos_dataset.slug_version}/images/',
        json={'image_ids': [image_logo.id]},
        headers=headers,
    ).raise_for_status()
    _create(api_url, headers, extra_pos_datasets=[pos_dataset.slug_version]).raise_for_status()

    _label(api_url, headers, [image_logo.id], 'negative').raise_for_status()

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['extra_pos'], counts['main_neg']) == (1, 1)
    members = requests.get(f'{api_url}/datasets/{pos_dataset.slug_version}/groups/', headers=headers).json()
    assert len(members['results']) == 1


def test_a_held_out_image_that_lost_its_side_is_counted_as_an_orphan(api_url, headers, image_logo):
    """Held out, but no longer an example of either side: training and its
    metrics both skip it, so it is neither trained on nor measured on. That is
    what taking an image out of a side dataset directly leaves behind —
    labelling it ``none`` here takes it off the held-out set as well — and
    without a count of its own it is simply missing."""
    from backend.api.classifiers.serializers import ensure_val_dataset
    from backend.dataroom.datasets.single_image import add_images_to_dataset, remove_images_from_dataset

    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()
    classifier = Classifier.objects.get(slug_version='studio-shots/1')
    add_images_to_dataset(ensure_val_dataset(classifier, classifier.author), [image_logo.id])

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['val_pos'], counts['val_orphan']) == (1, 0)

    # Straight out of the side dataset, which the classifier's own label action
    # would never do on its own.
    remove_images_from_dataset(classifier.main_pos_dataset, [image_logo.id])

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['val_pos'], counts['val_neg'], counts['val_orphan']) == (0, 0, 1)


def test_labelling_none_takes_the_image_off_the_held_out_set_too(api_url, headers, image_logo):
    """The counterpart: an image that is no longer an example of either side
    cannot be a held-out example of one, so the label action clears it."""
    from backend.api.classifiers.serializers import ensure_val_dataset
    from backend.dataroom.datasets.single_image import add_images_to_dataset

    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()
    classifier = Classifier.objects.get(slug_version='studio-shots/1')
    add_images_to_dataset(ensure_val_dataset(classifier, classifier.author), [image_logo.id])

    _label(api_url, headers, [image_logo.id], 'none').raise_for_status()

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['val_pos'], counts['val_neg'], counts['val_orphan']) == (0, 0, 0)


def test_switching_a_held_out_image_to_the_other_side_keeps_it_held_out(api_url, headers, image_logo):
    """Which side a held-out image is on comes from the side dataset it is
    still a member of, so flipping its label moves it across the held-out set
    rather than dropping it out of one."""
    from backend.api.classifiers.serializers import ensure_val_dataset
    from backend.dataroom.datasets.single_image import add_images_to_dataset

    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()
    classifier = Classifier.objects.get(slug_version='studio-shots/1')
    add_images_to_dataset(ensure_val_dataset(classifier, classifier.author), [image_logo.id])

    _label(api_url, headers, [image_logo.id], 'negative').raise_for_status()

    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['val_pos'], counts['val_neg'], counts['val_orphan']) == (0, 1, 0)


def test_labelling_a_locked_version_is_refused(api_url, headers, image_logo):
    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()
    requests.post(f'{api_url}/classifiers/studio-shots/1/lock/', headers=headers).raise_for_status()

    response = _label(api_url, headers, [image_logo.id], 'negative')
    assert response.status_code == 400
    assert 'locked' in response.text
    # Refused whole: the image is still positive, not off both sides.
    counts = requests.get(f'{api_url}/classifiers/studio-shots/1/', headers=headers).json()['counts']
    assert (counts['main_pos'], counts['main_neg']) == (1, 0)


def test_labelling_updates_the_image_datasets_denorm(api_url, headers, image_logo):
    """The annotate UI reads an image's side off this denorm, so a move has to
    drop the old dataset from it — not just add the new one."""
    _create(api_url, headers).raise_for_status()
    _label(api_url, headers, [image_logo.id], 'positive').raise_for_status()
    _label(api_url, headers, [image_logo.id], 'negative').raise_for_status()

    image = requests.get(f'{api_url}/images/{image_logo.id}/', headers=headers).json()
    assert 'studio-shots-negatives/1' in image['datasets']
    assert 'studio-shots-positives/1' not in image['datasets']


def test_name_prefix_narrows_the_list(api_url, headers):
    """search matches anywhere; a prefix narrows to one family of names."""
    _create(api_url, headers).raise_for_status()
    requests.post(
        f'{api_url}/classifiers/', json={'slug': 'outdoor-shots', 'name': 'Outdoor shots'}, headers=headers
    ).raise_for_status()

    results = requests.get(f'{api_url}/classifiers/?name__prefix=stu', headers=headers).json()['results']
    assert [c['slug'] for c in results] == ['studio-shots']
    # 'shots' is in both names but starts neither.
    assert requests.get(f'{api_url}/classifiers/?name__prefix=shots', headers=headers).json()['results'] == []


def test_delete_removes_the_version_only(api_url, headers):
    _create(api_url, headers).raise_for_status()
    requests.post(f'{api_url}/classifiers/studio-shots/1/new-version/', headers=headers).raise_for_status()
    assert requests.delete(f'{api_url}/classifiers/studio-shots/2/', headers=headers).status_code == 204
    assert Classifier.objects.filter(slug='studio-shots').count() == 1


def test_search_and_filter(api_url, headers):
    _create(api_url, headers).raise_for_status()
    requests.post(
        f'{api_url}/classifiers/', json={'slug': 'outdoor-shots', 'name': 'Outdoor shots'}, headers=headers
    ).raise_for_status()

    results = requests.get(f'{api_url}/classifiers/?search=outdoor', headers=headers).json()['results']
    assert [c['slug'] for c in results] == ['outdoor-shots']

    requests.post(f'{api_url}/classifiers/outdoor-shots/1/lock/', headers=headers).raise_for_status()
    results = requests.get(f'{api_url}/classifiers/?is_frozen=true', headers=headers).json()['results']
    assert [c['slug'] for c in results] == ['outdoor-shots']
