import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.models import AttributesSchema, AttributesField
from dataroom_client.dataroom_client.client import DataRoomError


LONG_DECIMAL = 0.30771970748901367


@pytest.fixture
def images_with_attributes(image_logo, image_logo_alt, image_girl, image_perfume):
    AttributesSchema.invalidate_cache()  # force invalidate cache from other tests

    # setup
    AttributesField.objects.create(name='color', field_type='string', is_indexed=True)
    AttributesField.objects.create(name='has_text', field_type='boolean', is_indexed=True)
    AttributesField.objects.create(name='user', field_type='string', is_indexed=True)
    AttributesField.objects.create(name='unknown', field_type='string', is_indexed=True)
    AttributesField.objects.create(name='caption.dot', field_type='string', is_indexed=True)
    AttributesField.objects.create(name='int', field_type='integer', is_indexed=True)
    AttributesField.objects.create(name='number', field_type='number', is_indexed=True)
    AttributesField.objects.create(name='double__underscore', field_type='number',is_indexed=True)
    AttributesField.objects.create(name='date', field_type='string', string_format='date', is_indexed=True)
    AttributesSchema.json_schema_fn()

    image_logo.attributes.update({
        'color': 'blue',
        'has_text': True,
        'user': 'test user 1',
        'caption.dot': 'image of a logo',
        'int': 15,
        'number': 15,
        'double__underscore': LONG_DECIMAL,
        'date': '2024-01-05',
    })
    image_logo.save(fields=['attributes'])

    image_logo_alt.attributes.update({
        'color': 'blue ',  # notice trailing whitespace
        'has_text': True,
        'unknown': '',
        'number': 12,
    })
    image_logo_alt.save(fields=['attributes'])

    image_girl.attributes.update({
        'color': 'blue',
        'has_text': False,
        'user': 'test user 2',
        'caption.dot': 'image of a girl',
        'int': 23,
        'number': 23,
        'double__underscore': 1.3,
        'date': '2024-02-03',
    })
    image_girl.save(fields=['attributes'])

    image_perfume.attributes.update({
        'int': 38,
        'number': 38,
        'double__underscore': 2.8,
        'date': '2024-03-08',
    })
    image_perfume.save(fields=['attributes'])


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes(DataRoom, images_with_attributes):
    images = await DataRoom.get_images(attributes={
        'color': 'blue',
    })
    assert len(images) == 2

    images = await DataRoom.get_images(attributes={
        'color': 'blue',
        'user': 'test user 1',
    })
    assert len(images) == 1
    assert images[0]['id'] == 'test-logo'

    images = await DataRoom.get_images(attributes={
        'color': 'blue',
        'user': 'unknown',
    })
    assert len(images) == 0

    images = await DataRoom.get_images(attributes={
        'number': 12,
    })
    assert len(images) == 1
    assert images[0]['id'] == 'test-logo_alt'

    images = await DataRoom.get_images(has_attributes=['color', 'user'])
    assert len(images) == 2

    images = await DataRoom.get_images(has_attributes=['unknown'])
    assert len(images) == 1
    assert images[0]['id'] == 'test-logo_alt'

    images = await DataRoom.get_images(lacks_attributes=['color', 'user'])
    assert len(images) == 1
    assert images[0]['id'] == 'test-perfume'

    images = await DataRoom.get_images(lacks_attributes=['unknown'])
    assert len(images) == 3


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_text(DataRoom, images_with_attributes):
    # tests for text
    images = await DataRoom.get_images(attributes={'color__eq': 'blue'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']
    images = await DataRoom.get_images(attributes={'color__ne': 'blue'})
    assert [i['id'] for i in images] == ['test-logo_alt', 'test-perfume']

    # tests for text search
    images = await DataRoom.get_images(attributes={'caption.dot__eq': 'image of a logo'})
    assert [i['id'] for i in images] == ['test-logo']
    images = await DataRoom.get_images(attributes={'caption.dot__match': 'logo'})
    assert [i['id'] for i in images] == ['test-logo']
    images = await DataRoom.get_images(attributes={'caption.dot__match_phrase': 'of a'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']
    images = await DataRoom.get_images(attributes={'caption.dot__prefix_phrase': 'of a'})
    assert [i['id'] for i in images] == []
    images = await DataRoom.get_images(attributes={'caption.dot__prefix': 'image of a'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo']
    images = await DataRoom.get_images(attributes={'caption.dot__prefix': 'girl'})
    assert [i['id'] for i in images] == []

    # tests for negated text search
    images = await DataRoom.get_images(attributes={'caption.dot__ne': 'image of a logo'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'caption.dot__not_match': 'logo'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'caption.dot__not_match_phrase': 'of a'})
    assert [i['id'] for i in images] == ['test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'caption.dot__not_prefix': 'image of a'})
    assert [i['id'] for i in images] == ['test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'caption.dot__not_prefix': 'girl'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-perfume']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_boolean(DataRoom, images_with_attributes):
    # test for boolean equality
    images = await DataRoom.get_images(attributes={'has_text': True})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt']
    
    images = await DataRoom.get_images(attributes={'has_text': False})
    assert len(images) == 1
    assert images[0]['id'] == 'test-girl'
    
    # test with explicit comparators
    images = await DataRoom.get_images(attributes={'has_text__eq': True})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt']
    
    images = await DataRoom.get_images(attributes={'has_text__ne': True})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-girl', 'test-perfume']
    
    images = await DataRoom.get_images(attributes={'has_text__eq': False})
    assert len(images) == 1
    assert images[0]['id'] == 'test-girl'
    
    images = await DataRoom.get_images(attributes={'has_text__ne': False})
    assert len(images) == 3
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt', 'test-perfume']
    
    # test for images that don't have the boolean attribute set
    images = await DataRoom.get_images(lacks_attributes=['has_text'])
    assert len(images) == 1
    assert images[0]['id'] == 'test-perfume'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_boolean_as_str(DataRoom, images_with_attributes):
    # test for boolean equality
    images = await DataRoom.get_images(attributes={'has_text': 'True'})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt']
    
    images = await DataRoom.get_images(attributes={'has_text': 'False'})
    assert len(images) == 1
    assert images[0]['id'] == 'test-girl'

    # lowercase
    images = await DataRoom.get_images(attributes={'has_text': 'true'})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt']
    
    # test with explicit comparators
    images = await DataRoom.get_images(attributes={'has_text__eq': 'True'})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt']
    
    images = await DataRoom.get_images(attributes={'has_text__ne': 'True'})
    assert len(images) == 2
    assert sorted([i['id'] for i in images]) == ['test-girl', 'test-perfume']
    
    images = await DataRoom.get_images(attributes={'has_text__eq': 'False'})
    assert len(images) == 1
    assert images[0]['id'] == 'test-girl'
    
    images = await DataRoom.get_images(attributes={'has_text__ne': 'False'})
    assert len(images) == 3
    assert sorted([i['id'] for i in images]) == ['test-logo', 'test-logo_alt', 'test-perfume']
    
    # test for images that don't have the boolean attribute set
    images = await DataRoom.get_images(lacks_attributes=['has_text'])
    assert len(images) == 1
    assert images[0]['id'] == 'test-perfume'
    


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_number(DataRoom, images_with_attributes):
    # tests for int
    images = await DataRoom.get_images(attributes={'int__gt': 15})
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']
    images = await DataRoom.get_images(attributes={'int__gte': 15})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']
    images = await DataRoom.get_images(attributes={'int__lt': 15})
    assert [i['id'] for i in images] == []
    images = await DataRoom.get_images(attributes={'int__lte': 15})
    assert [i['id'] for i in images] == ['test-logo']
    images = await DataRoom.get_images(attributes={'int__eq': 23})
    assert [i['id'] for i in images] == ['test-girl']
    images = await DataRoom.get_images(attributes={'int__ne': 23})
    assert [i['id'] for i in images] == ['test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'int__ne': 1})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'int__gt': 13, 'int__lt': 23})
    assert [i['id'] for i in images] == ['test-logo']

    # tests for number
    images = await DataRoom.get_images(attributes={'number__gt': 15})
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']
    images = await DataRoom.get_images(attributes={'number__gte': 15})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']
    images = await DataRoom.get_images(attributes={'number__lt': 15})
    assert [i['id'] for i in images] == ['test-logo_alt']
    images = await DataRoom.get_images(attributes={'number__lte': 15})
    assert [i['id'] for i in images] == ['test-logo', 'test-logo_alt']
    images = await DataRoom.get_images(attributes={'number__eq': 23})
    assert [i['id'] for i in images] == ['test-girl']
    images = await DataRoom.get_images(attributes={'number__ne': 23})
    assert [i['id'] for i in images] == ['test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'number__ne': 1})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'number__gt': 13, 'number__lt': 23})
    assert [i['id'] for i in images] == ['test-logo']

    # tests for double__underscore
    images = await DataRoom.get_images(attributes={'double__underscore__gt': LONG_DECIMAL})
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']
    images = await DataRoom.get_images(attributes={'double__underscore__gte': LONG_DECIMAL})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']
    images = await DataRoom.get_images(attributes={'double__underscore__gte': 0})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']
    images = await DataRoom.get_images(attributes={'double__underscore__lt': LONG_DECIMAL})
    assert [i['id'] for i in images] == []
    images = await DataRoom.get_images(attributes={'double__underscore__lte': LONG_DECIMAL})
    assert [i['id'] for i in images] == ['test-logo']
    images = await DataRoom.get_images(attributes={'double__underscore__eq': 1.3})
    assert [i['id'] for i in images] == ['test-girl']
    images = await DataRoom.get_images(attributes={'double__underscore__ne': 1.3})
    assert [i['id'] for i in images] == ['test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'double__underscore__ne': 0})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'double__underscore__gt': 0.3, 'double__underscore__lt': 1.3})
    assert [i['id'] for i in images] == ['test-logo']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_date(DataRoom, images_with_attributes):
    # tests for date
    images = await DataRoom.get_images(attributes={'date__gt': '2024-01-05'})
    assert [i['id'] for i in images] == ['test-girl', 'test-perfume']
    images = await DataRoom.get_images(attributes={'date__gte': '2024-01-05'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-perfume']
    images = await DataRoom.get_images(attributes={'date__lt': '2024-01-05'})
    assert [i['id'] for i in images] == []
    images = await DataRoom.get_images(attributes={'date__lte': '2024-01-05'})
    assert [i['id'] for i in images] == ['test-logo']
    images = await DataRoom.get_images(attributes={'date__eq': '2024-02-03'})
    assert [i['id'] for i in images] == ['test-girl']
    images = await DataRoom.get_images(attributes={'date__ne': '2024-02-03'})
    assert [i['id'] for i in images] == ['test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'date__ne': '2024-01-01'})
    assert [i['id'] for i in images] == ['test-girl', 'test-logo', 'test-logo_alt', 'test-perfume']
    images = await DataRoom.get_images(attributes={'date__gt': '2024-01-03', 'date__lt': '2024-02-03'})
    assert [i['id'] for i in images] == ['test-logo']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_attributes_invalid(DataRoom, images_with_attributes):
    # invalid
    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color__gt': 'blue'})
    assert "Invalid comparator 'gt' for attribute 'color' of type 'text'" in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'number__match': 3})
    assert "Invalid comparator 'match' for attribute 'number' of type 'double'" in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'color__eq__eq': 'blue'})
    assert 'Field \\"color__eq\\" not found in schema' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        images = await DataRoom.get_images(attributes={'nonexistent__gt': 'blue'})
    assert 'Field \\"nonexistent\\" not found in schema' in str(excinfo.value)
    
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(attributes={'has_text': 'not a bool'})
    assert "Invalid filter value 'not a bool' for attribute 'has_text'" in str(excinfo.value)
