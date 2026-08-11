"""The image ``datasets`` field is derived from dataset membership, not writable.

DRF silently drops undeclared keys, so removing the writable field alone would let a
caller keep sending ``datasets`` and get a 200 back with the value discarded. These
tests pin the loud rejection instead.
"""

import pytest
import requests

from backend.api.images.serializers import (
    OSImageBulkUpdateSerializer,
    OSImageCreateSerializer,
    OSImageUpdateSerializer,
)


@pytest.fixture
def api_url(live_server):
    return live_server.url + '/api'


@pytest.fixture
def headers(token):
    return {'Authorization': f'Token {token.key}'}


@pytest.mark.parametrize(
    'serializer_class',
    [OSImageCreateSerializer, OSImageUpdateSerializer, OSImageBulkUpdateSerializer],
)
def test_write_serializers_reject_datasets(serializer_class):
    serializer = serializer_class(data={'source': 'test', 'datasets': ['products/1']})
    assert not serializer.is_valid()
    assert 'datasets' in serializer.errors


@pytest.mark.parametrize('value', [[], None, ['products/1', 'other/2']])
def test_datasets_rejected_whatever_the_value(value):
    """Even an empty list or null is a write attempt — reject the key, not the value."""
    serializer = OSImageUpdateSerializer(data={'source': 'test', 'datasets': value})
    assert not serializer.is_valid()
    assert 'datasets' in serializer.errors


def test_update_serializer_still_accepts_other_fields():
    serializer = OSImageUpdateSerializer(data={'source': 'test'})
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db(transaction=True)
def test_rest_update_rejects_datasets(api_url, headers, image_logo):
    resp = requests.put(
        f'{api_url}/images/{image_logo.id}/',
        json={'source': 'test', 'datasets': ['products/1']},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert 'datasets' in resp.json()


@pytest.mark.django_db(transaction=True)
def test_rest_bulk_update_rejects_datasets(api_url, headers, image_logo):
    resp = requests.put(
        f'{api_url}/images/bulk_update/',
        json=[{'id': image_logo.id, 'source': 'test', 'datasets': ['products/1']}],
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.django_db(transaction=True)
def test_rest_update_without_datasets_succeeds(api_url, headers, image_logo):
    resp = requests.put(
        f'{api_url}/images/{image_logo.id}/',
        json={'source': 'updated-source'},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.django_db(transaction=True)
def test_datasets_still_readable_on_response(api_url, headers, image_logo):
    resp = requests.get(f'{api_url}/images/{image_logo.id}/', headers=headers)
    assert resp.status_code == 200, resp.text
    assert 'datasets' in resp.json()
