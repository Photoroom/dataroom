import os
from django.conf import settings
import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.choices import DuplicateState
from backend.dataroom.models.latents import LatentType
from backend.dataroom.models.os_image import OSImage, OSAttributes, OSLatents
from backend.task_runner.tasks.delete_images import (
    get_images_marked_as_duplicates,
    image_delete_duplicates,
    get_images_marked_for_deletion,
    image_delete_marked_for_deletion,
)
from backend.task_runner.tasks.delete_latents import get_disabled_latent_types, get_images_with_disabled_latents, image_delete_latents
from backend.task_runner.tasks.update_images import (
    get_images_without_duplicate_state,
)
from dataroom_client.dataroom_client.client import DataRoomFile


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_image_attributes(image_logo):
    assert isinstance(image_logo.attributes, OSAttributes)
    assert isinstance(image_logo.latents, OSLatents)
    assert isinstance(image_logo.duplicate_state, DuplicateState)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_create_image_sizes(image_logo, image_girl, image_perfume):
    assert image_logo.width == 180
    assert image_logo.height == 180
    assert image_logo.short_edge == 180
    assert image_logo.aspect_ratio == 1.0
    assert image_logo.aspect_ratio_fraction == '1:1'
    assert image_logo.image_hash.startswith('sha256:')
    assert len(image_logo.image_hash) == 7 + 64

    assert image_girl.width == 400
    assert image_girl.height == 266
    assert image_girl.short_edge == 266
    assert image_girl.aspect_ratio == 400 / 266
    assert image_girl.aspect_ratio_fraction == '3:2'
    assert image_girl.image_hash.startswith('sha256:')
    assert len(image_girl.image_hash) == 7 + 64

    assert image_perfume.width == 120
    assert image_perfume.height == 160
    assert image_perfume.short_edge == 120
    assert image_perfume.aspect_ratio == 0.75
    assert image_perfume.aspect_ratio_fraction == '3:4'
    assert image_perfume.image_hash.startswith('sha256:')
    assert len(image_perfume.image_hash) == 7 + 64


@pytest.mark.django_db
def test_update_thumbnail(image_logo, tests_path):
    # first, remove existing thumbnail
    image_logo.thumbnail = None
    image_logo.save(fields=['thumbnail'])
    image_logo = OSImage.objects.get(id=image_logo.id)
    assert not image_logo.thumbnail

    # call update_thumbnail
    image_logo.update_thumbnail()
    image_logo = OSImage.objects.get(id=image_logo.id)
    assert image_logo.thumbnail == 'images/test-logo/thumbnail.png'
    assert image_logo.thumbnail_url == '/media/images/test-logo/thumbnail.png'
    assert image_logo.thumbnail_direct_url == '/media/images/test-logo/thumbnail.png'


@pytest.mark.django_db
def test_update_coca_embedding(image_logo, mocker):
    # remove existing embedding
    image_logo.coca_embedding_exists = False
    image_logo.coca_embedding_author = None
    image_logo.coca_embedding_vector = None
    image_logo.save(fields=['coca_embedding'])

    image_logo = OSImage.objects.get(id=image_logo.id)
    assert image_logo.coca_embedding_exists is False
    assert image_logo.coca_embedding_author is None
    assert image_logo.coca_embedding_vector is None

    # Mock the fetch_coca_embedding function to return a test vector
    mock_vector = [0.1] * 768
    mocker.patch('backend.dataroom.models.os_image.fetch_coca_embedding', return_value=mock_vector)

    # update the embedding
    image_logo.update_coca_embedding(author='test@example.com')
    image_logo = OSImage.objects.get(id=image_logo.id)

    assert image_logo.coca_embedding_exists is True
    assert image_logo.coca_embedding_author == 'test@example.com'
    assert image_logo.coca_embedding_vector is not None


@pytest.mark.django_db
def test_embedding_get_similarity(
    image_logo,
    image_logo_alt,
    image_logo_small,
    image_girl,
    image_perfume,
):
    similarity = image_logo.get_similarity(image_logo)
    assert round(similarity, 3) == 1.0

    similarity = image_logo.get_similarity(image_logo_alt)
    assert round(similarity, 3) == 0.946

    similarity = image_logo.get_similarity(image_logo_small)
    assert round(similarity, 3) == 0.866

    similarity = image_logo.get_similarity(image_girl)
    assert round(similarity, 3) == 0.329

    similarity = image_logo.get_similarity(image_perfume)
    assert round(similarity, 3) == 0.397


@pytest.mark.django_db
def test_embedding_find_similar(
    image_logo,
    image_logo_alt,
    image_logo_small,
    image_girl,
    image_perfume,
):
    similar = image_logo.find_similar()
    assert len(similar) == 4  # does not include self
    assert [s.id for s in similar] == [i.id for i in [image_logo_alt, image_logo_small, image_perfume, image_girl]]
    assert round(similar[0].similarity_from_score, 3) == 0.946
    assert round(similar[1].similarity_from_score, 3) == 0.866
    assert round(similar[2].similarity_from_score, 3) == 0.397
    assert round(similar[3].similarity_from_score, 3) == 0.329

    # apply limit
    similar = image_logo.find_similar(number=2)
    assert len(similar) == 2
    assert [s.id for s in similar] == [i.id for i in [image_logo_alt, image_logo_small]]


@pytest.mark.django_db
def test_mark_duplicates(image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):
    images = get_images_without_duplicate_state()
    assert len(images) == 5

    # duplicates are marked
    OSImage.mark_duplicates(image_id=image_logo.id, threshold=0.8)

    image_logo = OSImage.objects.get(id=image_logo.id)
    image_logo_alt = OSImage.objects.get(id=image_logo_alt.id)
    image_logo_small = OSImage.objects.get(id=image_logo_small)
    image_girl = OSImage.objects.get(id=image_girl.id)
    image_perfume = OSImage.objects.get(id=image_perfume.id)

    assert image_logo.duplicate_state is DuplicateState.ORIGINAL
    assert image_logo_alt.duplicate_state is DuplicateState.DUPLICATE
    assert image_logo_small.duplicate_state is DuplicateState.DUPLICATE
    assert image_girl.duplicate_state is DuplicateState.UNPROCESSED
    assert image_perfume.duplicate_state is DuplicateState.UNPROCESSED

    # no duplicates should be found, so the original should be marked
    OSImage.mark_duplicates(image_id=image_perfume.id, threshold=0.9)

    image_logo = OSImage.objects.get(id=image_logo.id)
    image_logo_alt = OSImage.objects.get(id=image_logo_alt.id)
    image_logo_small = OSImage.objects.get(id=image_logo_small)
    image_girl = OSImage.objects.get(id=image_girl.id)
    image_perfume = OSImage.objects.get(id=image_perfume.id)

    assert image_logo.duplicate_state is DuplicateState.ORIGINAL
    assert image_logo_alt.duplicate_state is DuplicateState.DUPLICATE
    assert image_logo_small.duplicate_state is DuplicateState.DUPLICATE
    assert image_girl.duplicate_state is DuplicateState.UNPROCESSED
    assert image_perfume.duplicate_state is DuplicateState.ORIGINAL


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_delete_duplicates(tests_path, DataRoom, image_logo, image_logo_alt, image_logo_small, image_girl, image_perfume):

    # create some latents
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)
    await DataRoom.set_image_latent(image_id=image_logo.id, latent_file=latent_file, latent_type='example')
    await DataRoom.set_image_latent(image_id=image_logo_alt.id, latent_file=latent_file, latent_type='example')
    await DataRoom.set_image_latent(image_id=image_logo_small.id, latent_file=latent_file, latent_type='example')
    await DataRoom.set_image_latent(image_id=image_girl.id, latent_file=latent_file, latent_type='example')

    # mark some duplicates
    image_logo.duplicate_state = DuplicateState.ORIGINAL
    image_logo_alt.duplicate_state = DuplicateState.DUPLICATE
    image_logo_small.duplicate_state = DuplicateState.DUPLICATE
    image_girl.duplicate_state = DuplicateState.UNPROCESSED
    image_perfume.duplicate_state = DuplicateState.UNPROCESSED
    await sync_to_async(image_logo.save)(fields=['duplicate_state'])
    await sync_to_async(image_logo_alt.save)(fields=['duplicate_state'])
    await sync_to_async(image_logo_small.save)(fields=['duplicate_state'])
    await sync_to_async(image_girl.save)(fields=['duplicate_state'])
    await sync_to_async(image_perfume.save)(fields=['duplicate_state'])

    image_ids = await sync_to_async(get_images_marked_as_duplicates)(sources=['test'])
    assert image_ids == ['test-logo_alt', 'test-logo_small']

    # reload from os
    image_logo = await sync_to_async(OSImage.objects.get)(id=image_logo.id, fields=['id', 'image', 'thumbnail', 'latents'])
    image_logo_alt = await sync_to_async(OSImage.objects.get)(id=image_logo_alt.id, fields=['id', 'image', 'thumbnail', 'latents'])
    image_logo_small = await sync_to_async(OSImage.objects.get)(id=image_logo_small.id, fields=['id', 'image', 'thumbnail', 'latents'])
    image_girl = await sync_to_async(OSImage.objects.get)(id=image_girl.id, fields=['id', 'image', 'thumbnail', 'latents'])
    image_perfume = await sync_to_async(OSImage.objects.get)(id=image_perfume.id, fields=['id', 'image', 'thumbnail', 'latents'])

    # check files exist
    existing_paths = [
        image_logo.image,
        image_logo.thumbnail,
        image_logo.latents.latents['example'].file,
        image_logo_alt.image,
        image_logo_alt.thumbnail,
        image_logo_alt.latents.latents['example'].file,
        image_logo_small.image,
        image_logo_small.thumbnail,
        image_logo_small.latents.latents['example'].file,
        image_girl.image,
        image_girl.thumbnail,
        image_girl.latents.latents['example'].file,
        image_perfume.image,
        image_perfume.thumbnail,
    ]
    for path in existing_paths:
        assert os.path.exists(settings.MEDIA_ROOT / path)

    # delete duplicates
    for image_id in image_ids:
        await sync_to_async(image_delete_duplicates)(image_id=image_id)

    # check that the duplicates are deleted
    duplicate_image_ids = await sync_to_async(get_images_marked_as_duplicates)(sources=['test'])
    assert len(duplicate_image_ids) == 0

    all_images = await sync_to_async(OSImage.objects.all)()
    assert len(all_images) == 3
    assert [i.id for i in all_images] == [image_girl.id, image_logo.id, image_perfume.id]

    # check that only the duplicate files are deleted
    existing_paths = [
        image_logo.image,
        image_logo.thumbnail,
        image_logo.latents.latents['example'].file,
        image_girl.image,
        image_girl.thumbnail,
        image_girl.latents.latents['example'].file,
        image_perfume.image,
        image_perfume.thumbnail,
    ]
    deleted_paths = [
        image_logo_alt.image,
        image_logo_alt.thumbnail,
        image_logo_alt.latents.latents['example'].file,
        image_logo_small.image,
        image_logo_small.thumbnail,
        image_logo_small.latents.latents['example'].file,
    ]
    for path in existing_paths:
        assert os.path.exists(settings.MEDIA_ROOT / path)
    for path in deleted_paths:
        assert not os.path.exists(settings.MEDIA_ROOT / path)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_permanent_deletion(tests_path, DataRoom, image_logo, image_girl):

    # create some latents
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)
    await DataRoom.set_image_latent(image_id=image_logo.id, latent_file=latent_file, latent_type='example')
    await DataRoom.set_image_latent(image_id=image_girl.id, latent_file=latent_file, latent_type='example')

    # mark logo as deleted
    image_logo.is_deleted = True
    await sync_to_async(image_logo.save)(fields=['is_deleted'])

    to_delete_image_ids = await sync_to_async(get_images_marked_for_deletion)()
    assert to_delete_image_ids == ['test-logo']

    # reload from os
    image_logo = await sync_to_async(OSImage.all_objects.get)(id=image_logo.id, fields=['id', 'image', 'thumbnail', 'latents', 'is_deleted'])
    image_girl = await sync_to_async(OSImage.all_objects.get)(id=image_girl.id, fields=['id', 'image', 'thumbnail', 'latents', 'is_deleted'])

    # check files exist
    existing_paths = [
        image_logo.image,
        image_logo.thumbnail,
        image_logo.latents.latents['example'].file,
        image_girl.image,
        image_girl.thumbnail,
        image_girl.latents.latents['example'].file,
    ]
    for path in existing_paths:
        assert os.path.exists(settings.MEDIA_ROOT / path)

    # delete marked for deletion
    for image_id in to_delete_image_ids:
        await sync_to_async(image_delete_marked_for_deletion)(image_id=image_id)

    # check they are deleted
    to_delete_image_ids = await sync_to_async(get_images_marked_for_deletion)()
    assert to_delete_image_ids == []

    all_images = await sync_to_async(OSImage.objects.all)()
    assert [i.id for i in all_images] == ['test-girl']

    # check that only logo files are deleted
    existing_paths = [
        image_girl.image,
        image_girl.thumbnail,
        image_girl.latents.latents['example'].file,
    ]
    deleted_paths = [
        image_logo.image,
        image_logo.thumbnail,
        image_logo.latents.latents['example'].file,
    ]
    for path in existing_paths:
        print(settings.MEDIA_ROOT / path)
        assert os.path.exists(settings.MEDIA_ROOT / path)
    for path in deleted_paths:
        print(settings.MEDIA_ROOT / path)
        assert not os.path.exists(settings.MEDIA_ROOT / path)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_delete_disabled_latents(tests_path, DataRoom, image_logo):
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')
    mask_file_2 = DataRoomFile.from_path(tests_path / 'images/logo_small.png')

    await sync_to_async(LatentType.objects.create)(name='example', is_mask=False)
    await sync_to_async(LatentType.objects.create)(name='mask', is_mask=True)
    await sync_to_async(LatentType.objects.create)(name='mask_2', is_mask=True)

    await DataRoom.set_image_latent(image_id=image_logo.id, latent_file=latent_file, latent_type='example')
    await DataRoom.set_image_latent(image_id=image_logo.id, latent_file=mask_file, latent_type='mask')
    await DataRoom.set_image_latent(image_id=image_logo.id, latent_file=mask_file_2, latent_type='mask_2')
    image_logo = await sync_to_async(OSImage.objects.get)(id=image_logo.id, fields=['id', 'latents'])
    example_latent_path = settings.MEDIA_ROOT / image_logo.latents.latents['example'].file
    mask_latent_path = settings.MEDIA_ROOT / image_logo.latents.latents['mask'].file
    mask_2_latent_path = settings.MEDIA_ROOT / image_logo.latents.latents['mask_2'].file
    disabled_latents = await sync_to_async(get_disabled_latent_types)()
    assert disabled_latents == []
    image_ids = await sync_to_async(get_images_with_disabled_latents)(disabled_latents)
    assert image_ids == []

    assert os.path.exists(example_latent_path)
    assert os.path.exists(mask_latent_path)

    # disable example and mask_2 latents
    await sync_to_async(LatentType.objects.filter(name__in=['example', 'mask_2']).update)(is_enabled=False)

    disabled_latents = await sync_to_async(get_disabled_latent_types)()
    assert disabled_latents == ['example', 'mask_2']
    image_ids = await sync_to_async(get_images_with_disabled_latents)(disabled_latents)
    assert image_ids == [image_logo.id]

    # delete example and mask_2 latents
    await sync_to_async(image_delete_latents)(image_logo.id, disabled_latents)

    assert not os.path.exists(example_latent_path)
    assert os.path.exists(mask_latent_path)  # mask is still enabled
    assert not os.path.exists(mask_2_latent_path)

    image_ids = await sync_to_async(get_images_with_disabled_latents)(disabled_latents)
    assert image_ids == []
