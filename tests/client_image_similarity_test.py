import pytest
from asgiref.sync import sync_to_async

from dataroom_client import DataRoomFile


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similarity(DataRoom, image_logo, image_logo_alt):
    response = await DataRoom.get_image_similarity(image_logo.id, image_logo_alt.id)
    assert isinstance(response, float)
    assert round(response, 3) == 0.946


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar(DataRoom, image_logo, image_logo_alt, image_girl):
    response = await DataRoom.get_similar_images(image_id=image_logo.id, number=2, fields=['id', 'source'])
    assert len(response) == 2
    assert response[0]['id'] == 'test-logo_alt'
    assert response[0]['source'] == 'test'
    assert round(response[0]['similarity'], 3) == 0.946
    assert response[1]['id'] == 'test-girl'
    assert response[1]['source'] == 'test'
    assert round(response[1]['similarity'], 3) == 0.329


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_with_filter(DataRoom, image_logo, image_logo_alt, image_girl):
    response = await DataRoom.get_similar_images(
        image_id=image_logo.id,
        number=2,
        fields=['id', 'source'],
        aspect_ratio__gt=1.5,
    )
    assert len(response) == 1
    assert response[0]['id'] == 'test-girl'
    assert response[0]['source'] == 'test'
    assert round(response[0]['similarity'], 3) == 0.329


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_file(DataRoom, tests_path, image_logo, image_logo_alt, image_girl, mocker):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    # Mock get_vector_for_image_file
    mocker.patch(
        'backend.dataroom.models.os_image.get_vector_for_image_file',
        return_value=image_logo.coca_embedding_vector,
    )

    response = await DataRoom.get_similar_images(image_file=image_file, number=2, fields=['id', 'source'])

    assert len(response) == 2
    assert response[0]['id'] == 'test-logo'
    assert response[0]['source'] == 'test'
    assert round(response[0]['similarity'], 3) == 1.0
    assert response[1]['id'] == 'test-logo_alt'
    assert response[1]['source'] == 'test'
    assert round(response[1]['similarity'], 3) == 0.946


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_file_with_filter(DataRoom, tests_path, image_logo, image_logo_alt, image_girl, mocker):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    # Mock get_vector_for_image_file
    mocker.patch(
        'backend.dataroom.models.os_image.get_vector_for_image_file',
        return_value=image_logo.coca_embedding_vector,
    )

    response = await DataRoom.get_similar_images(
        image_file=image_file,
        number=2,
        fields=['id', 'source'],
        aspect_ratio__gt=1.5,
    )
    assert len(response) == 1
    assert response[0]['id'] == 'test-girl'
    assert response[0]['source'] == 'test'
    assert round(response[0]['similarity'], 3) == 0.329


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_vector(DataRoom, tests_path, image_logo, image_logo_alt, image_girl):
    vector = str(image_logo.coca_embedding_vector)
    response = await DataRoom.get_similar_images(image_vector=vector, number=2, fields=['id', 'source'])
    assert len(response) == 2
    assert response[0]['id'] == 'test-logo'
    assert response[0]['source'] == 'test'
    assert round(response[0]['similarity'], 3) == 1.0
    assert response[1]['id'] == 'test-logo_alt'
    assert response[1]['source'] == 'test'
    assert round(response[1]['similarity'], 3) == 0.946


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_vector_with_filter(DataRoom, tests_path, image_logo, image_logo_alt, image_girl):
    vector = str(image_logo.coca_embedding_vector)
    image_girl.source = 'example'
    await sync_to_async(image_girl.save)(fields=['source'])
    response = await DataRoom.get_similar_images(
        image_vector=vector,
        number=2,
        fields=['id', 'source'],
        sources=['example'],
    )
    assert len(response) == 1
    assert response[0]['id'] == 'test-girl'
    assert response[0]['source'] == 'example'
    assert round(response[0]['similarity'], 3) == 0.329

    response = await DataRoom.get_similar_images(
        image_vector=vector,
        number=2,
        fields=['id', 'source'],
        aspect_ratio__gt=1.5,
    )
    assert len(response) == 1
    assert response[0]['id'] == 'test-girl'
    assert response[0]['source'] == 'example'
    assert round(response[0]['similarity'], 3) == 0.329


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_text(DataRoom, image_logo, image_logo_alt, image_girl, mocker):

    # Mock get_vector_for_image_file
    mocker.patch(
        'backend.api.images.views.fetch_coca_embedding_for_text',
        return_value=image_logo.coca_embedding_vector,
    )

    response = await DataRoom.get_similar_images(image_text='logo', number=2, fields=['id', 'source'])
    assert len(response) == 2
    assert response[0]['id'] == 'test-logo'
    assert response[1]['id'] == 'test-logo_alt'
    assert round(response[0]['similarity'], 3) == 1.000
    assert round(response[1]['similarity'], 3) == 0.946


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_get_similar_to_text_with_filter(DataRoom, image_logo, image_logo_alt, image_girl, mocker):

    # Mock get_vector_for_image_file
    mocker.patch(
        'backend.api.images.views.fetch_coca_embedding_for_text',
        return_value=image_girl.coca_embedding_vector,
    )

    response = await DataRoom.get_similar_images(
        image_text='girl',
        number=2,
        fields=['id', 'source'],
        aspect_ratio__gt=1.5,
    )
    assert len(response) == 1
    assert response[0]['id'] == 'test-girl'
    assert round(response[0]['similarity'], 3) == 1.000

