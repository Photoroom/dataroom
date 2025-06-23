import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.models import Tag, LatentType
from backend.dataroom.models.attributes import AttributesField, AttributesSchema
from dataroom_client import DataRoomError, DataRoomFile
from tests.utils import get_random_vector


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image(DataRoom, image_logo):
    images = await DataRoom.get_images()
    image = images[0]
    assert image['source'] == 'test'
    assert image['attributes'] == {}
    old_date_updated = image['date_updated']

    await DataRoom.update_image(image_id=image['id'], source='test2')
    images = await DataRoom.get_images()
    image = images[0]
    assert image['source'] == 'test2'
    assert image['date_updated'] != image['date_created']
    assert image['date_updated'] != old_date_updated


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_requires_source(DataRoom, image_logo):
    images = await DataRoom.get_images()
    image = images[0]
    assert image['source'] == 'test'

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image['id'], source='')
    assert '{"source":["This field may not be blank."]}' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image['id'], source=' ')
    assert '{"source":["This field may not be blank."]}' in str(excinfo.value)

    # not providing source is fine, keeps the old value
    await DataRoom.update_image(image_id=image['id'], source=None)
    image = await DataRoom.get_image(image['id'])
    assert image['source'] == 'test'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_attributes(DataRoom, image_logo):
    images = await DataRoom.get_images()
    image = images[0]
    image_id = image['id']
    assert image['source'] == 'test'
    assert image['attributes'] == {}

    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    # no attributes defined
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_id, source='test', attributes={'color': 'blue'})
    assert ('{"attributes":["Schema validation error: Additional properties are not '
            'allowed (\'color\' was unexpected)"]}') in str(excinfo.value)

    # attribute does not exist
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_id, source='test', attributes={'fail': True})
    assert (
        'Schema validation error: Additional properties are not allowed (\'fail\' was unexpected)"'
        in str(excinfo.value)
    )

    # define some attributes
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='required', field_type='boolean', is_required=True)
    await sync_to_async(AttributesField.objects.create)(name='date', field_type='string', string_format='date')

    # force invalidate cache
    AttributesSchema.invalidate_cache()

    # missing required field
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_id, source='test', attributes={'color': 'red'})
    assert '{"attributes":["Schema validation error: \'required\' is a required property"]}' in str(excinfo.value)

    # wrong date format
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_id, source='test', attributes={'required': True, 'date': 'today'})
    assert '{"attributes":["Schema validation error: \'today\' is not a \'date\'"]}' in str(excinfo.value)

    # correct
    await DataRoom.update_image(image_id=image_id, source='test', attributes={'required': True, 'date': '2024-02-01'})

    images = await DataRoom.get_images()
    image = images[0]
    assert image['source'] == 'test'
    assert image['attributes'] == {'required': True, 'date': '2024-02-01'}

    # adding another attribute does not discard the old ones
    await DataRoom.update_image(image_id=image_id, attributes={'color': 'red', 'required': True})

    images = await DataRoom.get_images()
    image = images[0]
    assert image['source'] == 'test'
    assert image['attributes'] == {'required': True, 'date': '2024-02-01', 'color': 'red'}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_latents(DataRoom, tests_path, image_logo):
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')
    latent_file_2 = DataRoomFile.from_path(tests_path / 'images/logo_alt.png')

    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['latents'] == []

    # missing latent_type
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{}])
    assert "Missing 'latent_type' field in latent" in str(excinfo.value)

    # missing file
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{
            "latent_type": "test",
        }])
    assert "Missing 'file' field in latent" in str(excinfo.value)

    # wrong file type
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{
            "latent_type": "test",
            "file": "not a file",
        }])
    assert "Property 'file' must be a DataRoomFile" in str(excinfo.value)

    # same latent multiple times
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{
            "latent_type": "test",
            "file": latent_file,
        }, {
            "latent_type": "test",
            "file": latent_file,
        }])
    assert "Latent type 'test' appears multiple times in update" in str(excinfo.value)

    # LatentType doesn't exist
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{
            "latent_type": "embedding",
            "file": latent_file,
        }, {
            "latent_type": "mask",
            "file": mask_file,
        }])
    assert "Latent type 'embedding' does not exist" in str(excinfo.value)

    # create one LatentType
    await sync_to_async(LatentType.objects.create)(name='embedding', is_mask=False)

    # other still doesn't exist
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_image(image_id=image_logo.id, latents=[{
            "latent_type": "embedding",
            "file": latent_file,
        }, {
            "latent_type": "mask",
            "file": mask_file,
        }])
    assert "Latent type 'mask' does not exist" in str(excinfo.value)

    # create all LatentTypes
    await sync_to_async(LatentType.objects.create)(name='mask', is_mask=True)

    # correct
    await DataRoom.update_image(image_id=image_logo.id, latents=[{
        "latent_type": "embedding",
        "file": latent_file,
    }, {
        "latent_type": "mask",
        "file": mask_file,
    }])
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert sorted(image['latents'], key=lambda x: x['latent_type']) == [{
        "latent_type": "embedding",
        "file_direct_url": "/media/images/test-logo/latent_embedding.txt",
        "is_mask": False,
    }, {
        "latent_type": "mask",
        "file_direct_url": "/media/images/test-logo/latent_mask.png",
        "is_mask": True,
    }]

    # LatentTypes are created
    latent_types = await sync_to_async(list)(LatentType.objects.all())
    assert len(latent_types) == 2
    assert latent_types[0].name == 'embedding'
    assert latent_types[0].is_mask is False
    assert latent_types[1].name == 'mask'
    assert latent_types[1].is_mask is True

    # overwrite
    await DataRoom.update_image(image_id=image_logo.id, latents=[{
        "latent_type": "embedding",
        "file": latent_file_2,
    }])
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert sorted(image['latents'], key=lambda x: x['latent_type']) == [{
        "latent_type": "embedding",
        "file_direct_url": "/media/images/test-logo/latent_embedding.png",
        "is_mask": False,
    }, {
        "latent_type": "mask",
        "file_direct_url": "/media/images/test-logo/latent_mask.png",
        "is_mask": True,
    }]

    # LatentTypes are still the same
    latent_types = await sync_to_async(list)(LatentType.objects.all())
    assert len(latent_types) == 2


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_latents_and_attributes(DataRoom, tests_path, image_logo):
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    AttributesSchema.invalidate_cache()
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    await sync_to_async(LatentType.objects.create)(name='embedding', is_mask=False)

    await DataRoom.update_image(
        image_id=image_logo.id,
        latents=[{
            "latent_type": "embedding",
            "file": latent_file,
        }],
        attributes={'color': 'red'},
    )
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['latents'] == [{
        "latent_type": "embedding",
        "file_direct_url": "/media/images/test-logo/latent_embedding.txt",
        "is_mask": False,
    }]
    assert image['attributes'] == {'color': 'red'}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_tags(DataRoom, image_logo):
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == []

    await DataRoom.update_image(image_id=image['id'], source='test', tags=['one', 'two'])
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == ['one', 'two']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_tags_replaces_existing(DataRoom, image_logo):
    tag = await sync_to_async(Tag.objects.create)(name='initial')
    image_logo.tags = [tag.name]
    await sync_to_async(image_logo.save)(fields=['tags'])
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == ['initial']

    await DataRoom.update_image(image_id=image['id'], source='test', tags=None)
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == ['initial']

    await DataRoom.update_image(image_id=image['id'], source='test', tags=['new'])
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == ['new']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_tags_clear(DataRoom, image_logo):
    tag = await sync_to_async(Tag.objects.create)(name='gone')
    image_logo.tags = [tag.name]
    await sync_to_async(image_logo.save)(fields=['tags'])
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == ['gone']

    await DataRoom.update_image(image_id=image['id'], source='test', tags=[])
    images = await DataRoom.get_images()
    image = images[0]
    assert image['tags'] == []


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_bulk_update_wrong(DataRoom):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_images([])
    assert 'Empty list provided' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.update_images([{'id': 'fail'}])
    assert 'Images with IDs \\"fail\\" were not found' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_bulk_update(DataRoom, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    images = await DataRoom.get_images()
    assert len(images) == 5

    await sync_to_async(AttributesField.objects.create)(name='example', field_type='integer')
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    AttributesSchema.invalidate_cache()

    vector1 = get_random_vector()
    vector2 = get_random_vector()
    vector3 = get_random_vector()
    vector4 = get_random_vector()
    vector5 = get_random_vector()

    result = await DataRoom.update_images([
        {
            'id': image_logo.id,
            'source': 'test1',
            'attributes': {'example': 1},
            'tags': ['test1'],
            'coca_embedding': "[" + ",".join([str(x) for x in vector1]) + "]"
        },
        {
            'id': image_logo_alt.id,
            'source': 'test2',
            'attributes': {'example': 2},
            'tags': ['test2'],
            'coca_embedding': "[" + ",".join([str(x) for x in vector2]) + "]"
        },
        {
            'id': image_logo_small.id,
            'source': 'test3',
            'attributes': {'example': 3},
            'tags': ['test3'],
            'coca_embedding': "[" + ",".join([str(x) for x in vector3]) + "]"
        },
        {
            'id': image_girl.id,
            'source': 'test4',
            'attributes': {'example': 4},
            'tags': ['test4'],
            'coca_embedding': "[" + ",".join([str(x) for x in vector4]) + "]"
        },
        {
            'id': image_perfume.id,
            'source': 'test5',
            'attributes': {'example': 5},
            'tags': ['test5'],
            'coca_embedding': "[" + ",".join([str(x) for x in vector5]) + "]"
        },
    ])

    assert result == {
        'updated': [
            image_logo.id,
            image_logo_alt.id,
            image_logo_small.id,
            image_girl.id,
            image_perfume.id,
        ],
    }

    images = await DataRoom.get_images(all_fields=True)
    assert len(images) == 5
    for image in images:
        if image['id'] == image_logo.id:
            assert image['source'] == 'test1'
            assert image['attributes'] == {'example': 1}
            assert image['tags'] == ['test1']
            assert round(image['coca_embedding']['vector'][0], 6) == round(vector1[0], 6)
        elif image['id'] == image_logo_alt.id:
            assert image['source'] == 'test2'
            assert image['attributes'] == {'example': 2}
            assert image['tags'] == ['test2']
            assert round(image['coca_embedding']['vector'][0], 6) == round(vector2[0], 6)
        elif image['id'] == image_logo_small.id:
            assert image['source'] == 'test3'
            assert image['attributes'] == {'example': 3}
            assert image['tags'] == ['test3']
            assert round(image['coca_embedding']['vector'][0], 6) == round(vector3[0], 6)
        elif image['id'] == image_girl.id:
            assert image['source'] == 'test4'
            assert image['attributes'] == {'example': 4}
            assert image['tags'] == ['test4']
            assert round(image['coca_embedding']['vector'][0], 6) == round(vector4[0], 6)
        elif image['id'] == image_perfume.id:
            assert image['source'] == 'test5'
            assert image['attributes'] == {'example': 5}
            assert image['tags'] == ['test5']
            assert round(image['coca_embedding']['vector'][0], 6) == round(vector5[0], 6)

    # another bulk update overwrites tags but not attributes
    result = await DataRoom.update_images([
        {'id': image_logo.id, 'source': 'bulk_update', 'attributes': {'color': 'red'}, 'tags': ['updated1']},
        {'id': image_logo_alt.id, 'source': 'bulk_update'},
        {'id': image_logo_small.id, 'source': 'bulk_update'},
        {'id': image_girl.id, 'source': 'bulk_update'},
        {'id': image_perfume.id, 'source': 'bulk_update'},
    ])

    images = await DataRoom.get_images()
    assert len(images) == 5
    for image in images:
        assert image['source'] == 'bulk_update'
        if image['id'] == image_logo.id:
            assert image['attributes'] == {'example': 1, 'color': 'red'}
            assert image['tags'] == ['updated1']
        elif image['id'] == image_logo_alt.id:
            assert image['attributes'] == {'example': 2}
            assert image['tags'] == ['test2']
        elif image['id'] == image_logo_small.id:
            assert image['attributes'] == {'example': 3}
            assert image['tags'] == ['test3']
        elif image['id'] == image_girl.id:
            assert image['attributes'] == {'example': 4}
            assert image['tags'] == ['test4']
        elif image['id'] == image_perfume.id:
            assert image['attributes'] == {'example': 5}
            assert image['tags'] == ['test5']
