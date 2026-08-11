"""POST /datasets/{slug}/{version}/images/ — add loose images to a
single_image dataset. Each image is wrapped in its single_image group; the
image-level ``datasets`` denorm is then derived from that two-hop relation.
"""

import time

import pytest
import requests

from backend.dataroom.management.commands.reconcile_datasets import reconcile_dataset
from backend.dataroom.models.group import Group, Membership
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.dataset import Dataset
from backend.dataroom.opensearch import OS
from backend.dataroom.datasets.single_image import SINGLE_IMAGE_TYPE, ensure_single_image_type


@pytest.fixture()
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture()
def headers(token):
    return {'Authorization': f'Token {token.key}'}


def _create_image(image_id: str):
    image = OSImage(
        id=image_id,
        author='tester',
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
    OS.client.indices.refresh(index=OSImage.INDEX)
    return image


def _image_datasets(image_id):
    OS.client.indices.refresh(index=OSImage.INDEX)
    hit = OSImage.objects.search().filter('term', id=image_id).execute().hits[0].to_dict()
    return sorted(hit.get('datasets', []))


def _wait_for_image_datasets(image_id, expected, timeout=15.0):
    """Poll until ``expected`` shows up in the image's datasets denorm.

    The add-images path hands OpenSearch an async update_by_query, so the write lands
    some time after the response. Asserting immediately is a race.
    """
    deadline = time.monotonic() + timeout
    datasets = _image_datasets(image_id)
    while expected not in datasets and time.monotonic() < deadline:
        time.sleep(0.25)
        datasets = _image_datasets(image_id)
    return datasets


def _single_image_dataset(api_url, headers, slug='photos'):
    ensure_single_image_type()
    resp = requests.post(
        f'{api_url}/datasets/',
        json={'name': slug, 'slug': slug, 'type': SINGLE_IMAGE_TYPE},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()['slug_version']


@pytest.fixture()
def counted_writes(monkeypatch):
    """Count the image documents sent to OpenSearch by the denorm writes.

    A scripted update rewrites the whole document and has to load its _source to even
    evaluate the script, so a write that no-ops still costs a read - a per-document S3
    fetch where the vectors live on s3vector. These tests therefore assert the ABSENCE
    of writes, which nothing else in the suite can see.
    """
    from backend.dataroom.datasets import os_sync

    sent = []
    real = os_sync.bulk_update_by_id

    def counting(ops):
        sent.append(len(ops))
        return real(ops)

    # Every denorm write resolves this name out of the os_sync module globals at call
    # time, so patching it here catches all of them.
    monkeypatch.setattr(os_sync, 'bulk_update_by_id', counting)
    return sent


@pytest.mark.django_db(transaction=True)
def test_re_adding_the_same_images_writes_nothing_to_opensearch(api_url, headers, counted_writes):
    """Adding images is idempotent, so re-adding is a normal thing to do. It used to
    issue a scripted update per image, all of which no-op'd - but a no-op still forces
    OpenSearch to load the document. Nothing changed in Postgres, so nothing may be sent."""
    _create_image('re_img1')
    _create_image('re_img2')
    sv = _single_image_dataset(api_url, headers, slug='rephotos')
    body = {'image_ids': ['re_img1', 're_img2']}

    first = requests.post(f'{api_url}/datasets/{sv}/images/', json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()['updated_count'] == 2
    assert sum(counted_writes) == 2, 'the first add must write both images'

    counted_writes.clear()
    again = requests.post(f'{api_url}/datasets/{sv}/images/', json=body, headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()['updated_count'] == 0
    assert counted_writes == [], f'a no-op re-add must not touch OpenSearch, sent {counted_writes}'

    # ...and the denorm is still right, i.e. we skipped the write without losing the value.
    assert sv in _image_datasets('re_img1')
    assert sv in _image_datasets('re_img2')


@pytest.mark.django_db(transaction=True)
def test_adding_one_new_image_writes_only_that_image(api_url, headers, counted_writes):
    """A partial overlap writes only the images that actually changed."""
    for i in range(3):
        _create_image(f'part_img{i}')
    sv = _single_image_dataset(api_url, headers, slug='partphotos')

    requests.post(f'{api_url}/datasets/{sv}/images/', json={'image_ids': ['part_img0', 'part_img1']}, headers=headers)
    counted_writes.clear()

    # Two of these three are already members; only the new one may be written.
    resp = requests.post(
        f'{api_url}/datasets/{sv}/images/',
        json={'image_ids': ['part_img0', 'part_img1', 'part_img2']},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['updated_count'] == 1
    assert sum(counted_writes) == 1, f'only the new image may be written, sent {counted_writes}'
    assert sv in _image_datasets('part_img2')


@pytest.mark.django_db(transaction=True)
def test_add_images_wraps_in_groups_and_syncs_denorm(api_url, headers):
    _create_image('add_img1')
    _create_image('add_img2')
    sv = _single_image_dataset(api_url, headers)

    resp = requests.post(
        f'{api_url}/datasets/{sv}/images/',
        json={'image_ids': ['add_img1', 'add_img2']},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['updated_count'] == 2

    # one single_image group per image, added to the dataset
    assert Group.objects.filter(name='add_img1', type_id=SINGLE_IMAGE_TYPE).exists()
    assert requests.get(f'{api_url}/datasets/{sv}/', headers=headers).json()['group_count'] == 2

    # the derived image-level denorm now carries the dataset (written asynchronously)
    assert sv in _wait_for_image_datasets('add_img1', sv)
    assert sv in _wait_for_image_datasets('add_img2', sv)


@pytest.mark.django_db(transaction=True)
def test_add_images_is_idempotent(api_url, headers):
    _create_image('add_img3')
    sv = _single_image_dataset(api_url, headers)
    body = {'image_ids': ['add_img3']}

    assert (
        requests.post(f'{api_url}/datasets/{sv}/images/', json=body, headers=headers).json()['updated_count'] == 1
    )
    # re-adding the same image is a no-op (group reused, membership already active)
    assert (
        requests.post(f'{api_url}/datasets/{sv}/images/', json=body, headers=headers).json()['updated_count'] == 0
    )
    assert Membership.objects.filter(image_id='add_img3', role=SINGLE_IMAGE_TYPE).count() == 1


@pytest.mark.django_db(transaction=True)
def test_add_images_rejects_non_single_image_dataset(api_url, headers, seed_group_types):
    _create_image('add_img4')
    resp = requests.post(
        f'{api_url}/datasets/',
        json={'name': 'Products', 'slug': 'products', 'type': 'zara_product'},
        headers=headers,
    )
    sv = resp.json()['slug_version']

    resp = requests.post(
        f'{api_url}/datasets/{sv}/images/',
        json={'image_ids': ['add_img4']},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.django_db(transaction=True)
def test_add_images_rejects_when_frozen(api_url, headers):
    _create_image('add_img5')
    sv = _single_image_dataset(api_url, headers)
    requests.post(f'{api_url}/datasets/{sv}/freeze/', headers=headers)

    resp = requests.post(
        f'{api_url}/datasets/{sv}/images/',
        json={'image_ids': ['add_img5']},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert Dataset.objects.get(slug_version=sv).memberships.count() == 0


@pytest.mark.django_db(transaction=True)
def test_add_images_rejects_empty(api_url, headers):
    sv = _single_image_dataset(api_url, headers)
    resp = requests.post(f'{api_url}/datasets/{sv}/images/', json={'image_ids': []}, headers=headers)
    assert resp.status_code == 400, resp.text


@pytest.mark.django_db(transaction=True)
def test_add_images_marks_rows_synced_because_it_waited(api_url, headers):
    """The OS write is a bulk update addressed by _id and we wait for it, so the rows
    can honestly claim to be synced. It used to be fire-and-forget, which meant nobody
    could claim the write landed and the reconciler had to re-write every doc to say so.
    """
    slug_version = _single_image_dataset(api_url, headers)
    image_id = 'synced_img'
    _create_image(image_id)

    resp = requests.post(f'{api_url}/datasets/{slug_version}/images/', json={'image_ids': [image_id]}, headers=headers)
    assert resp.status_code == 200, resp.text

    dataset = Dataset.objects.get(slug_version=slug_version)
    assert dataset.memberships.filter(os_synced=False).count() == 0
    assert Membership.objects.filter(image_id=image_id, os_synced=False).count() == 0

    # And the denorm is already there: no waiting on the reconciler.
    assert slug_version in _wait_for_image_datasets(image_id, slug_version)

    # The reconciler therefore has nothing to do.
    assert reconcile_dataset(dataset.id) == 0


@pytest.mark.django_db(transaction=True)
def test_add_images_refuses_an_image_id_squatted_by_another_group_type(api_url, headers, seed_group_types):
    """Group names are unique among active groups regardless of type. If a group of
    another type already owns the image id, wrapping it would smuggle a wrong-typed
    group into the dataset: refuse with a 400 rather than corrupt the dataset."""
    slug_version = _single_image_dataset(api_url, headers)
    image_id = 'squatted_img'
    _create_image(image_id)
    Group.objects.create(name=image_id, type_id='zara_product')

    resp = requests.post(f'{api_url}/datasets/{slug_version}/images/', json={'image_ids': [image_id]}, headers=headers)
    assert resp.status_code == 400, resp.text
    assert 'another type' in resp.text

    dataset = Dataset.objects.get(slug_version=slug_version)
    assert dataset.memberships.filter(deleted_at__isnull=True).count() == 0
