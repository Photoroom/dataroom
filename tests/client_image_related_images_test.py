import uuid
import pytest

from asgiref.sync import sync_to_async
from django.conf import settings

from backend.dataroom.models.os_image import OSImage
from dataroom_client.dataroom_client.client import DataRoomFile, DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_related_images(DataRoom, tests_path, image_logo_alt, user):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    image_id = str(uuid.uuid4())
    related_images_json = {
        'self': image_id,
        'other_logo': image_logo_alt.id,
        'missing': 'doesnotexist',
    }
    image = await DataRoom.create_image(
        image_id=image_id,
        image_file=image_file,
        source='test',
        related_images=related_images_json,
    )
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.id == image_id
    assert instance.related_images.to_json() == related_images_json
    assert instance.related_images.to_doc() == {'related_images': related_images_json}

    image = await DataRoom.get_image(image_id, all_fields=True)
    assert image['related_images'] == related_images_json


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_related_images_invalid(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image_id = str(uuid.uuid4())

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images=[])
    assert 'Expected a dictionary of items' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            '': '',
        })
    assert '"related_images":{"":["This field may not be blank."]' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            '': 'fail',
        })
    assert 'Key in related_images must be at least 1 characters long' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            'no spaces allowed': 'fail',
        })
    assert 'Key in related_images can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            'test': 'no spaces allowed',
        })
    assert 'Can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)

    related_type = 'a' * (settings.RELATED_IMAGE_TYPE_MAX_LENGTH + 1)
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            related_type: 'ok',
        })
    assert f'Key in related_images can only be {settings.RELATED_IMAGE_TYPE_MAX_LENGTH} characters long' in str(excinfo.value)
    
    image_id = '0' * (settings.IMAGE_ID_MAX_LENGTH + 1)
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', related_images={
            'ok': image_id,
        })
    assert f'Ensure this field has no more than {settings.IMAGE_ID_MAX_LENGTH} characters' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_related_images(DataRoom, image_logo, image_logo_alt):
    related_images_json = {
        'other_logo': image_logo_alt.id,
        'missing': 'doesnotexist',
    }
    image = await DataRoom.update_image(
        image_id=image_logo.id,
        related_images=related_images_json,
    )
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['related_images'] == related_images_json

    # updates will merge with existing object
    new_related_images_json = {
        'new': 'new_id',
        'missing': 'doesnotexist2',
    }
    image = await DataRoom.update_image(
        image_id=image_logo.id,
        related_images=new_related_images_json,
    )
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['related_images'] == {
        'other_logo': image_logo_alt.id,
        'new': 'new_id',
        'missing': 'doesnotexist2',
    }



@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_related_images(DataRoom, image_logo, image_logo_alt):
    response = await DataRoom.get_related_images(image_logo.id)
    assert response == []

    image = await DataRoom.update_image(
        image_id=image_logo.id,
        related_images={
            'other_logo': image_logo_alt.id,
            'missing': 'doesnotexist',
        },
    )

    response = await DataRoom.get_related_images(image_logo.id)
    assert response[0]['name'] == 'other_logo'
    assert response[0]['image_id'] == image_logo_alt.id
    assert response[0]['image']['source'] == 'test'
    assert 'related_images' not in response[0]['image']
    assert response[1]['name'] == 'missing'
    assert response[1]['image_id'] == 'doesnotexist'
    assert response[1]['image'] is None


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_related_images_circular_relation(DataRoom, image_logo, image_logo_alt):
    response = await DataRoom.get_related_images(image_logo.id)
    assert response == []

    image = await DataRoom.update_image(
        image_id=image_logo.id,
        related_images={
            'other_logo': image_logo_alt.id,
        },
    )

    image = await DataRoom.update_image(
        image_id=image_logo_alt.id,
        related_images={
            'other_logo': image_logo.id,
        },
    )

    response = await DataRoom.get_related_images(image_logo.id)
    assert response[0]['name'] == 'other_logo'
    assert response[0]['image_id'] == image_logo_alt.id
    assert response[0]['image']['source'] == 'test'
    assert 'related_images' not in response[0]['image']

    response = await DataRoom.get_related_images(image_logo_alt.id)
    assert response[0]['name'] == 'other_logo'
    assert response[0]['image_id'] == image_logo.id
    assert response[0]['image']['source'] == 'test'
    assert 'related_images' not in response[0]['image']

