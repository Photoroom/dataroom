"""Backend tests for the groups + memberships API.

Covers the three test-fixture types (zara_product / recolor_dresses / pose_pair),
the OS denorm sync, and the per-type validation invariants.
"""

import uuid

from unittest.mock import patch

import pytest
import requests
from django.db import IntegrityError
from django.urls import resolve
from django.utils import timezone

from backend.api.groups.views import GroupTypeViewSet
from backend.dataroom.groups.os_sync import add_membership_to_image
from backend.dataroom.models.dataset import Dataset, DatasetMembership
from backend.dataroom.models.group import Group, GroupType, Membership
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS



def _os_image(image_id):
    """Read an image doc. The write paths no longer refresh - they are bulk updates
    addressed by _id, so nothing downstream needs the index refreshed - which means a
    test that reads straight after a write has to refresh for itself."""
    OS.client.indices.refresh(index=OSImage.INDEX)
    return OSImage.objects.search().filter('term', id=image_id).execute().hits[0].to_dict()

@pytest.fixture
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture
def headers(token):
    return {'Authorization': f'Token {token.key}'}


def _create_image(image_id: str, author: str = 'tester'):
    image = OSImage(
        id=image_id,
        author=author,
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


def _add_member(group, image_id, role, metadata=None):
    """Create a Membership row + sync the image's OS denorm. Direct ORM/OS path
    used by tests that need a populated group without going through the API
    (the only API write is the bulk PUT).
    """
    Membership.objects.create(group=group, image_id=image_id, role=role, metadata=metadata or {})
    add_membership_to_image(image_id=image_id, group_id=group.os_encoded_id, role=role)
    OS.client.indices.refresh(index=OSImage.INDEX)


# ----------------------------------------------------------------------
# Group CRUD + type validation
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_put_creates_product_group(api_url, headers):
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={'name': 'zara_01455460', 'type': 'zara_product'},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body['id'] == gid
    assert body['type'] == 'zara_product'
    assert body['name'] == 'zara_01455460'
    assert body['image_count'] == 0


@pytest.mark.django_db(transaction=True)
def test_dataset_requires_author_metadata(api_url, headers):
    # missing required metadata.author
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={'name': 'fashion_v1', 'type': 'recolor_dresses', 'metadata': {}},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'metadata' in resp.json()


@pytest.mark.django_db(transaction=True)
def test_dataset_with_author_metadata_succeeds(api_url, headers):
    image = _create_image('img_ds_author')
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={
            'name': 'fashion_v1',
            'type': 'recolor_dresses',
            'metadata': {'author': 'alice'},
            'members': [{'image_id': image.id, 'role': 'main'}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()['type'] == 'recolor_dresses'


@pytest.mark.django_db(transaction=True)
def test_relationship_requires_context_metadata(api_url, headers):
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={'name': 'rel_42', 'type': 'pose_pair', 'metadata': {}},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_unknown_type_rejected(api_url, headers):
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={'name': 'something', 'type': 'mystery'},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_type_immutable(api_url, headers):
    g = Group.objects.create(name='p', type_id='zara_product')
    resp = requests.patch(
        f'{api_url}/groups/{g.id}/',
        json={'type': 'recolor_dresses'},
        headers=headers,
    )
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# GroupType immutability — create/list/delete only, never edited in place
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_group_type_put_rejected(api_url, headers):
    resp = requests.put(
        f'{api_url}/group-types/zara_product/',
        json={'description': 'changed'},
        headers=headers,
    )
    assert resp.status_code == 405, resp.text


@pytest.mark.django_db(transaction=True)
def test_group_type_patch_rejected(api_url, headers):
    resp = requests.patch(
        f'{api_url}/group-types/zara_product/',
        json={'description': 'changed'},
        headers=headers,
    )
    assert resp.status_code == 405, resp.text
    # Untouched.
    assert GroupType.objects.get(pk='zara_product').description != 'changed'


@pytest.mark.django_db(transaction=True)
def test_group_type_create_and_delete_still_allowed(api_url, headers):
    resp = requests.post(
        f'{api_url}/group-types/',
        json={'name': 'ephemeral_type'},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    resp = requests.delete(f'{api_url}/group-types/ephemeral_type/', headers=headers)
    assert resp.status_code == 204, resp.text
    assert not GroupType.objects.filter(pk='ephemeral_type').exists()


@pytest.mark.django_db(transaction=True)
def test_group_type_name_over_64_chars_rejected(api_url, headers):
    """name is the OS-encoding prefix and the DB PK (max_length=64). An
    over-length name must 400 with a clear message, not 500 on a DB error."""
    resp = requests.post(
        f'{api_url}/group-types/',
        json={'name': 'a' * 65},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'name' in resp.json()
    assert not GroupType.objects.filter(pk='a' * 65).exists()
    # A 64-char name is the boundary and must be accepted.
    resp = requests.post(
        f'{api_url}/group-types/',
        json={'name': 'a' * 64},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.django_db(transaction=True)
def test_group_type_name_invalid_chars_rejected(api_url, headers):
    """The lowercase-alphanumeric-underscore validator surfaces a meaningful
    message rather than an opaque error."""
    resp = requests.post(
        f'{api_url}/group-types/',
        json={'name': 'Has Spaces-And-Caps'},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'lowercase alphanumeric' in resp.text


# ----------------------------------------------------------------------
# OS sync via bulk PUT
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_put_add_member_syncs_os(api_url, headers):
    image = _create_image('img1')
    g = Group.objects.create(name='product_a', type_id='zara_product')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={'metadata': {}, 'members': [{'image_id': image.id, 'role': 'onhang'}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    refreshed = _os_image(image.id)
    assert g.os_encoded_id in refreshed.get('group_ids', [])
    assert f'onhang::{g.os_encoded_id}' in refreshed.get('memberships', [])


@pytest.mark.django_db(transaction=True)
def test_put_drop_member_scrubs_os(api_url, headers):
    image = _create_image('img_rm')
    g = Group.objects.create(name='p_rm', type_id='zara_product')
    _add_member(g, image.id, 'onhang')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={'metadata': {}, 'members': []},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    refreshed = _os_image(image.id)
    assert g.os_encoded_id not in refreshed.get('group_ids', [])
    assert all(not e.endswith(f'::{g.os_encoded_id}') for e in refreshed.get('memberships', []))


@pytest.mark.django_db(transaction=True)
def test_image_holds_multiple_roles_in_one_group(api_url, headers):
    """An image may carry several roles in the same group; dropping one role
    leaves the others (and the group_ids membership) intact."""
    image = _create_image('img_multi')
    g = Group.objects.create(name='p_multi', type_id='zara_product')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},
            'members': [
                {'image_id': image.id, 'role': 'front'},
                {'image_id': image.id, 'role': 'side'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # Two membership rows, one distinct image.
    assert sorted(g.memberships.values_list('role', flat=True)) == ['front', 'side']
    assert resp.json()['image_count'] == 1

    refreshed = _os_image(image.id)
    assert refreshed.get('group_ids', []).count(g.os_encoded_id) == 1
    assert f'front::{g.os_encoded_id}' in refreshed['memberships']
    assert f'side::{g.os_encoded_id}' in refreshed['memberships']

    # Drop only 'side' — 'front' and the group_ids entry survive.
    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={'metadata': {}, 'members': [{'image_id': image.id, 'role': 'front'}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # 'side' was soft-deleted by the PUT; only 'front' is active.
    active_roles = list(g.memberships.filter(deleted_at__isnull=True).values_list('role', flat=True))
    assert active_roles == ['front']

    refreshed = _os_image(image.id)
    assert g.os_encoded_id in refreshed['group_ids']
    assert f'front::{g.os_encoded_id}' in refreshed['memberships']
    assert f'side::{g.os_encoded_id}' not in refreshed['memberships']

    # Drop the last role — the gid leaves group_ids.
    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={'metadata': {}, 'members': []},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    refreshed = _os_image(image.id)
    assert g.os_encoded_id not in refreshed.get('group_ids', [])


@pytest.mark.django_db(transaction=True)
def test_put_rejects_duplicate_image_role_pair(api_url, headers):
    image = _create_image('img_dup_role')
    g = Group.objects.create(name='p_dup_role', type_id='zara_product')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},
            'members': [
                {'image_id': image.id, 'role': 'front'},
                {'image_id': image.id, 'role': 'front'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'image_id' in resp.text


# ----------------------------------------------------------------------
# Image-side filters and /images/{id}/groups
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_image_filter_by_group_ids(api_url, headers):
    image = _create_image('img_filt')
    g = Group.objects.create(name='p_filt', type_id='zara_product')
    _add_member(g, image.id, 'front')

    resp = requests.get(f'{api_url}/images/?group_ids={g.id}', headers=headers)
    assert resp.status_code == 200
    ids = [r['id'] for r in resp.json()['results']]
    assert image.id in ids


@pytest.mark.django_db(transaction=True)
def test_image_filter_by_role_and_group(api_url, headers):
    image = _create_image('img_role_group')
    g = Group.objects.create(name='p_role_group', type_id='zara_product')
    _add_member(g, image.id, 'side')

    # exact (role, group) pair
    resp = requests.get(f'{api_url}/images/?group_ids={g.id}&roles=side', headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()['results']) == 1
    # wrong role: empty
    resp_none = requests.get(f'{api_url}/images/?group_ids={g.id}&roles=front', headers=headers)
    assert resp_none.status_code == 200
    assert resp_none.json()['results'] == []


@pytest.mark.django_db(transaction=True)
def test_image_filter_by_group_type(api_url, headers):
    image = _create_image('img_type_filter')
    g = Group.objects.create(name='p_type_filter', type_id='zara_product')
    _add_member(g, image.id, 'onhang')

    resp = requests.get(f'{api_url}/images/?group_type=zara_product', headers=headers)
    assert resp.status_code == 200
    ids = [r['id'] for r in resp.json()['results']]
    assert image.id in ids


@pytest.mark.django_db(transaction=True)
def test_group_filter_by_dataset(api_url, headers):
    ds = Dataset.objects.create(name='Products', slug='products', type_id='zara_product')
    member = Group.objects.create(name='g_in_dataset', type_id='zara_product')
    Group.objects.create(name='g_not_in_dataset', type_id='zara_product')
    removed = Group.objects.create(name='g_removed_from_dataset', type_id='zara_product')
    DatasetMembership.objects.create(dataset=ds, group=member)
    DatasetMembership.objects.create(dataset=ds, group=removed, deleted_at=timezone.now())

    resp = requests.get(f'{api_url}/groups/?dataset={ds.slug_version}', headers=headers)
    assert resp.status_code == 200, resp.text
    assert {g['name'] for g in resp.json()['results']} == {'g_in_dataset'}


@pytest.mark.django_db(transaction=True)
def test_image_groups_endpoint(api_url, headers):
    image = _create_image('img_groups_ep')
    g = Group.objects.create(name='p_groups_ep', type_id='zara_product')
    _add_member(g, image.id, 'onhang', metadata={'raw_key': 'raw_label'})

    resp = requests.get(f'{api_url}/images/{image.id}/groups/', headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]['role'] == 'onhang'
    assert body[0]['metadata'] == {'raw_key': 'raw_label'}
    assert body[0]['group']['id'] == str(g.id)


# ----------------------------------------------------------------------
# Soft delete + scrub
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_group_delete_is_soft_and_scrubs(api_url, headers):
    image = _create_image('img_del')
    g = Group.objects.create(name='p_del', type_id='zara_product')
    _add_member(g, image.id, 'onhang')

    resp = requests.delete(f'{api_url}/groups/{g.id}/', headers=headers)
    assert resp.status_code == 204

    g.refresh_from_db()
    assert g.deleted_at is not None

    # not visible in list
    list_resp = requests.get(f'{api_url}/groups/', headers=headers)
    ids = [g_['id'] for g_ in list_resp.json().get('results', list_resp.json())]
    assert str(g.id) not in ids

    # DELETE scrubs OS and soft-deletes the rows inline (preserves audit
    # + lets the reconciler see what changed).
    assert not Membership.objects.filter(group_id=g.id, deleted_at__isnull=True).exists()
    assert Membership.objects.filter(group_id=g.id, deleted_at__isnull=False).exists()
    refreshed = _os_image(image.id)
    assert g.os_encoded_id not in refreshed.get('group_ids', [])


# ----------------------------------------------------------------------
# PUT /groups/{id} — bulk replace (metadata + members)
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_put_replaces_metadata_and_members(api_url, headers):
    img1 = _create_image('img_put_1')
    img2 = _create_image('img_put_2')
    g = Group.objects.create(name='ds_put', type_id='recolor_dresses', metadata={'author': 'a'})
    Membership.objects.create(group=g, image_id=img1.id, role='member')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {'author': 'bob'},
            'members': [
                {'image_id': img1.id, 'role': 'main'},
                {'image_id': img2.id, 'role': 'member'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    g.refresh_from_db()
    assert g.metadata == {'author': 'bob'}
    roles = sorted(g.memberships.filter(deleted_at__isnull=True).values_list('image_id', 'role'))
    assert roles == sorted([(img1.id, 'main'), (img2.id, 'member')])


@pytest.mark.django_db(transaction=True)
def test_put_removes_dropped_members(api_url, headers):
    img1 = _create_image('img_drop_1')
    img2 = _create_image('img_drop_2')
    g = Group.objects.create(name='p_drop', type_id='zara_product')
    Membership.objects.create(group=g, image_id=img1.id, role='onhang')
    Membership.objects.create(group=g, image_id=img2.id, role='front')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},
            'members': [{'image_id': img1.id, 'role': 'onhang'}],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    remaining = list(g.memberships.filter(deleted_at__isnull=True).values_list('image_id', flat=True))
    assert remaining == [img1.id]


@pytest.mark.django_db(transaction=True)
def test_put_rejects_missing_required_role(api_url, headers):
    img1 = _create_image('img_req_1')
    g = Group.objects.create(name='ds_req', type_id='recolor_dresses', metadata={'author': 'a'})

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {'author': 'a'},
            'members': [{'image_id': img1.id, 'role': 'member'}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_put_rejects_unknown_role(api_url, headers):
    img1 = _create_image('img_bad_role')
    g = Group.objects.create(name='p_bad', type_id='zara_product')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},
            'members': [{'image_id': img1.id, 'role': 'ghost'}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_put_rejects_invalid_metadata(api_url, headers):
    g = Group.objects.create(name='ds_meta_bad', type_id='recolor_dresses', metadata={'author': 'a'})
    img = _create_image('img_meta_bad')

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},  # missing 'author' (required by dataset metadata_schema)
            'members': [{'image_id': img.id, 'role': 'main'}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# A single PUT body that exercises every branch of bulk_create's
# update_conflicts path at once: insert a brand-new row, update an
# active row's metadata, revive a soft-deleted row, leave an active row
# untouched. PG end state, OS delta, and pk-stability of the revive are
# all verified.
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_put_bulk_upsert_mix_of_records(api_url, headers):
    imgs = [_create_image(f'img_bulk_{i}') for i in range(6)]
    g = Group.objects.create(name='p_bulk', type_id='zara_product')

    # img0: pre-existing active membership; the PUT keeps it as-is.
    _add_member(g, imgs[0].id, 'onhang')
    # img1: pre-existing active membership; PUT updates its metadata.
    _add_member(g, imgs[1].id, 'front')
    # img2: soft-deleted in PG, absent from OS (clean prior removal).
    # Created directly so we control the state and don't poke OS.
    Membership.objects.create(
        group=g, image_id=imgs[2].id, role='side', deleted_at=timezone.now()
    )
    # imgs[3..5]: not in the group yet.

    # Capture pks so we can verify revive vs. fresh-insert.
    pk_img1 = Membership.objects.get(group=g, image_id=imgs[1].id, role='front').pk
    pk_img2 = Membership.objects.get(group=g, image_id=imgs[2].id, role='side').pk

    resp = requests.put(
        f'{api_url}/groups/{g.id}/',
        json={
            'metadata': {},
            'members': [
                {'image_id': imgs[0].id, 'role': 'onhang'},                                # kept
                {'image_id': imgs[1].id, 'role': 'front', 'metadata': {'note': 'new'}},    # md update
                {'image_id': imgs[2].id, 'role': 'side'},                                   # revive
                {'image_id': imgs[3].id, 'role': 'onhang'},                                # insert
                {'image_id': imgs[4].id, 'role': 'front', 'metadata': {'k': 'v'}},         # insert + md
                {'image_id': imgs[5].id, 'role': 'side'},                                  # insert
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # All 6 are active in PG (no extra rows, no stragglers).
    active = g.memberships.filter(deleted_at__isnull=True)
    assert active.count() == 6
    assert set(active.values_list('image_id', 'role')) == {
        (imgs[0].id, 'onhang'),
        (imgs[1].id, 'front'),
        (imgs[2].id, 'side'),
        (imgs[3].id, 'onhang'),
        (imgs[4].id, 'front'),
        (imgs[5].id, 'side'),
    }

    # ON CONFLICT updated img1's metadata on the existing row.
    img1_row = Membership.objects.get(pk=pk_img1)
    assert img1_row.metadata == {'note': 'new'}
    assert img1_row.deleted_at is None

    # ON CONFLICT revived img2 in place: same pk, deleted_at cleared.
    img2_row = Membership.objects.get(pk=pk_img2)
    assert img2_row.deleted_at is None
    assert img2_row.role == 'side'

    # OS denorm: every image now references the group exactly once.
    OS.client.indices.refresh(index=OSImage.INDEX)
    for img, role in [
        (imgs[0], 'onhang'),
        (imgs[1], 'front'),
        (imgs[2], 'side'),
        (imgs[3], 'onhang'),
        (imgs[4], 'front'),
        (imgs[5], 'side'),
    ]:
        doc = _os_image(img.id)
        assert g.os_encoded_id in doc.get('group_ids', []), f"{img.id} missing gid"
        assert f'{role}::{g.os_encoded_id}' in doc.get('memberships', []), (
            f"{img.id} missing membership entry"
        )


# ----------------------------------------------------------------------
# GroupTypeViewSet config: lookup by name + cursor ordering + URL regex
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_group_type_viewset_config(api_url, headers):
    # lookup_field='name': GET by name works and returns the serializer shape.
    resp = requests.get(f'{api_url}/group-types/zara_product/', headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['name'] == 'zara_product'
    assert set(body) == {
        'name',
        'description',
        'metadata_schema',
        'roles',
        'group_count',
        'date_created',
        'date_updated',
    }
    assert isinstance(body['group_count'], int)

    # ordering=['name']: list returns the seed types alphabetically (PK is `name`,
    # so cursor pagination orders on it).
    resp = requests.get(f'{api_url}/group-types/', headers=headers)
    assert resp.status_code == 200, resp.text
    names = [t['name'] for t in resp.json()['results']]
    assert names == sorted(names) == ['pose_pair', 'recolor_dresses', 'zara_product']

    # lookup_value_regex=[a-z0-9_]+ gates the API: names with disallowed
    # characters never route to GroupTypeViewSet. Over HTTP they are *not* a
    # DRF 404 — they fall through to the SPA catch-all (200, index HTML) — so
    # assert on the resolved view instead of the status code.
    assert getattr(resolve('/api/group-types/zara_product/').func, 'cls', None) is GroupTypeViewSet
    for bad in ['Zara_Product', 'zara-product', 'zara product']:
        view_cls = getattr(resolve(f'/api/group-types/{bad}/').func, 'cls', None)
        assert view_cls is not GroupTypeViewSet, (bad, view_cls)


# ----------------------------------------------------------------------
# An image MAY hold several roles in the same group; the unit of
# uniqueness is (image_id, role), not image_id:
#   * Membership UniqueConstraint(group, image_id, role) at the DB level
#   * _bulk_replace rejects a duplicate (image_id, role) in the PUT body
#     but accepts the same image under two different roles
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_image_may_hold_multiple_roles_per_group(api_url, headers):
    image = _create_image('img_dup_role')
    gid = str(uuid.uuid4())

    # Same image in two *different* roles is allowed.
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={
            'name': 'pp_dup',
            'type': 'pose_pair',
            'metadata': {'context': {}},
            'members': [
                {'image_id': image.id, 'role': 'from'},
                {'image_id': image.id, 'role': 'to'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    g = Group.objects.get(id=gid)
    assert set(g.memberships.values_list('role', flat=True)) == {'from', 'to'}

    # The same (image_id, role) twice in one body is still rejected. ('to' is
    # repeated; 'from' is kept so the required-role check passes first and we
    # actually exercise the duplicate-key guard.)
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={
            'name': 'pp_dup',
            'type': 'pose_pair',
            'metadata': {'context': {}},
            'members': [
                {'image_id': image.id, 'role': 'from'},
                {'image_id': image.id, 'role': 'to'},
                {'image_id': image.id, 'role': 'to'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'duplicate (image_id, role)' in resp.text

    # DB-level: the UniqueConstraint is (group, image_id, role). A second
    # role for the same image is fine; the same role twice is not.
    g2 = Group.objects.create(name='zara_multi', type_id='zara_product')
    Membership.objects.create(group=g2, image_id=image.id, role='front')
    Membership.objects.create(group=g2, image_id=image.id, role='side')
    with pytest.raises(IntegrityError):
        Membership.objects.create(group=g2, image_id=image.id, role='front')


# ----------------------------------------------------------------------
# A GroupType's role set cannot be edited in place: GroupTypes are
# immutable (the name is baked into every group's OS denorm and the
# roles/metadata_schema gate validation). PUT/PATCH are not allowed, so
# the "stale membership after a role-set change" hazard never arises
# through the API — you create a new type and migrate instead.
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_group_type_role_set_is_immutable(api_url, headers):
    # PATCH and PUT on a GroupType are both 405 (http_method_names excludes
    # them); only GET / POST / DELETE are routed.
    resp = requests.patch(
        f'{api_url}/group-types/zara_product/',
        json={'roles': [{'role': 'nobody', 'is_required': False}]},
        headers=headers,
    )
    assert resp.status_code == 405, resp.text
    resp = requests.put(
        f'{api_url}/group-types/zara_product/',
        json={'name': 'zara_product', 'metadata_schema': {}, 'roles': []},
        headers=headers,
    )
    assert resp.status_code == 405, resp.text

    # The role catalogue is therefore untouched: 'front' is still a valid
    # zara_product role and a normal membership write keeps working.
    image = _create_image('img_stable_role')
    g = Group.objects.create(name='zara_stable', type_id='zara_product')
    _add_member(g, image.id, 'front')
    assert Membership.objects.filter(group=g, role='front').exists()


# ----------------------------------------------------------------------
# os_synced flag: True on inline-success, False if the inline OS write
# fails (so the periodic reconciler picks the row up next pass).
# ----------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_put_marks_memberships_os_synced(api_url, headers):
    """Happy path: a successful PUT leaves every touched row os_synced=True."""
    img1 = _create_image('img_synced_1')
    img2 = _create_image('img_synced_2')
    gid = str(uuid.uuid4())
    resp = requests.put(
        f'{api_url}/groups/{gid}/',
        json={
            'name': 'p_synced',
            'type': 'zara_product',
            'metadata': {},
            'members': [
                {'image_id': img1.id, 'role': 'onhang'},
                {'image_id': img2.id, 'role': 'front'},
            ],
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    g = Group.objects.get(id=gid)
    assert g.memberships.filter(os_synced=False).count() == 0
    assert g.memberships.filter(os_synced=True).count() == 2


@pytest.mark.django_db(transaction=True)
def test_put_leaves_os_synced_false_on_os_failure(api_url, headers):
    """OS write blows up after PG commit ⇒ rows stay os_synced=False so the
    reconciler will pick them up next pass."""
    img = _create_image('img_os_fail')
    gid = str(uuid.uuid4())
    with patch('backend.api.groups.views.apply_delta_to_images', side_effect=RuntimeError('os down')):
        resp = requests.put(
            f'{api_url}/groups/{gid}/',
            json={
                'name': 'p_os_fail',
                'type': 'zara_product',
                'metadata': {},
                'members': [{'image_id': img.id, 'role': 'onhang'}],
            },
            headers=headers,
        )
    # The view propagates the exception → 500. PG committed, but the
    # post-OS mark-synced step never ran.
    assert resp.status_code == 500
    g = Group.objects.get(id=gid)
    assert g.memberships.filter(os_synced=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_reconcile_memberships_drains_unsynced(api_url, headers):
    """The reconciler picks up rows os_synced=False, drives them to OS, and
    flips the flag. Active rows ⇒ OS add; soft-deleted rows ⇒ OS remove."""
    from django.core.management import call_command

    img_active = _create_image('img_recon_active')
    img_drop = _create_image('img_recon_drop')
    g = Group.objects.create(name='p_recon', type_id='zara_product')

    # Pre-existing membership for img_drop, currently in OS — we'll soft-delete
    # it and let the reconciler scrub OS.
    _add_member(g, img_drop.id, 'onhang')
    Membership.objects.filter(group=g, image_id=img_drop.id).update(
        deleted_at=timezone.now(), os_synced=False
    )
    # New active membership for img_active, NOT yet in OS, awaiting reconcile.
    Membership.objects.create(group=g, image_id=img_active.id, role='front', os_synced=False)

    call_command('reconcile_memberships')

    OS.client.indices.refresh(index=OSImage.INDEX)
    active_doc = _os_image(img_active.id)
    drop_doc = _os_image(img_drop.id)
    assert f'front::{g.os_encoded_id}' in active_doc.get('memberships', [])
    assert g.os_encoded_id not in drop_doc.get('group_ids', [])

    # Flag flipped on both rows.
    assert g.memberships.filter(os_synced=False).count() == 0


@pytest.mark.django_db(transaction=True)
def test_reconcile_memberships_skips_soft_deleted_group(api_url, headers):
    """Memberships of a soft-deleted Group are out of scope — handled by
    cleanup_deleted_groups. Reconciler must leave their os_synced alone."""
    from django.core.management import call_command

    img = _create_image('img_recon_skip')
    g = Group.objects.create(name='p_recon_skip', type_id='zara_product')
    Membership.objects.create(group=g, image_id=img.id, role='onhang', os_synced=False)
    # Soft-delete the group AFTER creating the unsynced membership.
    Group.objects.filter(pk=g.pk).update(deleted_at=timezone.now())

    call_command('reconcile_memberships')

    # Reconciler skipped this membership; flag remains False.
    assert g.memberships.filter(os_synced=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_destroy_marks_memberships_os_synced(api_url, headers):
    """DELETE soft-deletes memberships, scrubs OS, then marks them synced."""
    img = _create_image('img_destroy_sync')
    g = Group.objects.create(name='p_destroy_sync', type_id='zara_product')
    _add_member(g, img.id, 'onhang')
    # _add_member writes directly to OS but doesn't touch os_synced; force it
    # True so the assertion below proves DELETE's own mark-synced step ran
    # (not just that the row was already True).
    g.memberships.update(os_synced=False)

    resp = requests.delete(f'{api_url}/groups/{g.id}/', headers=headers)
    assert resp.status_code == 204
    assert g.memberships.filter(os_synced=False).count() == 0
    assert g.memberships.filter(os_synced=True, deleted_at__isnull=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_roles_catalog_carries_group_types_and_usage(api_url, headers, seed_group_types):
    """Each role says which GroupTypes declare it and how many active groups actually
    hold a membership with it - declared vs. used, same duality as the roles/has_role
    group filters."""
    img = _create_image('rolecat_img')
    g = Group.objects.create(name='rolecat_g', type_id='zara_product')
    Membership.objects.create(group=g, image_id=img.id, role='onhang')

    roles = {r['name']: r for r in requests.get(f'{api_url}/roles/?page_size=100', headers=headers).json()['results']}

    assert 'zara_product' in roles['onhang']['group_types']
    assert roles['onhang']['group_count'] == 1
    # declared by a type, used by nothing
    assert roles['front']['group_count'] == 0
    assert 'zara_product' in roles['front']['group_types']


@pytest.mark.django_db(transaction=True)
def test_bulk_create_groups(api_url, headers, seed_group_types):
    """POST /groups/bulk/ creates many groups + memberships + the OS denorm in one
    request - the fast path for importing at scale."""
    imgs = [_create_image(f'bulk_img_{i}') for i in range(4)]

    specs = {
        'groups': [
            {'name': 'bg1', 'type': 'zara_product',
             'members': [{'image_id': imgs[0].id, 'role': 'onhang'}, {'image_id': imgs[1].id, 'role': 'front'}]},
            {'name': 'bg2', 'type': 'zara_product',
             'members': [{'image_id': imgs[2].id, 'role': 'onhang'}]},
            {'name': 'bg3', 'type': 'zara_product', 'members': []},
        ]
    }
    resp = requests.post(f'{api_url}/groups/bulk/', json=specs, headers=headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert len(created) == 3
    assert {g['name'] for g in created} == {'bg1', 'bg2', 'bg3'}
    assert next(g for g in created if g['name'] == 'bg1')['image_count'] == 2

    # PG memberships exist
    bg1 = Group.objects.get(name='bg1')
    assert bg1.memberships.filter(deleted_at__isnull=True).count() == 2

    # OS denorm was written and marked synced
    assert bg1.memberships.filter(os_synced=False).count() == 0
    doc = _os_image(imgs[0].id)
    assert bg1.os_encoded_id in doc.get('group_ids', [])
    assert f'onhang::{bg1.os_encoded_id}' in doc.get('memberships', [])


@pytest.mark.django_db(transaction=True)
def test_bulk_create_reports_per_group_errors(api_url, headers, seed_group_types):
    _create_image('bulkerr_img')
    specs = {
        'groups': [
            {'name': 'ok', 'type': 'zara_product', 'members': [{'image_id': 'bulkerr_img', 'role': 'onhang'}]},
            {'name': 'bad-role', 'type': 'zara_product', 'members': [{'image_id': 'bulkerr_img', 'role': 'nope'}]},
            {'name': 'bad-type', 'type': 'does_not_exist', 'members': []},
        ]
    }
    resp = requests.post(f'{api_url}/groups/bulk/', json=specs, headers=headers)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    # unknown type is caught up front; nothing is created (atomic)
    assert 'type' in body or 'groups' in body
    assert not Group.objects.filter(name__in=['ok', 'bad-role']).exists()


@pytest.mark.django_db(transaction=True)
def test_bulk_delete_groups(api_url, headers, seed_group_types):
    """POST /groups/bulk-delete/ soft-deletes many groups + scrubs the OS denorm in one
    request - the counterpart of bulk create, and what makes tearing down an import
    cost one round trip instead of one per group."""
    imgs = [_create_image(f'bulkdel_img_{i}') for i in range(3)]
    specs = {
        'groups': [
            {'name': 'bd1', 'type': 'zara_product',
             'members': [{'image_id': imgs[0].id, 'role': 'onhang'}, {'image_id': imgs[1].id, 'role': 'front'}]},
            {'name': 'bd2', 'type': 'zara_product', 'members': [{'image_id': imgs[1].id, 'role': 'onhang'}]},
            {'name': 'keep', 'type': 'zara_product', 'members': [{'image_id': imgs[1].id, 'role': 'side'}]},
        ]
    }
    created = requests.post(f'{api_url}/groups/bulk/', json=specs, headers=headers).json()
    by_name = {g['name']: g['id'] for g in created}
    kept = Group.objects.get(name='keep')

    # imgs[1] is in all three groups — it must keep exactly the survivor.
    doc = _os_image(imgs[1].id)
    assert len(doc['group_ids']) == 3

    resp = requests.post(
        f'{api_url}/groups/bulk-delete/',
        json={'group_ids': [by_name['bd1'], by_name['bd2']]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {'deleted_count': 2}

    # PG: groups and their memberships soft-deleted, and marked synced.
    for name in ('bd1', 'bd2'):
        g = Group.objects.get(name=name)
        assert g.deleted_at is not None
        assert g.memberships.filter(deleted_at__isnull=True).count() == 0
        assert g.memberships.filter(os_synced=False).count() == 0
    assert Group.objects.get(name='keep').deleted_at is None

    # OS: only the deleted groups are stripped; the survivor's entries are untouched.
    doc = _os_image(imgs[1].id)
    assert doc.get('group_ids', []) == [kept.os_encoded_id]
    assert doc.get('memberships', []) == [f'side::{kept.os_encoded_id}']
    # An image that was ONLY in a deleted group is left with nothing.
    doc = _os_image(imgs[0].id)
    assert doc.get('group_ids', []) == []
    assert doc.get('memberships', []) == []


@pytest.mark.django_db(transaction=True)
def test_bulk_delete_drops_the_groups_datasets_from_images(api_url, headers, seed_group_types):
    """A deleted group can no longer back a dataset membership, so its images must
    lose the dataset's slug_version too."""
    img = _create_image('bulkdel_ds_img')
    created = requests.post(
        f'{api_url}/groups/bulk/',
        json={'groups': [{'name': 'dsg', 'type': 'zara_product',
                          'members': [{'image_id': img.id, 'role': 'onhang'}]}]},
        headers=headers,
    ).json()
    gid = created[0]['id']
    ds = Dataset.objects.create(name='P', slug='p', type_id='zara_product')
    requests.post(f'{api_url}/datasets/{ds.slug_version}/groups/', json={'group_ids': [gid]}, headers=headers)
    assert _os_image(img.id).get('datasets') == ['p/1']

    resp = requests.post(f'{api_url}/groups/bulk-delete/', json={'group_ids': [gid]}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert _os_image(img.id).get('datasets', []) == []


@pytest.mark.django_db(transaction=True)
def test_bulk_delete_ignores_unknown_and_already_deleted_ids(api_url, headers, seed_group_types):
    """Deleting is idempotent: a retry after a partial failure must not 400."""
    created = requests.post(
        f'{api_url}/groups/bulk/',
        json={'groups': [{'name': 'once', 'type': 'zara_product', 'members': []}]},
        headers=headers,
    ).json()
    gid = created[0]['id']

    first = requests.post(f'{api_url}/groups/bulk-delete/', json={'group_ids': [gid]}, headers=headers)
    assert first.json() == {'deleted_count': 1}

    # Same id again, plus one that never existed.
    again = requests.post(
        f'{api_url}/groups/bulk-delete/',
        json={'group_ids': [gid, str(uuid.uuid4())]},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert again.json() == {'deleted_count': 0}


@pytest.mark.django_db(transaction=True)
def test_bulk_delete_validates_the_body(api_url, headers, seed_group_types):
    for body in ({}, {'group_ids': []}, {'group_ids': ['not-a-uuid']}):
        resp = requests.post(f'{api_url}/groups/bulk-delete/', json=body, headers=headers)
        assert resp.status_code == 400, f'{body} -> {resp.status_code} {resp.text}'

    over = {'group_ids': [str(uuid.uuid4()) for _ in range(1001)]}
    assert requests.post(f'{api_url}/groups/bulk-delete/', json=over, headers=headers).status_code == 400


@pytest.mark.django_db(transaction=True)
def test_bulk_delete_failed_os_write_leaves_rows_for_the_reconciler(api_url, headers, seed_group_types):
    """Two-phase, like every other write: PG commits first, so a failed OS write leaves
    os_synced=False rows rather than a silent PG<->OS desync."""
    img = _create_image('bulkdel_fail_img')
    created = requests.post(
        f'{api_url}/groups/bulk/',
        json={'groups': [{'name': 'failg', 'type': 'zara_product',
                          'members': [{'image_id': img.id, 'role': 'onhang'}]}]},
        headers=headers,
    ).json()
    gid = created[0]['id']

    with patch('backend.api.groups.views.remove_groups_from_images', side_effect=RuntimeError('OS down')):
        resp = requests.post(f'{api_url}/groups/bulk-delete/', json={'group_ids': [gid]}, headers=headers)
    assert resp.status_code == 500

    group = Group.objects.get(id=gid)
    assert group.deleted_at is not None  # PG committed
    assert group.memberships.filter(os_synced=False).count() == 1  # OS did not — reconciler's job


@pytest.mark.django_db(transaction=True)
def test_bare_post_groups_is_405(api_url, headers, seed_group_types):
    resp = requests.post(f'{api_url}/groups/', json={'name': 'x', 'type': 'zara_product'}, headers=headers)
    assert resp.status_code == 405, resp.text
