"""Regression tests for the Tag-table stats sync.

The tags filter validates tag names against the Postgres Tag table (400 on unknown tags)
and the UI offers the complete tag catalog from OpenSearch, so the stats cron must keep a
Tag row for EVERY tag present in OpenSearch — a top-N sync silently breaks filtering on
every tag beyond the cap.
"""

import datetime

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.stats import Stats
from backend.dataroom.models.tag import Tag
from backend.dataroom.opensearch import OS


def _make_image(image_id, user, tags):
    image = OSImage(
        id=image_id,
        author=user.email,
        source='tag-stats',
        image=f'images/{image_id}/original.png',
        image_hash=f'sha256:{image_id}',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=1.0,
        aspect_ratio_fraction='1:1',
        tags=tags,
    )
    image.create()
    return image


def _logged_in_client(user):
    client = Client()
    client.login(username=user.email, password='123')
    return client


def _patch_exhaustive_counts(mocker, **overrides):
    """Shrink counts_by_field_exhaustive's paging params to exercise pagination/truncation
    with a small seeded tag set."""
    real = type(OSImage.objects).counts_by_field_exhaustive
    mocker.patch.object(
        type(OSImage.objects),
        'counts_by_field_exhaustive',
        lambda self, field_name, page_size=50000, max_buckets=50000: real(
            self,
            field_name,
            page_size=overrides.get('page_size', page_size),
            max_buckets=overrides.get('max_buckets', max_buckets),
        ),
    )


@pytest.mark.django_db()
def test_update_stats_image_tags_keeps_every_tag_and_filter_works(user, mocker):
    # "popular-*" tags appear on 2 images, "rare-*" on 1 — 20 distinct tags total.
    popular = [f'popular-{i}' for i in range(10)]
    rare = [f'rare-{i}' for i in range(10)]
    _make_image('a', user, tags=popular)
    _make_image('b', user, tags=popular)
    _make_image('c', user, tags=rare)
    OS.client.indices.refresh(index=OSImage.INDEX)

    # page_size=7 forces multiple composite-agg pages for the 20 tags.
    _patch_exhaustive_counts(mocker, page_size=7)
    Stats.objects.update_stats_image_tags()

    counts = dict(Tag.objects.values_list('name', 'image_count'))
    assert counts == {**{t: 2 for t in popular}, **{t: 1 for t in rare}}

    # Filtering by the rarest tags keeps working — this is the prod regression: a top-N
    # sync deleted their Tag rows and the filter 400ed with "One or more tags do not exist".
    client = _logged_in_client(user)
    response = client.get(reverse('api:images-list'), {'tags': 'rare-0'})
    assert response.status_code == 200
    assert len(response.json()['results']) == 1


@pytest.mark.django_db()
def test_update_stats_image_tags_skips_cleanup_when_truncated(user, mocker):
    tags = [f'tag-{i}' for i in range(20)]
    _make_image('a', user, tags=tags)
    OS.client.indices.refresh(index=OSImage.INDEX)
    assert Tag.objects.count() == 20  # ingestion created all rows

    # Cap below the cardinality: counts come back truncated, so cleanup must not run —
    # deleting "unseen" tags here is exactly the bug this guards against.
    _patch_exhaustive_counts(mocker, page_size=5, max_buckets=5)
    Stats.objects.update_stats_image_tags()

    assert Tag.objects.count() == 20


@pytest.mark.django_db()
def test_update_stats_image_tags_deletes_stale_tags_after_grace_period(user):
    _make_image('a', user, tags=['kept'])
    OS.client.indices.refresh(index=OSImage.INDEX)

    Tag.objects.create(name='gone')  # not on any image
    Tag.objects.filter(name='gone').update(date_created=timezone.now() - datetime.timedelta(hours=1))
    Tag.objects.create(name='fresh')  # not on any image either, but inside the grace period

    Stats.objects.update_stats_image_tags()

    names = set(Tag.objects.values_list('name', flat=True))
    assert 'kept' in names
    assert 'gone' not in names  # stale and past the grace period -> cleaned up
    assert 'fresh' in names  # protected: could have been ingested after the agg snapshot
