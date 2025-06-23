import random

import pytest
from asgiref.sync import sync_to_async

from dataroom_client import DataRoomError
from tests.utils import get_random_vector


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_image_with_coca_embedding(DataRoom, tests_path, image_logo):
    image = await DataRoom.get_image(image_logo.id, fields=['coca_embedding'])
    assert image['coca_embedding']['vector'] is not None
    assert image['coca_embedding']['author'] is not None
    assert len(image['coca_embedding']['vector']) == 768


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_coca_embedding_new(DataRoom, tests_path, image_logo):
    # delete the existing embedding
    image_logo.coca_embedding_exists = False
    image_logo.coca_embedding_vector = None
    image_logo.coca_embedding_author = None
    await sync_to_async(image_logo.save)(fields=['coca_embedding'])
    image = await DataRoom.get_image(image_logo.id)

    image = await DataRoom.get_image(image['id'], fields=['coca_embedding'])
    assert image['coca_embedding'] is None

    vector = ",".join([str(x) for x in get_random_vector()])
    vector = f'[{vector}]'

    await DataRoom.update_image(image['id'], coca_embedding=vector)
    embedding = await DataRoom.get_image(image['id'], fields=['coca_embedding'])
    embedding = embedding['coca_embedding']
    assert embedding['author'] is not None
    assert len(embedding['vector']) == 768


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_coca_embedding_existing(DataRoom, tests_path, image_logo):
    vector = ",".join([str(x) for x in get_random_vector()])
    vector = f'[{vector}]'

    old_embedding = await DataRoom.get_image(image_logo.id, fields=['coca_embedding'])
    old_embedding = old_embedding['coca_embedding']

    await DataRoom.update_image(image_logo.id, coca_embedding=vector)
    new_embedding = await DataRoom.get_image(image_logo.id, fields=['coca_embedding'])
    new_embedding = new_embedding['coca_embedding']
    assert new_embedding['author'] is not None
    assert len(new_embedding['vector']) == 768
    assert new_embedding['vector'] != old_embedding['vector']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_coca_embedding_invalid(DataRoom, tests_path, image_logo):

    # invalid length
    vector = ",".join([str(x) for x in get_random_vector(767)])
    vector = f'[{vector}]'
    with pytest.raises(DataRoomError) as exc_info:
        await DataRoom.update_image(image_logo.id, coca_embedding=vector)
    assert "Argument vector must be a string representing a list of 768 floats." in str(exc_info.value)

    # not normalized
    vector = ",".join([str(random.randint(-99, 99)/100) for _ in range(768)])
    vector = f'[{vector}]'
    with pytest.raises(DataRoomError) as exc_info:
        await DataRoom.update_image(image_logo.id, coca_embedding=vector)
    assert "Vector must be normalized" in str(exc_info.value)

    # invalid value
    vector = ",".join(['fail' for _ in range(768)])
    vector = f'[{vector}]'
    with pytest.raises(DataRoomError) as exc_info:
        await DataRoom.update_image(image_logo.id, coca_embedding=vector)
    assert "Invalid vector" in str(exc_info.value)

