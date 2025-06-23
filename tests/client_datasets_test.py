import uuid
import pytest
from asgiref.sync import sync_to_async
from backend.dataroom.models.os_image import OSImage
from dataroom_client import DataRoomError
from dataroom_client.dataroom_client.client import DataRoomFile


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_dataset(DataRoom):
    datasets = await DataRoom.get_datasets()
    assert len(datasets) == 0

    # create dataset without description
    dataset = await DataRoom.create_dataset(name='Test Dataset', slug='test')
    assert dataset['name'] == 'Test Dataset'
    assert dataset['slug'] == 'test'
    assert dataset['version'] == 1
    assert dataset['description'] == ''

    # create dataset with description
    dataset = await DataRoom.create_dataset(name='Test Dataset 2', slug='test', description='Test description')
    assert dataset['name'] == 'Test Dataset 2'
    assert dataset['slug'] == 'test'
    assert dataset['version'] == 2  # version is incremented
    assert dataset['description'] == 'Test description'

    # get dataset
    dataset = await DataRoom.get_dataset(slug_version='test/2')
    assert dataset['name'] == 'Test Dataset 2'
    assert dataset['slug'] == 'test'
    assert dataset['version'] == 2
    assert dataset['description'] == 'Test description'


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_dataset_with_invalid_slug(DataRoom):
    # too long slug
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_dataset(name='Test Dataset', slug='a' * 101)
    assert 'Ensure this field has no more than 100 characters' in str(excinfo.value)

    # slug with spaces
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_dataset(name='Test Dataset', slug='test dataset')
    assert 'Enter a valid \\"slug\\"' in str(excinfo.value)

    # slug with invalid characters
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.create_dataset(name='Test Dataset', slug='test@dataset')
    assert 'Enter a valid \\"slug\\"' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_datasets(DataRoom, tests_path):
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.create_dataset(name='Test', slug='test')
    
    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')

    image_id = str(uuid.uuid4())
    datasets = ['test/1', 'test/2']
    image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', datasets=datasets)
    instance = await sync_to_async(OSImage.objects.get)(id=image['id'])

    assert instance.id == image_id
    assert instance.datasets.datasets == datasets
    
    image = await DataRoom.get_image(image_id, all_fields=True)
    assert image['datasets'] == datasets
    

@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_datasets_invalid(DataRoom, tests_path):
    await DataRoom.create_dataset(name='Test', slug='test')

    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image_id = str(uuid.uuid4())

    datasets = ['wrong',]
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', datasets=datasets)
    assert 'Invalid datasets: wrong' in str(excinfo.value)

    datasets = ['doesnotexist/1',]
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', datasets=datasets)
    assert 'Invalid datasets: doesnotexist/1' in str(excinfo.value)
    

@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_with_datasets_frozen(DataRoom, tests_path):
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.freeze_dataset(slug_version='test/1')

    image_file = DataRoomFile.from_path(tests_path / 'images/logo.png')
    image_id = str(uuid.uuid4())

    datasets = ['test/1', 'test/2']
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.create_image(image_id=image_id, image_file=image_file, source='test', datasets=datasets)
    assert 'Invalid datasets: test/1' in str(excinfo.value)

    # did not create image
    with pytest.raises(OSImage.DoesNotExist) as excinfo:
        existing = await sync_to_async(OSImage.objects.get)(id=image_id)
    assert 'not found' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_datasets(DataRoom, image_logo, image_logo_alt):
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.create_dataset(name='Test', slug='test')
    
    datasets = ['test/1', 'test/2']
    image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['datasets'] == datasets

    # updates will merge with existing list of datasets
    datasets = ['test/1', 'test/3']
    image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['datasets'] == ['test/1', 'test/2', 'test/3']

    # will do nothing
    datasets = []
    image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['datasets'] == ['test/1', 'test/2', 'test/3']

    # will do nothing
    datasets = None
    image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    image = await DataRoom.get_image(image_logo.id, all_fields=True)
    assert image['datasets'] == ['test/1', 'test/2', 'test/3']
    

@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_datasets_invalid(DataRoom, tests_path, image_logo):
    await DataRoom.create_dataset(name='Test', slug='test')

    datasets = ['wrong',]
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    assert 'Invalid datasets: wrong' in str(excinfo.value)

    datasets = ['doesnotexist/1',]
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    assert 'Invalid datasets: doesnotexist/1' in str(excinfo.value)
    

@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_image_with_datasets_frozen(DataRoom, tests_path, image_logo):
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.freeze_dataset(slug_version='test/1')

    datasets = ['test/1', 'test/2']
    with pytest.raises(DataRoomError) as excinfo:
        image = await DataRoom.update_image(image_id=image_logo.id, datasets=datasets)
    assert 'Invalid datasets: test/1' in str(excinfo.value)

    # did not update image
    instance = await sync_to_async(OSImage.objects.get)(id=image_logo.id)
    assert instance.datasets.datasets == []


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_add_images(DataRoom, image_logo, image_girl, image_perfume):
    # create dataset
    dataset = await DataRoom.create_dataset(name='Test', slug='test')

    # add images to dataset
    response = await DataRoom.dataset_add_images(slug_version='test/1', image_ids=[image_logo.id, image_girl.id])
    assert response['updated_count'] == 2

    # verify images were added
    images = await DataRoom.get_images(datasets=['test/1'])
    assert [img['id'] for img in images] == [image_girl.id, image_logo.id]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_remove_images(DataRoom, image_logo, image_girl, image_perfume):
    # create dataset
    dataset = await DataRoom.create_dataset(name='Test', slug='test')

    # add images to dataset
    await DataRoom.dataset_add_images(slug_version='test/1', image_ids=[image_logo.id, image_girl.id, image_perfume.id])

    # remove some images
    response = await DataRoom.dataset_remove_images(slug_version='test/1', image_ids=[image_logo.id, image_girl.id])
    assert response['updated_count'] == 2

    # verify images were removed
    images = await DataRoom.get_images(datasets=['test/1'])
    assert [img['id'] for img in images] == [image_perfume.id]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_add_images_frozen(DataRoom, image_logo, image_girl, image_perfume):
    # create dataset
    dataset = await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.freeze_dataset(slug_version='test/1')

    # can't add images to frozen dataset
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.dataset_add_images(slug_version='test/1', image_ids=[image_logo.id, image_girl.id])
    assert 'Dataset is frozen' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_remove_images_frozen(DataRoom, image_logo, image_girl, image_perfume):
    # create dataset
    dataset = await DataRoom.create_dataset(name='Test', slug='test')
    await DataRoom.freeze_dataset(slug_version='test/1')

    # can't remove images from frozen dataset
    with pytest.raises(DataRoomError) as excinfo:
        await DataRoom.dataset_remove_images(slug_version='test/1', image_ids=[image_logo.id, image_girl.id])
    assert 'Dataset is frozen' in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_filter(DataRoom, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    # create datasets
    dataset_logos = await DataRoom.create_dataset(name='Logos', slug='logos')
    dataset_logos_alt = await DataRoom.create_dataset(name='Logos', slug='logos')
    dataset_people = await DataRoom.create_dataset(name='People', slug='people')
    dataset_objects = await DataRoom.create_dataset(name='Objects', slug='objects')

    # add images to dataset
    await DataRoom.update_image(image_logo.id, datasets=['logos/1'])
    await DataRoom.update_image(image_logo_small.id, datasets=['logos/1', 'logos/2'])
    await DataRoom.update_image(image_logo_alt.id, datasets=['logos/2'])

    await DataRoom.update_image(image_girl.id, datasets=['people/1'])

    # single dataset
    images = await DataRoom.get_images(datasets=['objects/1'])
    assert [img['id'] for img in images] == []
    images = await DataRoom.get_images(datasets=['logos/1'])
    assert [img['id'] for img in images] == [image_logo.id, image_logo_small.id]

    # match any dataset
    images = await DataRoom.get_images(datasets=['logos/1', 'logos/2'])
    assert [img['id'] for img in images] == [image_logo.id, image_logo_alt.id, image_logo_small.id]

    # match all datasets
    images = await DataRoom.get_images(datasets__all=['logos/1', 'logos/2'])
    assert [img['id'] for img in images] == [image_logo_small.id]

    # match not having any of the datasets
    images = await DataRoom.get_images(datasets__ne=['logos/1', 'logos/2'])
    assert [img['id'] for img in images] == [image_girl.id, image_perfume.id]

    # match not having all of the datasets
    images = await DataRoom.get_images(datasets__ne_all=['logos/1', 'logos/2'])
    assert [img['id'] for img in images] == [image_girl.id, image_logo.id, image_logo_alt.id, image_perfume.id]

    # match empty datasets
    images = await DataRoom.get_images(datasets__empty=True)
    assert [img['id'] for img in images] == [image_perfume.id]
