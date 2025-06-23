import pytest

from asgiref.sync import sync_to_async

from backend.dataroom.models.attributes import AttributesField, AttributesSchema
from dataroom_client.dataroom_client.client import DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_aggregate_images(DataRoom, image_logo, image_girl, image_perfume):
    response = await DataRoom.aggregate_images(field='width', type='min')
    assert response['value'] == 120

    response = await DataRoom.aggregate_images(field='width', type='max')
    assert response['value'] == 400

    response = await DataRoom.aggregate_images(field='width', type='avg')
    assert response['value'] == 233.33333333333334

    response = await DataRoom.aggregate_images(field='width', type='sum')
    assert response['value'] == 700

    response = await DataRoom.aggregate_images(field='width', type='value_count')
    assert response['value'] == 3

    response = await DataRoom.aggregate_images(field='width', type='cardinality')
    assert response['value'] == 3

    response = await DataRoom.aggregate_images(field='width', type='stats')
    assert response == {
        'count': 3,
        'min': 120,
        'max': 400,
        'avg': 233.33333333333334,
        'sum': 700,
    }

    response = await DataRoom.aggregate_images(field='width', type='percentiles')
    assert response == {
        'values': {
            '1.0': 120.0,
            '25.0': 135.0,
            '5.0': 120.0,
            '50.0': 180.0,
            '75.0': 345.0,
            '95.0': 400.0,
            '99.0': 400.0,
        }
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_aggregate_images_on_attributes(DataRoom, image_logo, image_girl, image_perfume):
    AttributesSchema.invalidate_cache()  # force invalidate cache from other tests
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='number', field_type='number')

    await DataRoom.update_image(image_id=image_logo.id, attributes={'color': 'blue', 'number': 3})
    await DataRoom.update_image(image_id=image_girl.id, attributes={'color': 'red', 'number': 6})
    await DataRoom.update_image(image_id=image_perfume.id, attributes={'color': 'red', 'number': 6})

    response = await DataRoom.aggregate_images(field='attributes.number', type='stats')
    assert response == {
        'count': 3,
        'min': 3,
        'max': 6,
        'avg': 5,
        'sum': 15,
    }

    response = await DataRoom.aggregate_images(field='attributes.color', type='cardinality')
    assert response == {
        'value': 2,
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_aggregate_images_wrong_agg_type(DataRoom, image_logo, image_girl, image_perfume):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.aggregate_images(field='source', type='fail')
    assert 'not a valid choice' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_aggregate_images_wrong_field(DataRoom, image_logo, image_girl, image_perfume):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.aggregate_images(field='attributes.doesnotexist', type='min')
    assert 'not found in attributes schema' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_aggregate_images_wrong_field_type(DataRoom, image_logo, image_girl, image_perfume):
    AttributesSchema.invalidate_cache()  # force invalidate cache from other tests
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='number', field_type='number')

    await DataRoom.update_image(image_id=image_logo.id, attributes={'color': 'blue', 'number': 3})

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.aggregate_images(field='source', type='min')
    assert 'This field type is not supported for this aggregation' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.aggregate_images(field='attributes.color', type='min')
    assert 'This field type is not supported for this aggregation' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_bucket_images(DataRoom, image_logo, image_girl, image_perfume):
    response = await DataRoom.bucket_images(field='width', size=10)
    assert response == {
        "doc_count_error_upper_bound": 0,
        "sum_other_doc_count": 0,
        "buckets": [
            {"key": 120, "doc_count": 1},
            {"key": 180, "doc_count": 1},
            {"key": 400, "doc_count": 1},
        ]
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_bucket_images_on_attributes(DataRoom, image_logo, image_girl, image_perfume):
    AttributesSchema.invalidate_cache()  # force invalidate cache from other tests
    await sync_to_async(AttributesField.objects.create)(name='color', field_type='string')
    await sync_to_async(AttributesField.objects.create)(name='number', field_type='number')

    await DataRoom.update_image(image_id=image_logo.id, attributes={'color': 'blue', 'number': 3})
    await DataRoom.update_image(image_id=image_girl.id, attributes={'color': 'red', 'number': 6})
    await DataRoom.update_image(image_id=image_perfume.id, attributes={'color': 'red', 'number': 6})

    response = await DataRoom.bucket_images(field='attributes.color', size=10)
    assert response == {
        "doc_count_error_upper_bound": 0,
        "sum_other_doc_count": 0,
        "buckets": [
            {"key": "red", "doc_count": 2},
            {"key": "blue", "doc_count": 1},
        ],
    }
