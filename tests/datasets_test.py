"""Backend tests for the datasets API.

A Dataset is a versioned, freezable collection of Groups of one immutable
GroupType, stored purely in Postgres. Uses the seed_group_types fixture
(zara_product / recolor_dresses / pose_pair) from conftest.
"""

import uuid

import pytest
import requests

from backend.dataroom.models.group import Group
from backend.dataroom.models.dataset import Dataset, DatasetVersionTypeMismatchError, DatasetMembership


@pytest.fixture
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture
def headers(token):
    return {'Authorization': f'Token {token.key}'}


def _make_group(name, type_id='zara_product'):
    return Group.objects.create(name=name, type_id=type_id)


# Create, versioning, type
@pytest.mark.django_db(transaction=True)
def test_create_dataset_increments_version(api_url, headers):
    resp = requests.post(
        f'{api_url}/datasets/',
        json={'name': 'Products', 'slug': 'products', 'type': 'zara_product'},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body['slug_version'] == 'products/1'
    assert body['version'] == 1
    assert body['type'] == 'zara_product'
    assert body['group_count'] == 0

    # Posting the same slug bumps the version.
    resp = requests.post(
        f'{api_url}/datasets/',
        json={'name': 'Products', 'slug': 'products', 'type': 'zara_product'},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()['version'] == 2


@pytest.mark.django_db(transaction=True)
def test_create_rejects_unknown_type(api_url, headers):
    resp = requests.post(
        f'{api_url}/datasets/',
        json={'name': 'X', 'slug': 'x', 'type': 'mystery'},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'type' in resp.json()


@pytest.mark.django_db(transaction=True)
def test_changing_type_is_rejected(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')

    # Trying to change type must be a hard 400, not a silent no-op. PUT is a full
    # update, so it must carry the required `name` — otherwise it 400s on `name`
    # before the type-immutability check is even reached.
    for method in (requests.patch, requests.put):
        resp = method(
            f'{api_url}/datasets/{ds.slug_version}/',
            json={'name': 'P', 'type': 'recolor_dresses', 'description': 'edited'},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert 'type' in resp.json()
    ds.refresh_from_db()
    assert ds.type_id == 'zara_product'


@pytest.mark.django_db(transaction=True)
def test_edit_echoing_current_type_is_allowed(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')

    # A no-op round-trip that echoes back the current type must still succeed.
    resp = requests.patch(
        f'{api_url}/datasets/{ds.slug_version}/',
        json={'type': 'zara_product', 'description': 'edited'},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['type'] == 'zara_product'
    assert resp.json()['description'] == 'edited'


# Membership: add, list, type validation
@pytest.mark.django_db(transaction=True)
def test_add_and_list_groups(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    g1 = _make_group('g1')
    g2 = _make_group('g2')

    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g1.id), str(g2.id)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['updated_count'] == 2

    # group_count on the detail endpoint reflects the additions.
    detail = requests.get(f'{api_url}/datasets/{ds.slug_version}/', headers=headers)
    assert detail.json()['group_count'] == 2

    # And listed by the groups sub-resource.
    listing = requests.get(f'{api_url}/datasets/{ds.slug_version}/groups/', headers=headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body['next'] is None  # a cursor page, not a count
    assert {g['id'] for g in body['results']} == {str(g1.id), str(g2.id)}

    # Re-adding an already-member group is a no-op.
    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g1.id)]},
        headers=headers,
    )
    assert resp.json()['updated_count'] == 0


@pytest.mark.django_db(transaction=True)
def test_add_group_of_wrong_type_rejected(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    other = _make_group('other', type_id='recolor_dresses')

    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(other.id)]},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'group_ids' in resp.json()
    assert ds.memberships.count() == 0


@pytest.mark.django_db(transaction=True)
def test_add_unknown_group_rejected(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(uuid.uuid4())]},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


# Soft-delete and revive
@pytest.mark.django_db(transaction=True)
def test_remove_soft_deletes_and_readd_revives(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    g = _make_group('g')

    requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    row_pk = DatasetMembership.objects.get(dataset=ds, group=g).pk

    # Remove soft-deletes the row: it stays with deleted_at set.
    resp = requests.delete(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['updated_count'] == 1
    row = DatasetMembership.objects.get(pk=row_pk)
    assert row.deleted_at is not None
    assert requests.get(f'{api_url}/datasets/{ds.slug_version}/', headers=headers).json()['group_count'] == 0

    # Re-add revives the same row instead of creating a duplicate.
    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert resp.json()['updated_count'] == 1
    assert DatasetMembership.objects.filter(dataset=ds, group=g).count() == 1
    assert DatasetMembership.objects.get(pk=row_pk).deleted_at is None


# Freeze and unfreeze
@pytest.mark.django_db(transaction=True)
def test_freeze_blocks_mutations(api_url, headers):
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    g = _make_group('g')

    requests.post(f'{api_url}/datasets/{ds.slug_version}/freeze/', headers=headers)

    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'frozen' in resp.text.lower()

    # Unfreezing lets mutations work again.
    requests.post(f'{api_url}/datasets/{ds.slug_version}/unfreeze/', headers=headers)
    resp = requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()['updated_count'] == 1


# Copy
@pytest.mark.django_db(transaction=True)
def test_copy_creates_same_type_with_members(api_url, headers):
    source = Dataset.objects.create(name='Source', slug='source', type_id='zara_product')
    g1 = _make_group('g1')
    g2 = _make_group('g2')
    source.add_groups([g1.id, g2.id])

    resp = requests.post(
        f'{api_url}/datasets/{source.slug_version}/copy/',
        json={'name': 'Copy', 'slug': 'copy'},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body['slug_version'] == 'copy/1'
    assert body['type'] == 'zara_product'
    assert body['group_count'] == 2

    listing = requests.get(f'{api_url}/datasets/copy/1/groups/', headers=headers)
    assert {g['id'] for g in listing.json()['results']} == {str(g1.id), str(g2.id)}


@pytest.mark.django_db(transaction=True)
def test_groups_sub_resource_is_paginated(api_url, headers, seed_group_types):
    """It must be: resolving covers for the page is one OpenSearch search, and
    OpenSearch caps a search at index.max_result_window (10k hits). Returning a
    whole membership was a hard 500 for any dataset past that.
    """
    ds = Dataset.objects.create(name='P', slug='paged', type_id='zara_product')
    groups = [_make_group(f'pg{i}') for i in range(3)]
    requests.post(
        f'{api_url}/datasets/{ds.slug_version}/groups/',
        json={'group_ids': [str(g.id) for g in groups]},
        headers=headers,
    )

    first = requests.get(f'{api_url}/datasets/{ds.slug_version}/groups/?page_size=2', headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert set(body) == {'next', 'previous', 'results'}
    assert 'group_count' not in body  # the dataset carries the total, not the page
    assert len(body['results']) == 2
    assert body['next']

    # The cursor walks the rest.
    second = requests.get(body['next'], headers=headers)
    assert second.status_code == 200, second.text
    assert len(second.json()['results']) == 1

    seen = {g['id'] for g in body['results']} | {g['id'] for g in second.json()['results']}
    assert seen == {str(g.id) for g in groups}

    # page_size is bounded, so the cover fetch can never exceed the OS result window.
    too_big = requests.get(f'{api_url}/datasets/{ds.slug_version}/groups/?page_size=99999', headers=headers)
    assert too_big.status_code == 400, too_big.text


@pytest.mark.django_db(transaction=True)
def test_a_new_version_cannot_change_the_slug_type(api_url, headers, seed_group_types):
    """A slug names one collection. Its versions all collect the same kind of Group.

    `type` is immutable on a dataset, but creating against an existing slug makes a new
    *version*, which used to be an unguarded second way in: it let a `zara_product`
    dataset become a `recolor_dresses` one at version 2.
    """
    first = requests.post(
        f'{api_url}/datasets/', json={'name': 'M', 'slug': 'mixed', 'type': 'zara_product'}, headers=headers
    )
    assert first.status_code == 201, first.text

    clash = requests.post(
        f'{api_url}/datasets/', json={'name': 'M', 'slug': 'mixed', 'type': 'recolor_dresses'}, headers=headers
    )
    assert clash.status_code == 400, clash.text
    assert 'zara_product' in clash.json()['type'][0]

    # The same type is still a normal new version.
    same = requests.post(
        f'{api_url}/datasets/', json={'name': 'M', 'slug': 'mixed', 'type': 'zara_product'}, headers=headers
    )
    assert same.status_code == 201, same.text
    assert same.json()['slug_version'] == 'mixed/2'

    assert set(Dataset.objects.filter(slug='mixed').values_list('type_id', flat=True)) == {'zara_product'}


@pytest.mark.django_db(transaction=True)
def test_copy_into_a_slug_of_another_type_is_rejected(api_url, headers, seed_group_types):
    """copy creates a version of the target slug, so it inherits the same rule."""
    requests.post(
        f'{api_url}/datasets/', json={'name': 'A', 'slug': 'aaa', 'type': 'zara_product'}, headers=headers
    )
    requests.post(
        f'{api_url}/datasets/', json={'name': 'B', 'slug': 'bbb', 'type': 'recolor_dresses'}, headers=headers
    )

    resp = requests.post(
        f'{api_url}/datasets/aaa/1/copy/', json={'name': 'B copy', 'slug': 'bbb'}, headers=headers
    )
    assert resp.status_code == 400, resp.text
    assert 'recolor_dresses' in str(resp.json()['slug'])
    assert Dataset.objects.filter(slug='bbb').count() == 1


@pytest.mark.django_db(transaction=True)
def test_manager_rejects_a_type_change_across_versions(seed_group_types):
    """Enforced in the manager, so the ORM cannot sidestep the API's validation."""
    Dataset.objects.create(name='M', slug='ormmixed', type_id='zara_product')
    with pytest.raises(DatasetVersionTypeMismatchError):
        Dataset.objects.create(name='M', slug='ormmixed', type_id='recolor_dresses')
    assert Dataset.objects.filter(slug='ormmixed').count() == 1
