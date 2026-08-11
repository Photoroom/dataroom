"""Expandable serializer output for the datasets & groups APIs (include_fields)."""

import uuid

import pytest
import requests

from backend.api.groups.expand import expand_groups
from backend.dataroom.models.dataset import Dataset
from backend.dataroom.models.group import Group, Membership
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


@pytest.fixture()
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture()
def headers(token):
    return {'Authorization': f'Token {token.key}'}


def _create_image(image_id):
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


@pytest.mark.django_db(transaction=True)
def test_expanded_roles_always_carry_membership_metadata(api_url, headers, seed_group_types):
    """include_roles brings each membership's metadata with it - the query fetches it
    anyway, and a member without its metadata is half a member. include_metadata still
    gates the GROUP's own metadata blob."""
    group = Group.objects.create(name='g-rolemeta', type_id='zara_product', metadata={'season': 'aw26'})
    _create_image('rolemeta_img')
    Membership.objects.create(group=group, image_id='rolemeta_img', role='onhang', metadata={'quality': 'a'})

    r = requests.get(f'{api_url}/groups/{group.id}/?include_fields=roles', headers=headers).json()
    assert r['roles'][0]['metadata'] == {'quality': 'a'}
    # the group blob is still opt-in on the dataset sub-resource merge; on /groups/
    # it is part of the serializer regardless.


def test_group_expand_roles_metadata_presigned(api_url, headers, seed_group_types):
    _create_image('exp_img1')
    _create_image('exp_img2')
    group = Group.objects.create(name='g-expand', type_id='zara_product', metadata={'season': 'ss25'})
    Membership.objects.create(group=group, image_id='exp_img1', role='onhang', metadata={'quality': 'a'})
    Membership.objects.create(group=group, image_id='exp_img2', role='onmodel', metadata={'quality': 'b'})

    # plain: no roles field by default
    plain = requests.get(f'{api_url}/groups/{group.id}/', headers=headers).json()
    assert 'roles' not in plain

    # expanded: roles + role metadata + presigned url + group metadata
    r = requests.get(
        f'{api_url}/groups/{group.id}/?include_fields=roles,presigned_url&include_metadata=true', headers=headers
    ).json()
    assert r['metadata'] == {'season': 'ss25'}
    roles = {m['role']: m for m in r['roles']}
    assert set(roles) == {'onhang', 'onmodel'}
    assert roles['onhang']['image_id'] == 'exp_img1'
    assert roles['onhang']['metadata'] == {'quality': 'a'}
    assert roles['onhang']['presigned_url']  # a real signed URL string

    # return_roles filters which roles come back
    only = requests.get(
        f'{api_url}/groups/{group.id}/?include_fields=roles&return_roles=onmodel', headers=headers
    ).json()
    assert [m['role'] for m in only['roles']] == ['onmodel']


@pytest.mark.django_db(transaction=True)
def test_groups_list_has_role_filter(api_url, headers, seed_group_types):
    _create_image('exp_img3')
    g1 = Group.objects.create(name='g-hero', type_id='zara_product')
    Membership.objects.create(group=g1, image_id='exp_img3', role='onhang')
    g2 = Group.objects.create(name='g-none', type_id='zara_product')  # no memberships

    ids = {g['id'] for g in requests.get(f'{api_url}/groups/?has_role=onhang', headers=headers).json()['results']}
    assert str(g1.id) in ids
    assert str(g2.id) not in ids


@pytest.mark.django_db
def test_expand_groups_issues_one_query_regardless_of_page_size(seed_group_types, django_assert_num_queries):
    """The batching claim: one PG query for the whole page, not one per group.

    Roles-only, so no OpenSearch call is involved.
    """
    opts = {
        'roles': True,
        'return_roles': None,
        'include_metadata': False,
        'presigned_url': False,
        'thumbnail_url': False,
        'os_metadata': False,
        'datasets': False,
    }

    def _page(size):
        groups = [Group.objects.create(name=f'batch_{uuid.uuid4().hex[:8]}', type_id='zara_product') for _ in range(size)]
        for group in groups:
            Membership.objects.create(group=group, image_id=f'img_{uuid.uuid4().hex[:8]}', role='onhang')
        return groups

    small, large = _page(2), _page(8)

    with django_assert_num_queries(1):
        expanded = expand_groups(small, opts)
    assert sum(len(e['roles']) for e in expanded.values()) == 2

    # Four times the groups, same number of queries.
    with django_assert_num_queries(1):
        expanded = expand_groups(large, opts)
    assert sum(len(e['roles']) for e in expanded.values()) == 8


@pytest.mark.django_db(transaction=True)
def test_presigned_url_never_falls_back_to_the_thumbnail(api_url, headers, seed_group_types):
    """presigned_url is the original's url or null. It used to silently hand back the
    thumbnail when the original was missing - a field named presigned_url returning a
    thumbnail is a lie. thumbnail_url is its own include field now."""
    group = Group.objects.create(name='g-urls', type_id='zara_product')
    _create_image('urls_img')
    # a doc with no original on file: strip the field the way a broken/legacy doc has it
    OS.client.update(
        index=OSImage.INDEX, id='urls_img',
        body={'script': {'lang': 'painless', 'source': "ctx._source.image = null;"}},
    )
    OS.client.indices.refresh(index=OSImage.INDEX)
    Membership.objects.create(group=group, image_id='urls_img', role='onhang')

    r = requests.get(
        f'{api_url}/groups/{group.id}/?include_fields=presigned_url,thumbnail_url', headers=headers
    ).json()
    entry = r['roles'][0]
    assert entry['presigned_url'] is None  # no original: null, not a thumbnail in disguise
    assert 'thumbnail_url' in entry  # requested separately, present as its own key


@pytest.mark.django_db(transaction=True)
def test_thumbnail_url_falls_back_to_the_original(api_url, headers, seed_group_types):
    """Thumbnails are generated asynchronously, so an image can sit without one.
    thumbnail_url then serves the original instead of null - otherwise the dataset
    page's role tiles go blank while the group's cover (which already falls back)
    still shows. The cover and the role cells have to agree."""
    group = Group.objects.create(name='g-nothumb', type_id='zara_product')
    _create_image('nothumb_img')  # created without a thumbnail, like a freshly ingested image
    Membership.objects.create(group=group, image_id='nothumb_img', role='onhang')

    r = requests.get(f'{api_url}/groups/{group.id}/?include_fields=thumbnail_url', headers=headers).json()
    assert r['roles'][0]['thumbnail_url']  # the original, not null

    # and with no image on file either, it is honestly null
    OS.client.update(
        index=OSImage.INDEX, id='nothumb_img',
        body={'script': {'lang': 'painless', 'source': "ctx._source.image = null;"}},
    )
    OS.client.indices.refresh(index=OSImage.INDEX)
    r = requests.get(f'{api_url}/groups/{group.id}/?include_fields=thumbnail_url', headers=headers).json()
    assert r['roles'][0]['thumbnail_url'] is None


@pytest.mark.django_db(transaction=True)
def test_groups_expand_their_dataset_memberships(api_url, headers, seed_group_types):
    """?include_fields=datasets on the groups list: one page-scoped join over
    DatasetMembership, so a group can finally say which datasets contain it."""
    g1 = Group.objects.create(name='g-ds1', type_id='zara_product')
    g2 = Group.objects.create(name='g-ds2', type_id='zara_product')
    a = Dataset.objects.create(name='A', slug='exp-a', type_id='zara_product')
    b = Dataset.objects.create(name='B', slug='exp-b', type_id='zara_product')
    a.add_groups([g1.id])
    b.add_groups([g1.id])

    r = requests.get(f'{api_url}/groups/?include_fields=datasets&name__prefix=g-ds', headers=headers).json()
    by_name = {g['name']: g for g in r['results']}
    assert by_name['g-ds1']['datasets'] == ['exp-a/1', 'exp-b/1']
    assert by_name['g-ds2']['datasets'] == []

    # and on retrieve
    one = requests.get(f'{api_url}/groups/{g1.id}/?include_fields=datasets', headers=headers).json()
    assert one['datasets'] == ['exp-a/1', 'exp-b/1']

    # not requested -> not present
    plain = requests.get(f'{api_url}/groups/{g1.id}/', headers=headers).json()
    assert 'datasets' not in plain
