import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.models import AttributesField, AttributesSchema, LatentType
from backend.dataroom.models.os_image import OSImage
from dataroom_client import DataRoomFile


@pytest.mark.django_db
def test_os_image_serialized_simple(image_logo):
    es_doc = image_logo.to_doc()
    assert es_doc == {
        "id": "test-logo",
        "source": "test",
        "image": "images/test-logo/original.png",
        "date_created": image_logo.date_created,
        "date_updated": image_logo.date_updated,
        "is_deleted": False,
        "author": "user@example.com",
        "image_hash": image_logo.image_hash,
        "width": 180,
        "height": 180,
        "short_edge": 180,
        "pixel_count": 180*180,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": "images/test-logo/thumbnail.png",
        "thumbnail_error": False,
        "original_url": None,
        "tags": [],
        "coca_embedding_exists": True,
        "coca_embedding_vector": image_logo.coca_embedding_vector,
        "coca_embedding_author": "user@example.com",
        "duplicate_state": None,
        "related_images": {},
        "datasets": [],
    }

    es_json = image_logo.to_json(all_fields=True)
    assert es_json == {
        "id": "test-logo",
        "source": "test",
        "image": "/media/images/test-logo/original.png",
        "image_direct_url": "/media/images/test-logo/original.png",
        "date_created": image_logo.date_created,
        "date_updated": image_logo.date_updated,
        "author": "user@example.com",
        "image_hash": image_logo.image_hash,
        "width": 180,
        "height": 180,
        "short_edge": 180,
        "pixel_count": 180*180,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": "/media/images/test-logo/thumbnail.png",
        "thumbnail_error": False,
        "thumbnail_direct_url": "/media/images/test-logo/thumbnail.png",
        "original_url": None,
        "tags": [],
        "coca_embedding": {
            "vector": image_logo.coca_embedding_vector,
            "author": "user@example.com",
        },
        "latents": [],
        "attributes": {},
        "duplicate_state": None,
        "related_images": {},
        "datasets": [],
    }


@pytest.mark.django_db
def test_os_image_to_doc_fields(image_logo):
    # test specifying doc fields
    es_doc = image_logo.to_doc(fields=["id", "source", "date_created"])
    assert es_doc == {
        "id": "test-logo",
        "source": "test",
        "date_created": image_logo.date_created,
    }

    # invalid field
    with pytest.raises(ValueError) as exc:
        es_doc = image_logo.to_doc(fields=["id", "fail"])
    assert str(exc.value) == "Invalid field: fail"


@pytest.mark.django_db
def test_os_image_serialized_no_coca(os_image):
    es_doc = os_image.to_doc(fields=["coca_embedding"])
    assert es_doc == {
        "coca_embedding_exists": False,
        "coca_embedding_vector": None,
        "coca_embedding_author": None,
    }

    es_doc = os_image.to_doc()
    assert es_doc == {
        "id": "test-image",
        "source": "test",
        "image": "images/test-image/original.png",
        "date_created": os_image.date_created,
        "date_updated": os_image.date_updated,
        "is_deleted": False,
        "author": "user@example.com",
        "image_hash": os_image.image_hash,
        "width": 10,
        "height": 10,
        "short_edge": 10,
        "pixel_count": 10*10,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": None,
        "thumbnail_error": False,
        "original_url": None,
        "tags": [],
        "coca_embedding_exists": False,
        "coca_embedding_vector": None,
        "coca_embedding_author": None,
        "duplicate_state": None,
        "related_images": {},
        "datasets": [],
    }

    es_json = os_image.to_json(all_fields=True)
    assert es_json == {
        "id": "test-image",
        "source": "test",
        "image": "/media/images/test-image/original.png",
        "image_direct_url": "/media/images/test-image/original.png",
        "date_created": os_image.date_created,
        "date_updated": os_image.date_updated,
        "author": "user@example.com",
        "image_hash": os_image.image_hash,
        "width": 10,
        "height": 10,
        "short_edge": 10,
        "pixel_count": 10*10,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": None,
        "thumbnail_error": False,
        "thumbnail_direct_url": None,
        "original_url": None,
        "tags": [],
        "coca_embedding": None,
        "latents": [],
        "attributes": {},
        "duplicate_state": None,
        "related_images": {},
        "datasets": [],
    }


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_os_image_serialized_complex(DataRoom, tests_path, image_logo):
    # create some latents
    latent_file = DataRoomFile.from_path(tests_path / 'images/logo_latent.txt')
    await sync_to_async(LatentType.objects.create)(name='example_latent', is_mask=False)
    await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=latent_file,
        latent_type='example_latent',
    )
    mask_file = DataRoomFile.from_path(tests_path / 'images/logo_mask.png')
    await sync_to_async(LatentType.objects.create)(name='example_mask', is_mask=True)
    await DataRoom.set_image_latent(
        image_id=image_logo.id,
        latent_file=mask_file,
        latent_type='example_mask',
    )
    # add some tags
    await DataRoom.create_tag(name='red')
    await DataRoom.create_tag(name='green')
    await DataRoom.create_tag(name='blue')
    await DataRoom.tag_images(image_ids=[image_logo.id], tag_names=['red', 'green'])

    # define attributes
    await sync_to_async(AttributesField.objects.create)(name="name", field_type="string", is_indexed=True)
    await sync_to_async(AttributesField.objects.create)(name="approved", field_type="boolean", is_required=True, is_indexed=False)
    await sync_to_async(AttributesField.objects.create)(name="date", field_type="string", string_format="date-time", is_indexed=True)
    await sync_to_async(AttributesField.objects.create)(name="some_number", field_type="number", enum_choices=[1, 2, 3], is_indexed=True)
    await sync_to_async(AttributesField.objects.create)(name="disabled", field_type="string", is_enabled=False, is_indexed=True)
    await sync_to_async(AttributesField.objects.create)(name="numbers", field_type="array", array_type="number", is_indexed=True)
    # force invalidate cache
    AttributesSchema.invalidate_cache()
    # add some attributes
    await DataRoom.add_image_attributes(
        image_id=image_logo.id,
        attributes={
            'name': 'my name',
            'approved': True,
            'date': '2000-01-01T00:00:00Z',
            'some_number': 2,
            'numbers': [1, 2, 3],
        }
    )

    # create some related images
    await DataRoom.update_image(
        image_id=image_logo.id,
        related_images={
            'test_related_image': 'test-logo',
        },
    )

    # create some datasets
    await DataRoom.create_dataset(name='Test Dataset', slug='test')
    await DataRoom.update_image(
        image_id=image_logo.id,
        datasets=['test/1'],
    )

    # re-fetch image
    image_logo = await sync_to_async(OSImage.objects.get)(image_logo.id)

    # serialize to ES document
    es_doc = await sync_to_async(image_logo.to_doc)()
    assert es_doc == {
        "id": "test-logo",
        "source": "test",
        "image": "images/test-logo/original.png",
        "date_created": image_logo.date_created,
        "date_updated": image_logo.date_updated,
        "is_deleted": False,
        "author": "user@example.com",
        "image_hash": image_logo.image_hash,
        "width": 180,
        "height": 180,
        "short_edge": 180,
        "pixel_count": 180*180,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": "images/test-logo/thumbnail.png",
        "thumbnail_error": False,
        "original_url": None,
        "tags": ["red", "green"],
        "coca_embedding_exists": True,
        "coca_embedding_vector": [float(p) for p in image_logo.coca_embedding_vector],
        "coca_embedding_author": "user@example.com",
        "latent_example_latent_file": 'images/test-logo/latent_example_latent.txt',
        "latent_example_mask_file": 'images/test-logo/latent_example_mask.png',
        "attr_name_text": "my name",
        "attr_noidx_approved_boolean": True,
        "attr_date_date": "2000-01-01T00:00:00Z",
        "attr_some_number_double": 2,
        "attr_numbers_double": [1, 2, 3],
        "duplicate_state": None,
        "related_images": {
            "test_related_image": "test-logo",
        },
        "datasets": ["test/1"],
    }

    # serialize to json
    es_json = await sync_to_async(image_logo.to_json)(all_fields=True)
    assert es_json == {
        "id": "test-logo",
        "source": "test",
        "image": "/media/images/test-logo/original.png",
        "image_direct_url": "/media/images/test-logo/original.png",
        "date_created": image_logo.date_created,
        "date_updated": image_logo.date_updated,
        "author": "user@example.com",
        "image_hash": image_logo.image_hash,
        "width": 180,
        "height": 180,
        "short_edge": 180,
        "pixel_count": 180*180,
        "aspect_ratio": 1.0,
        "aspect_ratio_fraction": "1:1",
        "thumbnail": "/media/images/test-logo/thumbnail.png",
        "thumbnail_error": False,
        "thumbnail_direct_url": "/media/images/test-logo/thumbnail.png",
        "original_url": None,
        "tags": ["red", "green"],
        "coca_embedding": {
            "vector": [float(p) for p in image_logo.coca_embedding_vector],
            "author": "user@example.com",
        },
        "latents": [
            {
                "latent_type": "example_latent",
                "file_direct_url": '/media/images/test-logo/latent_example_latent.txt',
                "is_mask": False,
            },
            {
                "latent_type": "example_mask",
                "file_direct_url": '/media/images/test-logo/latent_example_mask.png',
                "is_mask": True,
            },
        ],
        "attributes": {
            "name": "my name",
            "approved": True,
            "date": "2000-01-01T00:00:00Z",
            "some_number": 2,
            "numbers": [1, 2, 3],
        },
        "duplicate_state": None,
        "related_images": {
            "test_related_image": "test-logo",
        },
        "datasets": ["test/1"],
    }

    # test specifying doc fields

    es_doc = image_logo.to_doc(fields=["id"])
    assert es_doc == {
        "id": "test-logo",
    }
    es_doc = image_logo.to_doc(fields=["source"])
    assert es_doc == {
        "source": "test",
    }
    es_doc = image_logo.to_doc(fields=["coca_embedding"])
    assert es_doc == {
        "coca_embedding_exists": True,
        "coca_embedding_vector": [float(p) for p in image_logo.coca_embedding_vector],
        "coca_embedding_author": "user@example.com",
    }
    es_doc = image_logo.to_doc(fields=["thumbnail"])
    assert es_doc == {
        "thumbnail": "images/test-logo/thumbnail.png",
    }
    es_doc = image_logo.to_doc(fields=["id", "latents"])
    assert es_doc == {
        "id": "test-logo",
        "latent_example_latent_file": 'images/test-logo/latent_example_latent.txt',
        "latent_example_mask_file": 'images/test-logo/latent_example_mask.png',
    }
    es_doc = image_logo.to_doc(fields=["id", "attributes"])
    assert es_doc == {
        "id": "test-logo",
        "attr_name_text": "my name",
        "attr_noidx_approved_boolean": True,
        "attr_date_date": "2000-01-01T00:00:00Z",
        "attr_some_number_double": 2,
        "attr_numbers_double": [1, 2, 3],
    }
