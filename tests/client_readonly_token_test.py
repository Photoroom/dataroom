import uuid
import pytest

from dataroom_client.dataroom_client.client import DataRoomFile, DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_readonly_token_allowed(DataRoomReadOnly):
    response = await DataRoomReadOnly.get_images()
    assert response == []


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_readonly_token_create_image(DataRoomReadOnly, tests_path):
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image_id = str(uuid.uuid4())
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoomReadOnly.create_image(image_id=image_id, image_file=image_file, source='test')
    assert 'This token is read-only' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_readonly_token_update_image(DataRoomReadOnly, image_logo):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoomReadOnly.update_image(image_id=image_logo.id, source='test2')
    assert 'This token is read-only' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_readonly_token_delete_image(DataRoomReadOnly, image_logo):
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoomReadOnly.delete_image(image_id=image_logo.id)
    assert 'This token is read-only' in str(excinfo.value)
