import asyncio
import datetime

from freezegun import freeze_time
import pytest
from asgiref.sync import sync_to_async

from backend.api.pagination import API_MAX_PAGE_SIZE
from backend.dataroom.models import AttributesSchema, AttributesField, Tag
from backend.dataroom.choices import DuplicateState
from backend.dataroom.models.os_image import OSAttributes, OSImage
from dataroom_client import DataRoomFile, DataRoomError, DataRoomClient
from dataroom_client.dataroom_client.client import ClientDuplicateState


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_wrong_token(live_server):
    DataRoom = DataRoomClient(
        api_url=live_server.url + "/api/",
        api_key='this-token-is-wrong',
    )
    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images()
    assert '403 Forbidden' in str(excinfo.value)
    assert 'Invalid token' in str(excinfo.value.response.content)
    assert excinfo.value.response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images(DataRoom, image_logo):
    response = await DataRoom.get_images()
    assert len(response) == 1
    assert response[0]['id'] == str(image_logo.id)
    assert 'images/test-logo/original.png' in response[0]['image_direct_url']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_cache(DataRoom, tests_path, image_perfume, image_girl):
    # cache the response for 3 seconds
    response = await DataRoom.get_images(fields='id', page_size=1, cache_ttl=2)
    assert len(response) == 2

    # create an image
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image = await DataRoom.create_image(image_id='logo', image_file=image_file, source='test')

    # the cache should still return the old images
    response = await DataRoom.get_images(fields='id', page_size=1, cache_ttl=2)
    assert len(response) == 2

    # wait for the cache to expire
    await asyncio.sleep(2)

    # the cache should now return the new image
    response = await DataRoom.get_images(fields='id', page_size=1, cache_ttl=2)
    assert len(response) == 3


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_limit(DataRoom, image_logo, image_girl, image_perfume):
    response = await DataRoom.get_images()
    assert len(response) == 3
    response = await DataRoom.get_images(limit=1)
    assert len(response) == 1


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_fields(DataRoom, os_image):
    response = await DataRoom.get_images(fields=['id'])
    assert len(response) == 1
    assert response[0] == {'id': str(os_image.id)}

    response = await DataRoom.get_images(fields=['id', 'tags'])
    assert len(response) == 1
    assert response[0] == {'id': str(os_image.id), 'tags': []}

    response = await DataRoom.get_images(fields=['coca_embedding'])
    assert len(response) == 1
    assert response[0]['id'] == str(os_image.id)
    assert response[0]['coca_embedding'] is None


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_all_fields(DataRoom, os_image):
    response = await DataRoom.get_images(all_fields=True)
    assert len(response) == 1
    assert list(response[0].keys()) == [
        'id',
        'source',
        'image',
        'image_direct_url',
        'date_created',
        'date_updated',
        'author',
        'image_hash',
        'width',
        'height',
        'short_edge',
        'pixel_count',
        'aspect_ratio',
        'aspect_ratio_fraction',
        'thumbnail',
        'thumbnail_direct_url',
        'thumbnail_error',
        'original_url',
        'tags',
        'coca_embedding',
        'latents',
        'attributes',
        'duplicate_state',
        'related_images',
        'datasets',
    ]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_include_fields(DataRoom, image_logo):
    # default response has no "thumbnail" field
    response = await DataRoom.get_images()
    assert 'thumbnail' not in response[0]

    response = await DataRoom.get_images(include_fields=['thumbnail', 'thumbnail_direct_url'])
    assert 'thumbnail' in response[0]
    assert response[0]['thumbnail'] == '/media/images/test-logo/thumbnail.png'
    assert response[0]['thumbnail_direct_url'] == '/media/images/test-logo/thumbnail.png'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_exclude_fields(DataRoom, image_logo):
    response = await DataRoom.get_images()
    assert 'width' in response[0]

    response = await DataRoom.get_images(exclude_fields=['width'])
    assert 'width' not in response[0]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_image(DataRoom, image_logo):
    response = await DataRoom.get_image(image_logo.id)
    assert response['id'] == str(image_logo.id)

    response = await DataRoom.get_image(image_logo.id, fields=['id', 'width'])
    assert response == {
        'id': str(image_logo.id),
        'width': 180,
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_add_image_attributes_validates_schema(DataRoom, image_logo):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='background', field_type='string', is_required=True)

    image_logo.attributes = await sync_to_async(OSAttributes.from_json)({'color': 'blue', 'background': 'transparent'})
    await sync_to_async(image_logo.save)(fields=['attributes'])

    # "user" field doesn't exist
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.add_image_attributes(image_id=str(image_logo.id), attributes={'color': 'red', 'user': 'john'})
    assert 'Additional properties are not allowed (\'user\' was unexpected)' in str(excinfo.value)

    # "color" is wrong type
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.add_image_attributes(image_id=str(image_logo.id), attributes={'color': 1})
    assert 'Schema validation error: 1 is not of type \'string\'' in str(excinfo.value)

    # "background" is required, but when adding attributes it's ok to omit it
    await DataRoom.add_image_attributes(image_id=str(image_logo.id), attributes={'color': 'red'})

    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'color': 'red', 'background': 'transparent'}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_add_image_attributes(DataRoom, image_logo):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='background', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='user', field_type='string')

    image_logo.attributes = await sync_to_async(OSAttributes.from_json)({'color': 'blue', 'background': 'transparent'})
    await sync_to_async(image_logo.save)(fields=['attributes'])

    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'color': 'blue', 'background': 'transparent'}

    await DataRoom.add_image_attributes(image_id=image['id'], attributes={'color': 'red', 'user': 'john'})
    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'color': 'red', 'background': 'transparent', 'user': 'john'}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_add_image_attributes_change_type(DataRoom, image_logo):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    # initially it's an integer
    attribute = await sync_to_async(AttributesField.objects.create)(name='number', field_type='integer')

    image_logo.attributes = await sync_to_async(OSAttributes.from_json)({'number': 314})
    await sync_to_async(image_logo.save)(fields=['attributes'])

    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'number': 314}

    # change attribute type to string
    attribute.field_type = 'string'
    await sync_to_async(attribute.save)()
    AttributesSchema.invalidate_cache()

    # save the image again
    image_logo.attributes = await sync_to_async(OSAttributes.from_json)({'number': 'a string'})
    await sync_to_async(image_logo.save)(fields=['attributes'])

    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'number': 'a string'}

    # now change it back
    attribute.field_type = 'integer'
    await sync_to_async(attribute.save)()
    AttributesSchema.invalidate_cache()

    # old value is still there
    images = await DataRoom.get_images()
    image = images[0]
    assert image['attributes'] == {'number': 314}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_add_image_attributes_in_bulk(DataRoom, image_logo, image_girl, image_perfume):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='background', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='user', field_type='string')
    
    image_logo.attributes = await sync_to_async(OSAttributes.from_json)({'color': 'blue', 'background': 'transparent'})
    await sync_to_async(image_logo.save)(fields=['attributes'])

    image = await DataRoom.get_image(str(image_logo.id))
    assert image['attributes'] == {'color': 'blue', 'background': 'transparent'}

    response = await DataRoom.add_image_attributes_in_bulk({
        image_logo.id: {'color': 'red', 'user': 'john'},
        image_girl.id: {'color': 'blue'},
    })
    assert response['added'] == 1
    assert response['merged'] == 1

    images = await DataRoom.get_images()
    images = {image['id']: image['attributes'] for image in images}
    assert images == {
        image_logo.id: {'color': 'red', 'background': 'transparent', 'user': 'john'},
        image_girl.id: {'color': 'blue'},
        image_perfume.id: {},
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_delete_image(DataRoom, image_logo, image_girl):
    images = await DataRoom.get_images()
    assert len(images) == 2

    await DataRoom.delete_image(image_id=image_logo.id)
    images = await DataRoom.get_images()
    assert len(images) == 1
    assert images[0]['id'] == image_girl.id

    all = await sync_to_async(OSImage.all_objects.all)()
    active = await sync_to_async(OSImage.objects.all)()
    assert len(all) == 2
    assert len(active) == 1
    assert active[0].id == image_girl.id


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_cant_reuse_id_of_deleted_image(DataRoom, tests_path, image_logo):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    await DataRoom.delete_image(image_id=image_logo.id)
    images = await DataRoom.get_images()
    assert len(images) == 0

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_image(image_id=image_logo.id, image_file=image_file, source='test')
    assert 'The provided ID already exists in the database as a deleted image' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_short_edge(DataRoom, image_logo, image_girl, image_perfume):
    images = await DataRoom.get_images()
    assert len(images) == 3

    # eq
    images = await DataRoom.get_images(short_edge=180)
    assert len(images) == 1
    images = await DataRoom.get_images(short_edge=181)
    assert len(images) == 0

    # gt
    images = await DataRoom.get_images(short_edge__gt=265)
    assert len(images) == 1
    images = await DataRoom.get_images(short_edge__gt=266)
    assert len(images) == 0

    # gte
    images = await DataRoom.get_images(short_edge__gte=266)
    assert len(images) == 1
    images = await DataRoom.get_images(short_edge__gte=267)
    assert len(images) == 0

    # lt
    images = await DataRoom.get_images(short_edge__lt=121)
    assert len(images) == 1
    images = await DataRoom.get_images(short_edge__lt=120)
    assert len(images) == 0

    # lte
    images = await DataRoom.get_images(short_edge__lte=120)
    assert len(images) == 1
    images = await DataRoom.get_images(short_edge__lte=119)
    assert len(images) == 0


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_pixel_count(DataRoom, image_logo, image_girl, image_perfume):
    images = await DataRoom.get_images()
    assert len(images) == 3

    # eq
    images = await DataRoom.get_images(pixel_count=106400)
    assert len(images) == 1
    images = await DataRoom.get_images(pixel_count=106401)
    assert len(images) == 0

    # gt
    images = await DataRoom.get_images(pixel_count__gt=19200)
    assert len(images) == 2
    images = await DataRoom.get_images(pixel_count__gt=19199)
    assert len(images) == 3

    # gte
    images = await DataRoom.get_images(pixel_count__gte=19200)
    assert len(images) == 3
    images = await DataRoom.get_images(pixel_count__gte=19201)
    assert len(images) == 2

    # lt
    images = await DataRoom.get_images(pixel_count__lt=32401)
    assert len(images) == 2
    images = await DataRoom.get_images(pixel_count__lt=32400)
    assert len(images) == 1

    # lte
    images = await DataRoom.get_images(pixel_count__lte=19200)
    assert len(images) == 1
    images = await DataRoom.get_images(pixel_count__lte=19199)
    assert len(images) == 0


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_aspect_ratio(DataRoom, image_logo, image_girl, image_perfume):
    images = await DataRoom.get_images()
    assert len(images) == 3

    # eq
    images = await DataRoom.get_images(aspect_ratio=1.0)
    assert len(images) == 1
    images = await DataRoom.get_images(aspect_ratio=1.1)
    assert len(images) == 0

    # gt
    images = await DataRoom.get_images(aspect_ratio__gt=1.5)
    assert len(images) == 1
    images = await DataRoom.get_images(aspect_ratio__gt=1.5038)
    assert len(images) == 0

    # gte
    images = await DataRoom.get_images(aspect_ratio__gte=1.5037)
    assert len(images) == 1
    images = await DataRoom.get_images(aspect_ratio__gte=1.5038)
    assert len(images) == 0

    # lt
    images = await DataRoom.get_images(aspect_ratio__lt=1.0)
    assert len(images) == 1
    images = await DataRoom.get_images(aspect_ratio__lt=0.75)
    assert len(images) == 0

    # lte
    images = await DataRoom.get_images(aspect_ratio__lte=0.75)
    assert len(images) == 1
    images = await DataRoom.get_images(aspect_ratio__lte=0.74)
    assert len(images) == 0


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_aspect_ratio_fraction(DataRoom, image_logo, image_girl, image_perfume):
    images = await DataRoom.get_images()
    assert len(images) == 3

    images = await DataRoom.get_images(aspect_ratio_fraction='1:1')
    assert len(images) == 1

    images = await DataRoom.get_images(aspect_ratio_fraction='3:2')
    assert len(images) == 1

    images = await DataRoom.get_images(aspect_ratio_fraction='2:1')
    assert len(images) == 0


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_source(DataRoom, image_logo, image_girl, image_perfume):
    image_logo.source = 'other'
    await sync_to_async(image_logo.save)(fields=['source'])

    images = await DataRoom.get_images(sources=['test'])
    assert len(images) == 2

    images = await DataRoom.get_images(sources=['other'])
    assert len(images) == 1

    images = await DataRoom.get_images(sources=['none'])
    assert len(images) == 0

    images = await DataRoom.get_images(sources=['test', 'other'])
    assert len(images) == 3

    images = await DataRoom.get_images(sources__ne=['test'])
    assert len(images) == 1

    images = await DataRoom.get_images(sources__ne=['test', 'other'])
    assert len(images) == 0


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_attributes_invalid(DataRoom, image_logo, image_girl, image_perfume):

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color': 'blue,red'})
    assert 'Commas are not allowed' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color': 'blue:red'})
    assert 'Colons are not allowed' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color,a': 'blue'})
    assert 'Commas are not allowed' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color:a': 'blue'})
    assert 'Colons are not allowed' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'doesnotexist': 'blue'})
    assert 'Field \\"doesnotexist\\" not found in schema' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(has_attributes=['doesnotexist'])
    assert 'Field \\"doesnotexist\\" not found in schema' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_count_images(DataRoom, image_logo, image_girl, image_perfume):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string', is_indexed=True)
    await sync_to_async(AttributesSchema.json_schema_fn)()

    image_logo.source = 'other'
    image_logo.attributes.update({
        'color': 'blue',
    })
    blue = await sync_to_async(Tag.objects.create)(name='blue')
    image_logo.tags = ['blue']
    await sync_to_async(image_logo.save)(fields=['source', 'attributes', 'tags'])

    count = await DataRoom.count_images()
    assert count == 3

    count = await DataRoom.count_images(aspect_ratio=1.0)
    assert count == 1

    count = await DataRoom.count_images(aspect_ratio__gt=1.0)
    assert count == 1

    count = await DataRoom.count_images(aspect_ratio__gte=1.0)
    assert count == 2

    count = await DataRoom.count_images(aspect_ratio__lt=1.0)
    assert count == 1

    count = await DataRoom.count_images(sources=['other'])
    assert count == 1

    count = await DataRoom.count_images(sources=['other', 'test'])
    assert count == 3

    count = await DataRoom.count_images(attributes={
        'color': 'blue',
    })
    assert count == 1

    count = await DataRoom.count_images(tags=['blue'])
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_tags(DataRoom, image_logo, image_logo_alt, image_girl, image_perfume):
    red = await sync_to_async(Tag.objects.create)(name='red')
    green = await sync_to_async(Tag.objects.create)(name='green')
    blue = await sync_to_async(Tag.objects.create)(name='blue')
    none = await sync_to_async(Tag.objects.create)(name='none')
    image_logo.tags = ['red', 'green']
    await sync_to_async(image_logo.save)(fields=['tags'])
    image_girl.tags = ['green']
    await sync_to_async(image_girl.save)(fields=['tags'])
    image_perfume.tags = ['blue']
    await sync_to_async(image_perfume.save)(fields=['tags'])

    # tags
    images = await DataRoom.get_images(tags=['red'])
    assert [i['id'] for i in images] == ['test-logo']

    images = await DataRoom.get_images(tags=['green'])
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']

    images = await DataRoom.get_images(tags=['blue'])
    assert [i['id'] for i in images] == ['test-perfume']

    images = await DataRoom.get_images(tags=['none'])
    assert len(images) == 0

    # tags__ne
    images = await DataRoom.get_images(tags__ne=['red'])
    assert [i['id'] for i in images] == ['test-girl', 'test-logo_alt', 'test-perfume']

    images = await DataRoom.get_images(tags__ne=['red', 'blue'])
    assert [i['id'] for i in images] == ['test-girl', 'test-logo_alt']

    images = await DataRoom.get_images(tags__ne=['none'])
    assert len(images) == 4

    # tags__empty
    images = await DataRoom.get_images(tags__empty=True)
    assert [i['id'] for i in images] == ['test-logo_alt']

    images = await DataRoom.get_images(tags__empty=False)
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']

    # tags__all
    images = await DataRoom.get_images(tags__all=['red', 'green'])
    assert [i['id'] for i in images] == ['test-logo']

    images = await DataRoom.get_images(tags__all=['green'])
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']

    images = await DataRoom.get_images(tags__all=['green', 'blue'])
    assert len(images) == 0

    # tags__ne_all
    images = await DataRoom.get_images(tags__ne_all=['red', 'green'])
    assert [i['id'] for i in images] == ['test-girl', 'test-logo_alt', 'test-perfume']

    images = await DataRoom.get_images(tags__ne_all=['red', 'green', 'blue'])
    assert len(images) == 4


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_tags_that_doesnt_exist(DataRoom, image_logo):
    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(tags=['wrong'])
    assert "One or more tags do not exist: 'wrong'" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_coca_embedding_empty(DataRoom, image_logo, image_girl, image_perfume):
    image_logo.coca_embedding_vector = None
    image_logo.coca_embedding_author = None
    image_logo.coca_embedding_exists = False
    await sync_to_async(image_logo.save)(fields=['coca_embedding'])

    images = await DataRoom.get_images(coca_embedding__empty=True)
    assert len(images) == 1
    assert images[0]['id'] == 'test-logo'

    images = await DataRoom.get_images(coca_embedding__empty=False)
    assert len(images) == 2
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_duplicate_state(DataRoom, image_logo, image_girl, image_perfume):
    image_logo.duplicate_state = DuplicateState.ORIGINAL
    await sync_to_async(image_logo.save)(fields=['duplicate_state'])

    images = await DataRoom.get_images(duplicate_state=ClientDuplicateState.UNPROCESSED)
    assert len(images) == 2
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']

    images = await DataRoom.get_images(duplicate_state=DuplicateState.ORIGINAL)
    assert len(images) == 1
    assert images[0]['id'] == 'test-logo'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_date_created(DataRoom, image_logo, image_girl, image_perfume):
    image_logo.date_created = datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc)
    image_girl.date_created = datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc)
    image_perfume.date_created = datetime.datetime(2024, 1, 3, 3, tzinfo=datetime.timezone.utc)
    await sync_to_async(image_logo.save)(fields=['date_created'])
    await sync_to_async(image_girl.save)(fields=['date_created'])
    await sync_to_async(image_perfume.save)(fields=['date_created'])

    # gt
    images = await DataRoom.get_images(date_created__gt=datetime.datetime(2024, 1, 2, 1, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']

    images = await DataRoom.get_images(date_created__gt=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-perfume']

    images = await DataRoom.get_images(date_created__gte=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']

    # lt
    images = await DataRoom.get_images(date_created__lt=datetime.datetime(2024, 1, 3, 3, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']

    images = await DataRoom.get_images(date_created__lt=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-logo']

    images = await DataRoom.get_images(date_created__lte=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc))
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']

    # combined
    images = await DataRoom.get_images(
        date_created__gt=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_created__lt=datetime.datetime(2024, 1, 3, 3, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == ['test-girl']

    images = await DataRoom.get_images(
        date_created__gt=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_created__lte=datetime.datetime(2024, 1, 3, 3, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']

    images = await DataRoom.get_images(
        date_created__gte=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_created__lte=datetime.datetime(2024, 1, 3, 3, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_date_updated(DataRoom, image_logo):
    image_logo.date_created = datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc)
    date_updated = datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc)
    with freeze_time(date_updated):
        # date updated is set on save
        await sync_to_async(image_logo.save)(fields=['date_created', 'date_updated'])

    images = await DataRoom.get_images(
        date_created__gt=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_updated__lt=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == []

    images = await DataRoom.get_images(
        date_created__gte=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_updated__lt=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == []

    images = await DataRoom.get_images(
        date_created__gt=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_updated__lte=datetime.datetime(2024, 1, 2, 2, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == []

    images = await DataRoom.get_images(
        date_created__gte=datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
        date_updated__lte=datetime.datetime(2024, 2, 2, 2, tzinfo=datetime.timezone.utc),
    )
    assert [i['id'] for i in images] == ['test-logo']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_pagination(DataRoom, image_logo, image_logo_alt, image_girl, image_perfume):

    # patch DataRoom._make_request
    urls = []
    async def _make_request(url, **kwargs):
        response = await DataRoom._make_request_original(url, **kwargs)
        urls.append(url)
        return response

    DataRoom._make_request_original = DataRoom._make_request
    DataRoom._make_request = _make_request

    await DataRoom.get_images(page_size=1, sources=['test', 'other'], fields=['id'])

    # params shouldn't change, only the cursor
    assert len(urls) == 5
    urls = [url.split('/api')[1] if '/api' in url else url for url in urls]
    assert urls[0] == 'images/'
    assert urls[1] == '/images/?fields=id&page_size=1&sources=test%2Cother&cursor=test-girl'
    assert urls[2] == '/images/?fields=id&page_size=1&sources=test%2Cother&cursor=test-logo'
    assert urls[3] == '/images/?fields=id&page_size=1&sources=test%2Cother&cursor=test-logo_alt'
    assert urls[4] == '/images/?fields=id&page_size=1&sources=test%2Cother&cursor=test-perfume'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_pagination_max_page_size(DataRoom, image_logo, image_logo_alt, image_girl, image_perfume):
    await DataRoom.get_images(page_size=API_MAX_PAGE_SIZE)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(page_size=API_MAX_PAGE_SIZE + 1)
    assert f'Ensure this value is less than or equal to {API_MAX_PAGE_SIZE}.' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_random_images(DataRoom, image_logo, image_logo_alt, image_girl, image_perfume):
    response = await DataRoom.get_random_images(prefix_length=1, num_prefixes=300)
    assert len(response) == 4


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_partition_wrong(DataRoom, image_logo, image_logo_alt, image_girl, image_perfume):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=2)
    assert f'Both \\"partitions_count\\" and \\"partition\\" parameters must be provided' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partition=2)
    assert f'Both \\"partitions_count\\" and \\"partition\\" parameters must be provided' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count='fail', partition=0)
    assert f'Invalid \\"partitions_count\\" parameter' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=2, partition='fail')
    assert f'Invalid \\"partition\\" parameter' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=0, partition=0)
    assert f'Invalid \\"partitions_count\\" parameter' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=1, partition=0)
    assert f'\\"partitions_count\\" should be between 2 and 48' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=49, partition=0)
    assert f'\\"partitions_count\\" should be between 2 and 48' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(partitions_count=2, partition=2)
    assert f'\\"partition\\" should be between 0 and 1' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_partition(DataRoom, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    response = await DataRoom.get_images(partitions_count=2, partition=0)
    assert [image['id'] for image in response] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-logo_small']
    response = await DataRoom.get_images(partitions_count=2, partition=1)
    assert [image['id'] for image in response] == ['test-perfume']

    response = await DataRoom.get_images(partitions_count=6, partition=0)
    assert [image['id'] for image in response] == ['test-logo']
    response = await DataRoom.get_images(partitions_count=6, partition=1)
    assert [image['id'] for image in response] == []
    response = await DataRoom.get_images(partitions_count=6, partition=2)
    assert [image['id'] for image in response] == ['test-girl']
    response = await DataRoom.get_images(partitions_count=6, partition=3)
    assert [image['id'] for image in response] == []
    response = await DataRoom.get_images(partitions_count=6, partition=4)
    assert [image['id'] for image in response] == ['test-logo_alt', 'test-logo_small']
    response = await DataRoom.get_images(partitions_count=6, partition=5)
    assert [image['id'] for image in response] == ['test-perfume']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_count_images_partition(DataRoom, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    response = await DataRoom.count_images(partitions_count=2, partition=0)
    assert response == 4
    response = await DataRoom.count_images(partitions_count=2, partition=1)
    assert response == 1

    response = await DataRoom.count_images(partitions_count=6, partition=0)
    assert response == 1
    response = await DataRoom.count_images(partitions_count=6, partition=1)
    assert response == 0
    response = await DataRoom.count_images(partitions_count=6, partition=2)
    assert response == 1
    response = await DataRoom.count_images(partitions_count=6, partition=3)
    assert response == 0
    response = await DataRoom.count_images(partitions_count=6, partition=4)
    assert response == 2
    response = await DataRoom.count_images(partitions_count=6, partition=5)
    assert response == 1




