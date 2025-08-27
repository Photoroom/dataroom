from freezegun import freeze_time
import pytest
from django.core.files import File
import datetime

from django.urls import reverse
from django.test import Client

from backend.dataroom.choices import DuplicateState
from backend.dataroom.models import AttributesField, AttributesSchema, LatentType
from backend.dataroom.models.os_image import OSAttributes, OSLatents
from backend.dataroom.models.tag import Tag
from backend.dataroom.models.stats import Stats
from dataroom_client import DataRoomFile


@pytest.mark.django_db
def test_stats_api(user, tests_path, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    from backend.dataroom.models.os_image import OSImage

    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')

    client = Client()
    client.login(username=user.email, password='123')

    tag = Tag.objects.create(name='test')

    # define some attributes
    AttributesField.objects.create(name='color', field_type='string', is_indexed=True)
    AttributesField.objects.create(name='has_background', field_type='boolean', is_indexed=True)
    AttributesSchema.invalidate_cache()

    # create LatentType
    LatentType.objects.create(name='embedding', is_mask=False)

    # update image
    image_logo.thumbnail = None
    image_logo.source = 'new'
    image_logo.coca_embedding_exists = False
    image_logo.coca_embedding_vector = None
    image_logo.coca_embedding_author = None
    image_logo.tags = [tag.name]
    image_logo.attributes = OSAttributes.from_json({
        "color": "red",
    })
    image_logo.latents = OSLatents.from_json([{
        'latent_type': 'embedding',
        'file': File(latent_file.bytes_io, name=latent_file.filename),
    }])
    image_logo.save(
        fields=['thumbnail', 'source', 'tags', 'coca_embedding', 'attributes', 'latents'], latent_types=['embedding'],
    )

    # delete image_logo_alt
    image_logo_alt.is_deleted = True
    image_logo_alt.duplicate_state = DuplicateState.DUPLICATE
    image_logo_alt.save(fields=['is_deleted', 'duplicate_state'])

    # mark image_logo_small as duplicate
    image_logo_small.duplicate_state = DuplicateState.DUPLICATE
    image_logo_small.save(fields=['duplicate_state'])

    # get stats
    date_updated = datetime.datetime(2024, 11, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
    date_updated_str = date_updated.isoformat().replace('+00:00', 'Z')
    with freeze_time(date_updated):
        Stats.objects.update_all_stats()

    assert OSImage.objects.search().count() == 4
    assert OSImage.all_objects.search().count() == 5

    url = reverse('api:stats-totals')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {
        'images': {
            'current': 4,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
    }

    url = reverse('api:stats-queue')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {
        'total_images': {
            'current': 4,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_missing_thumbnail': {
            'current': 1,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_missing_coca_embedding': {
            'current': 1,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_missing_duplicate_state': {
            'current': 2,  # image_logo has no embedding so it's excluded
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_marked_as_duplicates': {
            'current': 1,  # deleted duplicates are not counted
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_marked_for_deletion': {
            'current': 1,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
        'images_with_disabled_latents': {
            'current': 0,
            'date_updated': date_updated_str,
            'prev': 0,
            'prev_date_updated': None,
            'change_per_second': 0,
            'time_left': None,
        },
    }

    url = reverse('api:stats-image_sources')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {
        'test': 3,
        'new': 1,
    }

    url = reverse('api:stats-image_aspect_ratio_fractions')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {
        '1:1': 2,
        '3:2': 1,
        '3:4': 1,
    }

    url = reverse('api:stats-attributes')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == [{
        'name': 'color',
        'field_type': 'string',
        'string_format': None,
        'is_enabled': True,
        'is_indexed': True,
        'image_count': 1,
    }, {
        'name': 'has_background',
        'field_type': 'boolean',
        'string_format': None,
        'is_enabled': True,
        'is_indexed': True,
        'image_count': 0,
    }]

    url = reverse('api:stats-latent_types')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == [{
        'name': 'embedding',
        'is_mask': False,
        'image_count': 1,
    }]

    url = reverse('api:tags-list')
    response = client.get(url)
    assert response.status_code == 200
    results = response.json()['results']
    assert len(results) == 1
    assert results[0]['name'] == 'test'
    assert results[0]['image_count'] == 1

    assert Stats.objects.get_images_missing_tags() == {
        'current': 3,
        'date_updated': date_updated,
        'prev': 0,
        'prev_date_updated': None,
        'change_per_second': 0,
            'time_left': None,
    }

    # ---------------- test updates per second

    image_girl.duplicate_state = DuplicateState.ORIGINAL
    image_girl.save(fields=['duplicate_state'])

    # get stats again
    new_date_updated = datetime.datetime(2024, 11, 21, 12, 0, 2, tzinfo=datetime.timezone.utc)
    with freeze_time(new_date_updated):
        Stats.objects.update_all_stats()

    # thumbnail count should be updated
    assert Stats.objects.get_images_missing_duplicate_state() == {
        'current': 1,
        'date_updated': new_date_updated,
        'prev': 2,
        'prev_date_updated': date_updated,
        'change_per_second': -0.5,  # after 2 seconds 1 was removed
        'time_left': datetime.timedelta(seconds=2),
    }
