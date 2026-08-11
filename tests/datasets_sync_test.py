"""OS-denorm sync for datasets.

``OSImage.datasets`` is a flattened cache of the two-hop relation
``Dataset -> Group -> image``. These tests assert it stays correct for both
triggers (dataset<->group and group<->image), via the inline API path and via
the reconcilers (the failure backstop).
"""

import threading

import pytest
import requests

from backend.dataroom.datasets import os_sync
from backend.dataroom.groups.os_sync import add_membership_to_image
from backend.dataroom.management.commands.reconcile_memberships import reconcile_group
from backend.dataroom.management.commands.reconcile_datasets import reconcile_dataset
from backend.dataroom.models.group import Group, Membership
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.dataset import Dataset, DatasetMembership
from backend.dataroom.opensearch import OS


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


def _add_member_raw(group, image_id, role='onhang'):
    """Put an image in a group via ORM + group denorm only — NO dataset recompute.
    Leaves Membership.os_synced=False, simulating the pre-sync / failed-sync state
    so the reconciler path can be exercised."""
    Membership.objects.create(group=group, image_id=image_id, role=role)
    add_membership_to_image(image_id=image_id, group_id=group.os_encoded_id, role=role)
    OS.client.indices.refresh(index=OSImage.INDEX)


def _image_datasets(image_id):
    OS.client.indices.refresh(index=OSImage.INDEX)
    hit = OSImage.objects.search().filter('term', id=image_id).execute().hits[0].to_dict()
    return sorted(hit.get('datasets', []))


def _put_members(api_url, headers, group, image_ids, role='onhang'):
    return requests.put(
        f'{api_url}/groups/{group.id}/',
        json={'metadata': {}, 'members': [{'image_id': i, 'role': role} for i in image_ids]},
        headers=headers,
    )


# -------------------- dataset <-> group trigger (inline) --------------------
@pytest.mark.django_db(transaction=True)
def test_re_adding_a_member_group_writes_nothing_to_opensearch(api_url, headers, monkeypatch):
    """Re-adding a group that is already a member changes nothing in Postgres, so it must
    not touch OpenSearch either. It used to recompute every one of the group's images -
    all no-ops, but a no-op still makes OpenSearch load the whole document to evaluate the
    script (an S3 read per doc where the vectors live on s3vector)."""
    img = _create_image('noop_img1')
    g = Group.objects.create(name='noop_g', type_id='zara_product')
    assert _put_members(api_url, headers, g, [img.id]).status_code == 200
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')

    sent = []
    real = os_sync.bulk_update_by_id
    monkeypatch.setattr(os_sync, 'bulk_update_by_id', lambda ops: (sent.append(len(ops)), real(ops))[1])

    resp = requests.post(f'{api_url}/datasets/{ds.slug_version}/groups/', json={'group_ids': [str(g.id)]},
                         headers=headers)
    assert resp.status_code == 200, resp.text
    assert sum(sent) == 1, 'the first add writes the image'
    assert _image_datasets(img.id) == ['p/1']

    sent.clear()
    again = requests.post(f'{api_url}/datasets/{ds.slug_version}/groups/', json={'group_ids': [str(g.id)]},
                          headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()['updated_count'] == 0
    assert sent == [], f'a no-op re-add must not touch OpenSearch, sent {sent}'
    assert _image_datasets(img.id) == ['p/1']  # and the value is still right


@pytest.mark.django_db(transaction=True)
def test_adding_group_to_dataset_syncs_member_images(api_url, headers):
    img = _create_image('sync_img1')
    g = Group.objects.create(name='g', type_id='zara_product')
    assert _put_members(api_url, headers, g, [img.id]).status_code == 200
    assert _image_datasets(img.id) == []  # not in any dataset yet

    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert _image_datasets(img.id) == ['p/1']

    # Removing the group drops the slug_version from its images.
    requests.delete(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert _image_datasets(img.id) == []


@pytest.mark.django_db(transaction=True)
def test_copy_waits_for_the_os_write_and_marks_rows_synced(api_url, headers):
    """copy used to hand OpenSearch a task and return, because an update_by_query over
    the copied groups' images was too slow to block on. A bulk update by _id is ~0.09ms
    per doc, so it waits - and waiting is what lets it mark the rows os_synced."""
    img = _create_image('copy_img1')
    g = Group.objects.create(name='copy_g', type_id='zara_product')
    assert _put_members(api_url, headers, g, [img.id]).status_code == 200

    src = Dataset.objects.create(name='S', slug='src', type_id='zara_product')
    requests.post(f'{api_url}/datasets/{src.slug_version}/groups/', json={'group_ids': [str(g.id)]}, headers=headers)
    assert _image_datasets(img.id) == ['src/1']

    resp = requests.post(
        f'{api_url}/datasets/{src.slug_version}/copy/', json={'name': 'C', 'slug': 'cp'}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    copy = Dataset.objects.get(slug_version=resp.json()['slug_version'])

    assert copy.memberships.filter(deleted_at__isnull=True).count() == 1
    assert copy.memberships.filter(os_synced=False).count() == 0
    assert _image_datasets(img.id) == ['cp/1', 'src/1']

    # Nothing left for the reconciler.
    assert reconcile_dataset(copy.id) == 0


# -------------------- group <-> image trigger (inline) --------------------
@pytest.mark.django_db(transaction=True)
def test_adding_image_to_member_group_syncs_datasets(api_url, headers):
    g = Group.objects.create(name='g', type_id='zara_product')
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )

    img = _create_image('sync_img2')
    # Adding the image to the (already-member) group must derive the dataset.
    assert _put_members(api_url, headers, g, [img.id]).status_code == 200
    assert _image_datasets(img.id) == ['p/1']

    # Removing it from the group drops the dataset again.
    assert _put_members(api_url, headers, g, []).status_code == 200
    assert _image_datasets(img.id) == []


# -------------------- union over multiple datasets --------------------
@pytest.mark.django_db(transaction=True)
def test_image_in_group_in_two_datasets_unions(api_url, headers):
    img = _create_image('sync_img3')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])

    a = Dataset.objects.create(name='A', slug='a', type_id='zara_product')
    b = Dataset.objects.create(name='B', slug='b', type_id='zara_product')
    for ds in (a, b):
        requests.post(
            f'{api_url}/datasets/{ds.slug_version}/groups/',
            json={'group_ids': [str(g.id)]},
            headers=headers,
        )
    assert _image_datasets(img.id) == ['a/1', 'b/1']

    # Dropping from one leaves the other.
    requests.delete(
        f'{api_url}/datasets/{a.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert _image_datasets(img.id) == ['b/1']


# -------------------- group deletion drops datasets --------------------
@pytest.mark.django_db(transaction=True)
def test_deleting_group_drops_datasets(api_url, headers):
    img = _create_image('sync_img4')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert _image_datasets(img.id) == ['p/1']

    assert requests.delete(f'{api_url}/groups/{g.id}/', headers=headers).status_code == 204
    assert _image_datasets(img.id) == []


# -------------------- deleting the dataset itself --------------------
@pytest.mark.django_db(transaction=True)
def test_deleting_dataset_drops_it_from_its_images(api_url, headers):
    """Deleting a dataset must strip its slug_version from every member image.

    The membership rows CASCADE with the dataset, so a plain delete leaves nothing
    behind with os_synced=False - the reconciler would never see it, and the images
    would stay filterable by a dataset that no longer exists.
    """
    img = _create_image('del_img1')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    other = Dataset.objects.create(name='K', slug='keep', type_id='zara_product')
    for d in (ds, other):
        requests.post(f'{api_url}/datasets/{d.slug_version}/groups/', json={'group_ids': [str(g.id)]}, headers=headers)
    assert _image_datasets(img.id) == ['keep/1', 'p/1']

    assert requests.delete(f'{api_url}/datasets/{ds.slug_version}/', headers=headers).status_code == 204

    # Only the deleted dataset is dropped; the group's other dataset survives.
    assert _image_datasets(img.id) == ['keep/1']
    assert not Dataset.objects.filter(slug_version='p/1').exists()
    assert not DatasetMembership.objects.filter(dataset_id=ds.id).exists()


@pytest.mark.django_db(transaction=True)
def test_deleting_a_frozen_dataset_is_allowed_and_still_syncs(api_url, headers):
    """A freeze protects the membership list of a dataset that exists, not the right
    to delete it. The delete still has to strip the denorm."""
    img = _create_image('del_img2')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(f'{api_url}/datasets/{ds.slug_version}/groups/', json={'group_ids': [str(g.id)]}, headers=headers)
    requests.post(f'{api_url}/datasets/{ds.slug_version}/freeze/', headers=headers)

    assert requests.delete(f'{api_url}/datasets/{ds.slug_version}/', headers=headers).status_code == 204
    assert _image_datasets(img.id) == []


@pytest.mark.django_db(transaction=True)
def test_failed_os_write_on_delete_keeps_the_dataset_for_the_reconciler(api_url, headers, monkeypatch):
    """If the OS write fails mid-delete, the dataset must survive with unsynced rows -
    otherwise the desync is unrecoverable (nothing left to reconcile)."""
    img = _create_image('del_img3')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(f'{api_url}/datasets/{ds.slug_version}/groups/', json={'group_ids': [str(g.id)]}, headers=headers)
    assert _image_datasets(img.id) == ['p/1']

    def boom(*args, **kwargs):
        raise RuntimeError('OpenSearch is down')

    monkeypatch.setattr('backend.api.datasets.views.recompute_datasets_for_groups', boom)
    assert requests.delete(f'{api_url}/datasets/{ds.slug_version}/', headers=headers).status_code == 500

    # The dataset is still there, its membership soft-deleted and unsynced.
    assert Dataset.objects.filter(id=ds.id).exists()
    membership = DatasetMembership.objects.get(dataset=ds, group=g)
    assert membership.deleted_at is not None
    assert membership.os_synced is False

    # ...so the reconciler can finish the job.
    monkeypatch.undo()
    assert reconcile_dataset(ds.id) == 1
    assert _image_datasets(img.id) == []


# -------------------- reconcile backstop: dataset <-> group --------------------
@pytest.mark.django_db(transaction=True)
def test_reconcile_dataset_recovers_failed_sync(api_url, headers):
    img = _create_image('sync_img5')
    g = Group.objects.create(name='g', type_id='zara_product')
    _put_members(api_url, headers, g, [img.id])
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')

    # Model-only add (no view) leaves the membership os_synced=False and OS untouched.
    ds.add_groups([g.id])
    assert DatasetMembership.objects.get(dataset=ds, group=g).os_synced is False
    assert _image_datasets(img.id) == []

    # The reconciler drives it to OS and flips the flag.
    assert reconcile_dataset(ds.id) == 1
    assert _image_datasets(img.id) == ['p/1']
    assert DatasetMembership.objects.get(dataset=ds, group=g).os_synced is True


# -------------------- reconcile backstop: group <-> image --------------------
@pytest.mark.django_db(transaction=True)
def test_reconcile_group_also_syncs_datasets(api_url, headers):
    img = _create_image('sync_img6')
    g = Group.objects.create(name='g', type_id='zara_product')
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )

    # Raw membership add: group denorm done, datasets NOT recomputed, os_synced=False.
    _add_member_raw(g, img.id)
    assert _image_datasets(img.id) == []

    # The group reconciler recomputes datasets for the touched images too.
    reconcile_group(g.id)
    assert _image_datasets(img.id) == ['p/1']
    assert Membership.objects.filter(group=g, os_synced=False).count() == 0


def test_recompute_writes_by_id_without_a_search_snapshot(monkeypatch):
    """The synchronous path addresses docs by _id with a bulk update, not by query.

    update_by_query takes a search snapshot: a doc modified since the last refresh
    fails the seq_no check and `conflicts: proceed` drops the write SILENTLY. That is
    why every write used to refresh the whole index - to stop the *next* write being
    lost. A bulk update by _id has no snapshot, so no refresh is needed anywhere.
    """
    bulk_calls = []
    lock = threading.Lock()
    monkeypatch.setattr(OS.client, 'update_by_query', lambda **kw: pytest.fail('must not query'))

    def fake_bulk(index, body):
        with lock:  # chunks go out concurrently now
            bulk_calls.append(body)
        return {'items': [{'update': {'_id': 'x'}} for _ in range(len(body) // 2)]}

    monkeypatch.setattr(OS.client, 'bulk', fake_bulk)
    monkeypatch.setattr(os_sync, '_datasets_by_image', lambda image_ids, image_to_groups=None: {})

    total = 2_500
    updated = os_sync.recompute_datasets_for_images([f'img_{i}' for i in range(total)])

    assert updated == total
    expected_chunks = -(-total // os_sync._BULK_CHUNK)  # ceil
    assert len(bulk_calls) == expected_chunks, (
        f'{total} docs at a {os_sync._BULK_CHUNK} chunk should be {expected_chunks} bulk requests, '
        f'got {len(bulk_calls)}'
    )
    assert sum(len(body) // 2 for body in bulk_calls) == total, 'every doc must be sent exactly once'
    # The chunks are concurrent, so img_0 is not necessarily in the first one to arrive.
    action = next(body[0]['update'] for body in bulk_calls if body[0]['update']['_id'] == 'img_0')
    assert action['retry_on_conflict'] == 3, 'concurrent writers must retry, not be dropped'
