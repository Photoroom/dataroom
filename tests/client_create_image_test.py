import uuid

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import override_settings

from backend.dataroom.models import Tag
from backend.dataroom.models.attributes import AttributesField, AttributesSchema
from backend.dataroom.models.os_image import OSImage, OSImageMeta, OSAttributes, OSLatents
from dataroom_client import DataRoomFile, DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_from_local_path(DataRoom, tests_path, user):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    image_id = str(uuid.uuid4())
    image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test')
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.id == image_id
    assert instance.source == 'test'
    assert instance.image == f'images/{image_id}/original.png'
    assert isinstance(instance.meta, OSImageMeta)
    assert instance.date_created is not None
    assert instance.date_updated is not None
    assert instance.is_deleted is False
    assert instance.author == user.email
    assert instance.image_hash.startswith('sha256:')
    assert len(instance.image_hash) == 7 + 64
    assert instance.width == 180
    assert instance.height == 180
    assert instance.short_edge == 180
    assert instance.aspect_ratio == 1.0
    assert instance.aspect_ratio_fraction == '1:1'
    assert instance.thumbnail is None
    assert instance.thumbnail_file is None
    assert instance.original_url is None
    assert instance.tags == []
    assert instance.coca_embedding_exists is False
    assert instance.coca_embedding_vector is None
    assert instance.coca_embedding_author is None
    assert isinstance(instance.latents, OSLatents)
    assert isinstance(instance.attributes, OSAttributes)
    assert instance.pil_image.height == 180
    assert instance.pil_image.width == 180
    assert instance.pil_thumbnail is None


@pytest.mark.asyncio
@pytest.mark.django_db
@override_settings(IMAGE_ID_MAX_LENGTH=10, FILENAME_MAX_LENGTH=30)
async def test_create_image_with_long_filename(DataRoom, tests_path, user):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    # just long enough
    image_id = '0' * settings.IMAGE_ID_MAX_LENGTH
    image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test')
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.id == image_id
    assert instance.image == f'images/{image_id}/original.png'

    image_instance = await sync_to_async(OSImage.objects.get)(id=image['id'])
    await sync_to_async(image_instance.delete)()

    # too long
    image_id = '0' * (settings.IMAGE_ID_MAX_LENGTH + 1)
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test')
    assert "Ensure this field has no more than 10 characters" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_from_url_without_id(DataRoom):
    image_url = 'https://storyblok-cdn.photoroom.com/f/191576/1200x800/4e54b928ef/remove_background.webp'
    image = await DataRoom.create_image(image_url=image_url, source='test')
    assert image['original_url'] == image_url
    assert image['id']
    created_image_id = image['id']

    response = await DataRoom.get_images()
    assert len(response) == 1

    # creating the image again, should return the same image
    image = await DataRoom.create_image(image_url=image_url, source='test')
    assert image['original_url'] == image_url
    assert image['id'] == created_image_id  # still the ID from above

    response = await DataRoom.get_images()
    assert len(response) == 1


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_from_url_avoids_duplicates(DataRoom):
    image_url = 'https://storyblok-cdn.photoroom.com/f/191576/1200x800/4e54b928ef/remove_background.webp'
    image_id = str(uuid.uuid4())
    image = await DataRoom.create_image(image_id=image_id, image_url=image_url, source='test')
    assert image['original_url'] == image_url
    assert image['id'] == image_id

    response = await DataRoom.get_images()
    assert len(response) == 1

    # creating the image again, should return the same image
    image = await DataRoom.create_image(image_id=str(uuid.uuid4()), image_url=image_url, source='test')
    assert image['original_url'] == image_url
    assert image['id'] == image_id  # still the ID from above

    response = await DataRoom.get_images()
    assert len(response) == 1

    # if the image is marked as deleted, still return the same image
    await DataRoom.delete_image(image_id)
    image = await DataRoom.create_image(image_id=str(uuid.uuid4()), image_url=image_url, source='test')
    assert image['original_url'] == image_url
    assert image['id'] == image_id  # still the ID from above

    response = await DataRoom.get_images()
    assert len(response) == 0  # because it's deleted
    assert OSImage.all_objects.search().count() == 1


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_source_is_required(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='1', image_file=image_file, source=None)
    assert 'Please provide a "source" field' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='1', image_file=image_file, source='')
    assert 'Please provide a "source" field' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_id_is_required(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=None, image_file=image_file, source='test')
    assert 'Please provide either an "image_id" or "image_url" field' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='', image_file=image_file, source='test')
    assert 'Please provide either an "image_id" or "image_url" field' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=' ', image_file=image_file, source='test')
    assert 'This field may not be blank' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_id_valid_chars(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='fail.', image_file=image_file, source='test')
    assert 'Can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='fa il', image_file=image_file, source='test')
    assert 'Can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='fa/il', image_file=image_file, source='test')
    assert 'Can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_same_id_not_possible(DataRoom, tests_path, os_image):
    response = await DataRoom.get_images()
    assert len(response) == 1
    image_id = response[0]['id']

    # creating the image again, should raise an error
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test')
    assert 'The provided ID already exists in the database' in str(excinfo.value)

    response = await DataRoom.get_images()
    assert len(response) == 1
    assert response[0]['id'] == image_id


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_same_file_not_possible(DataRoom, tests_path, image_logo):
    response = await DataRoom.get_images()
    assert len(response) == 1
    image_id = response[0]['id']

    # creating the image again, should raise an error
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id='other-ID', image_file=image_file, source='test')
    assert 'Image with the same hash already exists in the database' in str(excinfo.value)

    response = await DataRoom.get_images()
    assert len(response) == 1
    assert response[0]['id'] == image_id


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_similar_file_is_possible(DataRoom, tests_path, image_logo):
    response = await DataRoom.get_images()
    assert len(response) == 1

    # very similar image
    image_file = DataRoomFile.from_path(tests_path / 'images/logo_alt.png')

    # alter the hash to be the same
    image_logo.image_hash = OSImage.get_image_hash(image_file.bytes_io)
    await sync_to_async(image_logo.save)(fields=['image_hash'])

    # creating the image with an almost identical image again, should pass
    image = await DataRoom.create_image(image_id='other-ID', image_file=image_file, source='test')

    response = await DataRoom.get_images()
    assert len(response) == 2


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_from_wrong_url(DataRoom):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_image(
            image_id=str(uuid.uuid4()),
            image_url='https://www.example.com/does-not-exist.jpg',
            source='test',
        )
    assert 'Unable to download image from URL' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_attributes(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image_id = str(uuid.uuid4())

    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    # no attributes defined
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(
            image_id=image_id, image_file=image_file, source='test', attributes={'color': 'red'},
        )
    assert ('{"attributes":["Schema validation error: Additional properties are not '
            'allowed (\'color\' was unexpected)"]}') in str(excinfo.value)

    # define some attributes
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='required', field_type='boolean', is_required=True)
    await sync_to_async(AttributesField.objects.create)(name='date', field_type='string', string_format='date')

    # force invalidate cache
    AttributesSchema.invalidate_cache()

    # missing required field
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(
            image_id=image_id, image_file=image_file, source='test', attributes={'color': 'red'},
        )
    assert '{"attributes":["Schema validation error: \'required\' is a required property"]}' in str(excinfo.value)

    # wrong date format
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(
            image_id=image_id, image_file=image_file, source='test', attributes={'required': True, 'date': 'today'},
        )
    assert '{"attributes":["Schema validation error: \'today\' is not a \'date\'"]}' in str(excinfo.value)

    # correct
    image = await DataRoom.create_image(
        image_id=image_id, image_file=image_file, source='test', attributes={'required': True, 'date': '2024-02-01'},
    )
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.attributes.to_json() == {'required': True, 'date': '2024-02-01'}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_tags(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    await sync_to_async(Tag.objects.create)(name='existing')

    image_id = str(uuid.uuid4())
    image = await DataRoom.create_image(
        image_id=image_id, image_file=image_file, source='test', tags=['existing', 'new', '2'],
    )
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.tags == ['existing', 'new', '2']

    # new Tag instances should be created automatically
    assert await sync_to_async(Tag.objects.all().count)() == 3


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_empty_tags(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    image_id = str(uuid.uuid4())
    image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', tags=[])
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.tags == []


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_tags_invalid(DataRoom, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    image_id = str(uuid.uuid4())
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', tags=['a:b'])
    assert 'Tags can only contain alphanumeric characters' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_images_in_bulk_wrong(DataRoom, tests_path, image_logo):
    existing_image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    new_image_file = DataRoomFile.from_path(tests_path / 'images/logo_alt.png')
    new_image_file_2 = DataRoomFile.from_path(tests_path / 'images/logo_small.png')

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([])
    assert 'This field is required' in str(excinfo.value)

    # invalid ID
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'fa il',
            'source': 'test',
            'image_url': 'https://www.example.com/does-not-exist.jpg',
        }])
    assert 'Can only contain alphanumeric characters, dashes, and underscores' in str(excinfo.value)

    # wrong URL
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'new',
            'source': 'test',
            'image_url': 'https://www.example.com/does-not-exist.jpg',
        }, {
            'id': image_logo.id,
            'source': 'test',
            'image_url': 'https://www.example.com/does-not-exist.jpg',
        }])
    assert f'Unable to download image from URL' in str(excinfo.value)

    # existing ID
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'new',
            'source': 'test',
            'image_file': new_image_file,
        }, {
            'id': image_logo.id,
            'source': 'test',
            'image_file': new_image_file_2,
        }])
    assert f"Images with IDs '{image_logo.id}' already exist" in str(excinfo.value)

    # existing hash
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'new',
            'source': 'test',
            'image_file': new_image_file,
        }, {
            'id': 'new_2',
            'source': 'test',
            'image_file': existing_image_file,
        }])
    assert f"Image hashes with IDs '{image_logo.id}' already exist" in str(excinfo.value)

    # same ID in batch
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'new',
            'source': 'test',
            'image_file': new_image_file,
        }, {
            'id': 'new',
            'source': 'test',
            'image_file': new_image_file_2,
        }])
    assert f"Image with ID 'new' appears multiple times in bulk" in str(excinfo.value)

    # same hash in batch
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_images([{
            'id': 'new',
            'source': 'test',
            'image_file': new_image_file,
        }, {
            'id': 'new_2',
            'source': 'test',
            'image_file': new_image_file,
        }])
    assert f"Image hash with ID 'new_2' appears multiple times in bulk" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_images_in_bulk(DataRoom, tests_path):
    file_logo = DataRoomFile.from_path(tests_path / 'images/logo.png')
    file_girl = DataRoomFile.from_path(tests_path / 'images/girl.jpg')
    file_perfume = DataRoomFile.from_path(tests_path / 'images/perfume.jpg')

    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    AttributesSchema.invalidate_cache()

    response = await DataRoom.create_images([
        {'id': 'logo', 'source': 'test1', 'image_file': file_logo},
        {'id': 'girl', 'source': 'test2', 'image_file': file_girl, 'tags': ['one', 'two']},
        {
            'id': 'perfume',
            'source': 'test3',
            'image_file': file_perfume,
            'tags': ['three'],
            'attributes': {'color': 'red'},
         },
    ])

    assert response == {
        'created': ['logo', 'girl', 'perfume'],
    }

    images = await DataRoom.get_images()
    assert len(images) == 3
    for image in images:
        if image['id'] == 'logo':
            assert image['source'] == 'test1'
            assert image['tags'] == []
        elif image['id'] == 'girl':
            assert image['source'] == 'test2'
            assert image['tags'] == ['one', 'two']
        elif image['id'] == 'perfume':
            assert image['source'] == 'test3'
            assert image['tags'] == ['three']
            assert image['attributes'] == {'color': 'red'}
