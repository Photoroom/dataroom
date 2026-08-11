"""Image filtering by dataset slug_version.

The ``OSImage.datasets`` denorm holds Dataset slug_versions, so the images
endpoint filters on them directly (no PG validation). These assert the public
filter surface: exact ``?datasets=`` match, version-agnostic ``?datasets__prefix=``,
and that an unknown slug yields an empty result (not a 400 like the old model-
validated filter did).
"""

import pytest
import requests

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


@pytest.fixture()
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture()
def headers(token):
    return {'Authorization': f'Token {token.key}'}


def _create_image(image_id: str, datasets: list[str]):
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
    # Set the denorm directly — this test isolates the filter from the sync path.
    OS.client.update_by_query(
        index=OSImage.INDEX,
        body={
            'query': {'terms': {'id': [image_id]}},
            'script': {'lang': 'painless', 'source': 'ctx._source.datasets = params.d', 'params': {'d': datasets}},
        },
        params={'conflicts': 'proceed'},
    )
    OS.client.indices.refresh(index=OSImage.INDEX)
    return image


def _ids(api_url, headers, query):
    resp = requests.get(f'{api_url}/images/?{query}', headers=headers)
    assert resp.status_code == 200, resp.text
    return {img['id'] for img in resp.json()['results']}


@pytest.mark.django_db(transaction=True)
def test_filter_by_exact_slug_version(api_url, headers):
    _create_image('flt_a', ['shoes/1'])
    _create_image('flt_b', ['shoes/2'])
    _create_image('flt_c', [])

    assert _ids(api_url, headers, 'datasets=shoes/1') == {'flt_a'}
    assert _ids(api_url, headers, 'datasets=shoes/1,shoes/2') == {'flt_a', 'flt_b'}


@pytest.mark.django_db(transaction=True)
def test_unknown_slug_returns_empty_not_400(api_url, headers):
    _create_image('flt_a', ['shoes/1'])
    # The old model-validated filter 400'd here; now it's a plain empty match.
    resp = requests.get(f'{api_url}/images/?datasets=doesnotexist/1', headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()['results'] == []


@pytest.mark.django_db(transaction=True)
def test_filter_by_prefix_is_version_agnostic(api_url, headers):
    _create_image('flt_a', ['shoes/1'])
    _create_image('flt_b', ['shoes/2'])
    _create_image('flt_c', ['shoes-2/1'])  # different slug — must NOT match `shoes`

    assert _ids(api_url, headers, 'datasets__prefix=shoes') == {'flt_a', 'flt_b'}
    assert _ids(api_url, headers, 'datasets__prefix=shoes-2') == {'flt_c'}
