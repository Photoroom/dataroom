"""Backend tests for the Query API.

A Query stores its source `filters` (in the query_dict column) and compiles them to
OpenSearch on demand. It is a dynamic collection, nothing is precompiled. These tests
cover storage, the create/update API, and the live compilation (filtering, counts,
fail-loud validation).
"""

import json

import pytest
import requests

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.query import Query
from backend.dataroom.opensearch import OS
from backend.users.models.token import Token
from backend.users.models.user import User


@pytest.fixture()
def api_url(live_server) -> str:
    return live_server.url + '/api'


@pytest.fixture()
def headers(token: Token) -> dict[str, str]:
    return {'Authorization': f'Token {token.key}'}


def _create_query(
    api_url: str,
    headers: dict[str, str],
    slug: str = 'q',
    name: str = 'Q',
    filters: dict | None = None,
    description: str | None = None,
) -> requests.Response:
    payload = {'slug': slug, 'name': name, 'filters': filters if filters is not None else {'sources': 'shutterstock'}}
    if description is not None:
        payload['description'] = description
    return requests.post(f'{api_url}/queries/', json=payload, headers=headers)


def _create_image(image_id: str, source: str = 'shutterstock', aspect_ratio: float = 1.0) -> OSImage:
    """Index a minimal image into the (test) OS index so queries can match it."""
    image = OSImage(
        id=image_id,
        author='tester',
        source=source,
        image=f'images/{image_id}/original.png',
        image_hash=f'sha256:{image_id}',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=aspect_ratio,
        aspect_ratio_fraction='1:1',
    )
    image.create()
    OS.client.indices.refresh(index=OSImage.INDEX)
    return image


# -------------------- permissions / metadata --------------------


def test_requires_dataroom_access(api_url: str, user_with_no_permission: User) -> None:
    token = Token.objects.create(user=user_with_no_permission)
    resp = requests.get(f'{api_url}/queries/', headers={'Authorization': f'Token {token.key}'})
    assert resp.status_code == 403


def test_author_is_set_to_requester(api_url: str, headers: dict[str, str], user: User) -> None:
    _create_query(api_url, headers, slug='mine')
    assert Query.objects.get(slug='mine').author == user


# -------------------- storage (filters are the stored source) --------------------


def test_create_stores_source_filters(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='q', filters={'sources': 'shutterstock', 'aspect_ratio__gt': 0.5})
    # The source filters are stored verbatim (no precompiled blob).
    assert Query.objects.get(slug='q').query_dict == {'sources': 'shutterstock', 'aspect_ratio__gt': 0.5}


def test_detail_returns_filters(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='q', description='hi', filters={'sources': 'shutterstock'})
    body = requests.get(f'{api_url}/queries/q/', headers=headers).json()
    assert body['slug'] == 'q'
    assert body['description'] == 'hi'
    assert body['filters'] == {'sources': 'shutterstock'}


def test_list_returns_created_queries(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='a', name='Alpha')
    _create_query(api_url, headers, slug='b', name='Beta')
    slugs = {q['slug'] for q in requests.get(f'{api_url}/queries/', headers=headers).json()['results']}
    assert {'a', 'b'} <= slugs


def test_duplicate_slug_is_rejected(api_url: str, headers: dict[str, str]) -> None:
    assert _create_query(api_url, headers, slug='dup').status_code == 201
    resp = _create_query(api_url, headers, slug='dup')
    assert resp.status_code == 400
    assert 'slug' in resp.text.lower()


def test_patch_updates_filters(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='q', filters={'sources': 'shutterstock'})
    resp = requests.patch(f'{api_url}/queries/q/', json={'filters': {'sources': 'getty'}}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert Query.objects.get(slug='q').query_dict == {'sources': 'getty'}


def test_patch_raw_query_dict_is_ignored(api_url: str, headers: dict[str, str]) -> None:
    """query_dict is not a writable API field. Only validated `filters` can set it."""
    _create_query(api_url, headers, slug='q', filters={'sources': 'shutterstock'})
    resp = requests.patch(f'{api_url}/queries/q/', json={'query_dict': {'match_all': {}}}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert Query.objects.get(slug='q').query_dict == {'sources': 'shutterstock'}


def test_put_replaces_name_and_filters(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='q', name='Old', filters={'sources': 'shutterstock'})
    resp = requests.put(
        f'{api_url}/queries/q/',
        json={'slug': 'q', 'name': 'New', 'filters': {'sources': 'getty'}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    query = Query.objects.get(slug='q')
    assert query.name == 'New'
    assert query.query_dict == {'sources': 'getty'}


def test_delete_removes_query(api_url: str, headers: dict[str, str]) -> None:
    _create_query(api_url, headers, slug='gone')
    assert requests.delete(f'{api_url}/queries/gone/', headers=headers).status_code == 204
    assert not Query.objects.filter(slug='gone').exists()


# -------------------- live compilation --------------------


def test_query_filters_images_by_source(api_url: str, headers: dict[str, str]) -> None:
    _create_image('keep', source='shutterstock')
    _create_image('drop', source='getty')
    _create_query(api_url, headers, slug='ss', filters={'sources': 'shutterstock'})
    resp = requests.get(f'{api_url}/images/', params={'query': 'ss'}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert {img['id'] for img in resp.json()['results']} == {'keep'}


def test_query_filters_images_by_numeric_range(api_url: str, headers: dict[str, str]) -> None:
    _create_image('wide', aspect_ratio=2.0)
    _create_image('tall', aspect_ratio=0.5)
    _create_query(api_url, headers, slug='wide-q', filters={'aspect_ratio__gt': 1.0})
    resp = requests.get(f'{api_url}/images/', params={'query': 'wide-q'}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert {img['id'] for img in resp.json()['results']} == {'wide'}


def test_query_is_compiled_live_not_cached(api_url: str, headers: dict[str, str]) -> None:
    """An image added AFTER the query is created still matches, proving the filters are
    compiled on demand, not frozen into a cached query at save time."""
    _create_query(api_url, headers, slug='ss', filters={'sources': 'shutterstock'})

    def query_results() -> set[str]:
        resp = requests.get(f'{api_url}/images/', params={'query': 'ss'}, headers=headers)
        return {img['id'] for img in resp.json()['results']}

    assert query_results() == set()
    _create_image('late', source='shutterstock')
    assert query_results() == {'late'}


def test_filter_by_unknown_query_is_rejected(api_url: str, headers: dict[str, str]) -> None:
    resp = requests.get(f'{api_url}/images/', params={'query': 'nope'}, headers=headers)
    assert resp.status_code == 400, resp.text


def test_create_with_unknown_tag_is_accepted(api_url: str, headers: dict[str, str]) -> None:
    """Tags are matched directly against OpenSearch and no longer validated against the Tag
    table (cardinality is unbounded, e.g. per-product tags). A saved query referencing any
    tag string is stored and simply matches nothing if absent — exactly like `sources`."""
    resp = _create_query(api_url, headers, slug='rare-tag', filters={'tags': 'does-not-exist'})
    assert resp.status_code == 201, resp.text
    assert Query.objects.filter(slug='rare-tag').exists()


# -------------------- multi-lane (query builder) shape --------------------


def test_create_stores_filter_lanes_verbatim(api_url: str, headers: dict[str, str]) -> None:
    """The filter UI's params (a `filter_lanes` JSON string) are stored verbatim and reused."""
    filters = {
        'filter_lanes': json.dumps(
            [
                {'chips': [{'field': 'source', 'operator': 'eq', 'value': 'shutterstock'}], 'negated': False},
                {'chips': [{'field': 'source', 'operator': 'eq', 'value': 'getty'}], 'negated': False},
            ]
        )
    }
    assert _create_query(api_url, headers, slug='lanes', filters=filters).status_code == 201
    assert Query.objects.get(slug='lanes').query_dict == filters


def test_filter_lanes_query_filters_images_with_or(api_url: str, headers: dict[str, str]) -> None:
    """Lanes are OR'd: an image matching either lane is included, others excluded."""
    _create_image('a', source='shutterstock')
    _create_image('b', source='getty')
    _create_image('c', source='istock')
    filters = {
        'filter_lanes': json.dumps(
            [
                {'chips': [{'field': 'source', 'operator': 'eq', 'value': 'shutterstock'}], 'negated': False},
                {'chips': [{'field': 'source', 'operator': 'eq', 'value': 'getty'}], 'negated': False},
            ]
        )
    }
    _create_query(api_url, headers, slug='lanes', filters=filters)
    resp = requests.get(f'{api_url}/images/', params={'query': 'lanes'}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert {img['id'] for img in resp.json()['results']} == {'a', 'b'}


def test_negated_lane_excludes_matches(api_url: str, headers: dict[str, str]) -> None:
    """A negated lane is wrapped in must_not, so images matching it are excluded."""
    _create_image('keep', source='shutterstock')
    _create_image('drop', source='getty')
    filters = {
        'filter_lanes': json.dumps(
            [{'chips': [{'field': 'source', 'operator': 'eq', 'value': 'getty'}], 'negated': True}]
        )
    }
    _create_query(api_url, headers, slug='not-getty', filters=filters)
    resp = requests.get(f'{api_url}/images/', params={'query': 'not-getty'}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert {img['id'] for img in resp.json()['results']} == {'keep'}


def test_nested_query_filter_is_rejected(api_url: str, headers: dict[str, str]) -> None:
    """A saved query may not embed another query (it would recurse at compile time)."""
    _create_query(api_url, headers, slug='base', filters={'sources': 'shutterstock'})
    resp = _create_query(api_url, headers, slug='circular', filters={'query': 'base'})
    assert resp.status_code == 400, resp.text
    assert not Query.objects.filter(slug='circular').exists()
