import pytest
from asgiref.sync import sync_to_async
from django.core.files.storage import default_storage

from backend.dataroom.models.latents import LatentType
from backend.dataroom.models.os_image import OSImage
from dataroom_client import DataRoomFile, DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_set_image_latent(DataRoom, tests_path, image_logo):
    image = await DataRoom.get_image(image_logo.id)
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    latent_file_2 = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')

    # can't create without a LatentType
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.set_image_latent(
            image_id=image['id'],
            latent_file=latent_file,
            latent_type='example',
        )
    assert "Latent type 'example' does not exist" in str(excinfo.value)

    # create the LatentType
    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)

    # try again
    image = await DataRoom.set_image_latent(
        image_id=image['id'],
        latent_file=latent_file,
        latent_type='example',
    )
    assert len(image['latents']) == 1
    assert image['latents'][0]['latent_type'] == 'example'
    assert image['latents'][0]['file_direct_url'] == '/media/images/test-logo/latent_example.txt'
    old_file = image['latents'][0]['file_direct_url']
    old_date_updated = image['date_updated']

    image_instance = await sync_to_async(OSImage.objects.get)(id=image['id'])
    file_path = default_storage.base_location / image_instance.latents.latents['example'].file

    # file exists
    assert default_storage.exists(file_path) is True

    # update replaces the file
    image = await DataRoom.set_image_latent(
        image_id=image['id'],
        latent_file=latent_file_2,
        latent_type='example',
    )
    assert len(image['latents']) == 1
    assert image['latents'][0]['latent_type'] == 'example'
    assert image['latents'][0]['file_direct_url'] == '/media/images/test-logo/latent_example.png'
    assert image['latents'][0]['file_direct_url'] != old_file  # file is different
    assert image['date_updated'] != old_date_updated  # date updated is different

    # image still has only 1 latent
    image = await DataRoom.get_image(image['id'], fields=['latents'])
    assert len(image['latents']) == 1

    # and still one LatentType
    latent_types = await sync_to_async(list)(LatentType.objects.all())
    assert len(latent_types) == 1
    assert latent_types[0].name == 'example'
    assert latent_types[0].is_mask is False


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_delete_image_latent(DataRoom, tests_path, image_logo):
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')

    # first create
    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)
    await sync_to_async(LatentType.objects.create)(name='mask', is_mask=True)
    response = await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=latent_file,
        latent_type='example',
    )
    response = await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=mask_file,
        latent_type='mask',
    )

    # image has 2 latents
    image = await DataRoom.get_image(image_logo.id, fields=['latents'])
    assert len(image['latents']) == 2
    image_instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    # file exists
    latent_file_path = default_storage.base_location / image_instance.latents.latents['example'].file
    mask_file_path = default_storage.base_location / image_instance.latents.latents['mask'].file
    assert default_storage.exists(latent_file_path) is True
    assert default_storage.exists(mask_file_path) is True

    # delete
    await DataRoom.delete_image_latent(image['id'], 'example')

    # image has 1 latent
    image = await DataRoom.get_image(image['id'], fields=['latents'])
    assert len(image['latents']) == 1

    # file was deleted
    assert default_storage.exists(latent_file_path) is False

    # mask still exists
    assert image['latents'][0]['latent_type'] == 'mask'
    assert default_storage.exists(mask_file_path) is True

    # delete again raises
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.delete_image_latent(image['id'], 'example')
    assert 'Latent not found' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_latent_valid_chars(DataRoom, tests_path, image_logo):
    image = await DataRoom.get_image(image_logo.id)
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.set_image_latent(image_id=image['id'], latent_file=latent_file, latent_type='fail.txt')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.set_image_latent(image_id=image['id'], latent_file=latent_file, latent_type='fa il')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)

    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.set_image_latent(image_id=image['id'], latent_file=latent_file, latent_type='fa/il')
    assert 'Can only contain alphanumeric characters' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_filter_images_by_latent_and_mask(
    DataRoom, tests_path, image_logo, image_logo_alt, image_girl, image_perfume, image_logo_small,
):
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')

    latents = {
        "latent_one": [image_logo, image_logo_alt],
        "latent_two": [image_logo, image_girl],
        "latent_three": [image_girl],
        "latent_four": [image_perfume],
    }
    masks = {
        "mask_one": [image_logo, image_logo_alt],
        "mask_two": [image_logo, image_girl],
        "mask_three": [image_girl],
        "mask_four": [image_logo_small],
    }

    for latent_type, images in latents.items():
        await sync_to_async(LatentType.objects.create)(name=latent_type, is_mask=False)
        for image in images:
            await DataRoom.set_image_latent(
                image_id=image.id,
                latent_file=latent_file,
                latent_type=latent_type,
            )
    for mask_type, images in masks.items():
        await sync_to_async(LatentType.objects.create)(name=mask_type, is_mask=True)
        for image in images:
            await DataRoom.set_image_latent(
                image_id=image.id,
                latent_file=mask_file,
                latent_type=mask_type,
            )

    # has_latents invalid
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(has_latents=['fail1'])
    assert "Latent type 'fail1' does not exist" in str(excinfo.value)

    # has_masks invalid
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.get_images(has_masks=['fail2'])
    assert "Latent type 'fail2' does not exist" in str(excinfo.value)

    # has_latents
    response = await DataRoom.get_images(has_latents=['latent_one'])
    assert [i['id'] for i in response] == [image_logo.id, image_logo_alt.id]

    response = await DataRoom.get_images(has_latents=['latent_two'])
    assert [i['id'] for i in response] == [image_girl.id, image_logo.id]

    response = await DataRoom.get_images(has_latents=['latent_two', 'latent_three'])
    assert [i['id'] for i in response] == [image_girl.id]

    # lacks_latents
    response = await DataRoom.get_images(lacks_latents=['latent_one'])
    assert [i['id'] for i in response] == [image_girl.id, image_logo_small.id, image_perfume.id]

    response = await DataRoom.get_images(lacks_latents=['latent_two'])
    assert [i['id'] for i in response] == [image_logo_alt.id, image_logo_small.id, image_perfume.id]

    response = await DataRoom.get_images(lacks_latents=['latent_one', 'latent_two'])
    assert [i['id'] for i in response] == [image_logo_small.id, image_perfume.id]

    # has_masks
    response = await DataRoom.get_images(has_masks=['mask_one'])
    assert [i['id'] for i in response] == [image_logo.id, image_logo_alt.id]

    response = await DataRoom.get_images(has_masks=['mask_two'])
    assert [i['id'] for i in response] == [image_girl.id, image_logo.id]

    response = await DataRoom.get_images(has_masks=['mask_two', 'mask_three'])
    assert [i['id'] for i in response] == [image_girl.id]

    # lacks_masks
    response = await DataRoom.get_images(lacks_masks=['mask_one'])
    assert [i['id'] for i in response] == [image_girl.id, image_logo_small.id, image_perfume.id]

    response = await DataRoom.get_images(lacks_masks=['mask_two'])
    assert [i['id'] for i in response] == [image_logo_alt.id, image_logo_small.id, image_perfume.id]

    response = await DataRoom.get_images(lacks_masks=['mask_one', 'mask_two'])
    assert [i['id'] for i in response] == [image_logo_small.id, image_perfume.id]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_images_return_latents(DataRoom, tests_path, image_logo):
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')

    # create latents
    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)
    await sync_to_async(LatentType.objects.create)(name='mask', is_mask=True)
    response = await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=latent_file,
        latent_type='example',
    )
    response = await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=mask_file,
        latent_type='mask',
    )

    # test get_images
    images = await DataRoom.get_images(all_fields=True)
    assert len(images[0]['latents']) == 2

    images = await DataRoom.get_images(all_fields=True, return_latents=['example'])
    assert len(images[0]['latents']) == 1
    assert images[0]['latents'][0]['latent_type'] == 'example'

    images = await DataRoom.get_images(all_fields=True, return_latents=['mask'])
    assert len(images[0]['latents']) == 1
    assert images[0]['latents'][0]['latent_type'] == 'mask'

    # test get_image
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert len(image['latents']) == 2

    image = await DataRoom.get_image(image_logo.id, all_fields=True, return_latents=['example'])
    assert len(image['latents']) == 1
    assert image['latents'][0]['latent_type'] == 'example'
