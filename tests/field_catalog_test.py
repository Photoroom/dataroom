import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


def _make_image(image_id, user, source, tags=None):
    image = OSImage(
        id=image_id,
        author=user.email,
        source=source,
        image=f'images/{image_id}/original.png',
        image_hash=f'sha256:{image_id}',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=1.0,
        aspect_ratio_fraction='1:1',
        tags=tags or [],
    )
    image.create()
    return image


def _logged_in_client(user):
    client = Client()
    client.login(username=user.email, password='123')
    return client


@pytest.mark.django_db()
def test_field_catalog_source_returns_full_unfiltered_universe(user):
    # 3 images in "big", 2 in "medium", 1 in "small".
    for i in range(3):
        _make_image(f'big-{i}', user, source='big')
    for i in range(2):
        _make_image(f'medium-{i}', user, source='medium')
    _make_image('small-0', user, source='small')
    OS.client.indices.refresh(index=OSImage.INDEX)

    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    # A filter param is deliberately passed to prove the catalog ignores user filters
    # and always returns the global value universe with global counts.
    response = client.get(url, {'fields': 'source', 'source': 'small'})
    assert response.status_code == 200

    catalog = response.json()['source']
    assert catalog['total'] == 3
    assert catalog['truncated'] is False
    counts = {b['key']: b['doc_count'] for b in catalog['values']}
    assert counts == {'big': 3, 'medium': 2, 'small': 1}


@pytest.mark.django_db()
def test_field_catalog_excludes_deleted(user):
    _make_image('live-0', user, source='live')
    ghost = _make_image('ghost-0', user, source='ghost')
    ghost.is_deleted = True
    ghost.save(fields=['is_deleted'])
    OS.client.indices.refresh(index=OSImage.INDEX)

    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    catalog = client.get(url, {'fields': 'source'}).json()['source']
    counts = {b['key']: b['doc_count'] for b in catalog['values']}
    assert counts == {'live': 1}  # the soft-deleted "ghost" source is not listed
    assert catalog['total'] == 1


@pytest.mark.django_db()
def test_field_catalog_tags(user):
    _make_image('a', user, source='s', tags=['red', 'blue'])
    _make_image('b', user, source='s', tags=['red'])
    OS.client.indices.refresh(index=OSImage.INDEX)

    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    # Frontend uses the singular "tag" key; the backend maps it to the "tags" field.
    catalog = client.get(url, {'fields': 'tag'}).json()['tag']
    counts = {b['key']: b['doc_count'] for b in catalog['values']}
    assert counts == {'red': 2, 'blue': 1}
    assert catalog['total'] == 2


@pytest.mark.django_db()
def test_field_catalog_paginates_beyond_page_size(user, mocker):
    # 1200 distinct tags with the page size shrunk to 500 -> forces multiple
    # composite-agg pages, which no other test exercises.
    all_tags = [f'tag-{i:04d}' for i in range(1200)]
    for n, chunk_start in enumerate(range(0, 1200, 50)):
        _make_image(f'page-{n}', user, source='s', tags=all_tags[chunk_start : chunk_start + 50])
    OS.client.indices.refresh(index=OSImage.INDEX)

    real = type(OSImage.objects).counts_by_field_exhaustive
    mocker.patch.object(
        type(OSImage.objects),
        'counts_by_field_exhaustive',
        lambda self, field_name, page_size=50000, max_buckets=50000: real(
            self, field_name, page_size=500, max_buckets=max_buckets
        ),
    )

    client = _logged_in_client(user)
    catalog = client.get(reverse('api:images-field-catalog'), {'fields': 'tag'}).json()['tag']

    assert catalog['truncated'] is False
    assert catalog['total'] == 1200
    assert {v['key'] for v in catalog['values']} == set(all_tags)


@pytest.mark.django_db()
def test_field_catalog_multiple_fields(user):
    _make_image('a', user, source='s1', tags=['t1'])
    _make_image('b', user, source='s2', tags=['t2'])
    OS.client.indices.refresh(index=OSImage.INDEX)

    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    data = client.get(url, {'fields': 'source,tag'}).json()
    assert set(data.keys()) == {'source', 'tag'}
    assert data['source']['total'] == 2
    assert data['tag']['total'] == 2


@pytest.mark.django_db()
def test_field_catalog_rejects_unsupported_field(user):
    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    # Numeric fields are ranges, not term catalogs.
    response = client.get(url, {'fields': 'width'})
    assert response.status_code == 400


@pytest.mark.django_db()
def test_field_catalog_requires_fields_param(user):
    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')

    response = client.get(url)
    assert response.status_code == 400


@pytest.mark.django_db()
def test_field_catalog_served_from_cache_when_client_opts_in(user):
    cache.clear()
    _make_image('cached-0', user, source='cached')
    OS.client.indices.refresh(index=OSImage.INDEX)

    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')
    headers = {'HTTP_CACHE_CONTROL': 'max-age=60'}

    first = client.get(url, {'fields': 'source'}, **headers)
    assert first.status_code == 200
    assert first.json()['source']['total'] == 1

    # New data after the cached response: opted-in requests keep the snapshot,
    # requests without the header bypass the cache and see it.
    _make_image('cached-1', user, source='newer')
    OS.client.indices.refresh(index=OSImage.INDEX)

    cached = client.get(url, {'fields': 'source'}, **headers)
    assert cached.json()['source']['total'] == 1
    fresh = client.get(url, {'fields': 'source'})
    assert fresh.json()['source']['total'] == 2

    cache.clear()


@pytest.mark.django_db()
def test_field_catalog_errors_are_not_cached(user):
    cache.clear()
    client = _logged_in_client(user)
    url = reverse('api:images-field-catalog')
    headers = {'HTTP_CACHE_CONTROL': 'max-age=60'}

    # An unsupported field 400s; the error must not be cached and replayed as a 200.
    assert client.get(url, {'fields': 'width'}, **headers).status_code == 400
    assert client.get(url, {'fields': 'width'}, **headers).status_code == 400

    cache.clear()
