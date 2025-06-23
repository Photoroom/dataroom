import pytest
from dataroom_client import DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_tag(DataRoom, image_logo):
    await DataRoom.create_tag(name='test', description='example description')
    tags = await DataRoom.get_tags()
    assert len(tags) == 1
    assert tags[0]['name'] == 'test'
    assert tags[0]['description'] == 'example description'

    tag = await DataRoom.get_tag(tag_id=tags[0]['id'])
    assert tag['name'] == 'test'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_tag_trims(DataRoom, image_logo):
    await DataRoom.create_tag(name='trim ')
    tags = await DataRoom.get_tags()
    assert len(tags) == 1
    assert tags[0]['name'] == 'trim'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_tag_with_same_name(DataRoom, image_logo):
    await DataRoom.create_tag(name='hmm')

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='hmm')
    assert 'tag with this name already exists' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_tag_with_invalid_name(DataRoom):

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='a:b')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='a/b')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='a b')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='a.')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name='')
    assert 'This field may not be blank' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_tag(name=' ')
    assert 'This field may not be blank' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_tag_images(DataRoom, image_logo, image_girl, image_perfume):
    await DataRoom.create_tag(name='red')
    await DataRoom.create_tag(name='green')
    await DataRoom.create_tag(name='blue')
    await DataRoom.tag_images(image_ids=[image_logo.id, image_girl.id], tag_names=['red', 'green'])

    tags = await DataRoom.get_tags()
    assert len(tags) == 3

    image_logo_dict = await DataRoom.get_image(image_logo.id)
    assert image_logo_dict['tags'] == ['red', 'green']

    image_girl_dict = await DataRoom.get_image(image_girl.id)
    assert image_girl_dict['tags'] == ['red', 'green']

    image_perfume_dict = await DataRoom.get_image(image_perfume.id)
    assert image_perfume_dict['tags'] == []

    # keeps existing tags

    await DataRoom.tag_images(image_ids=[image_girl.id, image_perfume.id], tag_names=['blue'])

    image_logo_dict = await DataRoom.get_image(image_logo.id)
    assert image_logo_dict['tags'] == ['red', 'green']

    image_girl_dict = await DataRoom.get_image(image_girl.id)
    assert image_girl_dict['tags'] == ['red', 'green', 'blue']

    image_perfume_dict = await DataRoom.get_image(image_perfume.id)
    assert image_perfume_dict['tags'] == ['blue']


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_tag_images_on_wrong_image_id_raises(DataRoom, image_logo):
    await DataRoom.create_tag(name='example')
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.tag_images(image_ids=[image_logo.id, 'fail', '2'], tag_names=['example'])
    assert "One or more images do not exist" in str(excinfo.value)
