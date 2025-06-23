import logging

from backend.dataroom.choices import DuplicateState

logger = logging.getLogger('task_runner')


def get_images_marked_as_duplicates(sources=None):
    from backend.dataroom.models.os_image import OSImage

    if not sources:
        from django.conf import settings

        sources = settings.DUPLICATE_DELETE_TASK_INCLUDED_SOURCES

    search = (
        OSImage.objects.search(
            sort="_doc",
            fields=["id", "duplicate_state"],
        )
        .filter(
            "bool",
            must=[
                {"terms": {"source": sources}},
                {"term": {"duplicate_state": DuplicateState.DUPLICATE.value}},
            ],
        )
        .extra(size=500)
    )
    results = search.execute()
    return [hit.meta.id for hit in results]


def image_delete_duplicates(image_id):
    from backend.dataroom.models.os_image import OSImage

    image = OSImage.objects.get(image_id, fields=['id', 'image', 'thumbnail', 'latents'])
    image.delete_permanently()


def get_images_marked_for_deletion():
    from backend.dataroom.models.os_image import OSImage

    search = (
        OSImage.all_objects.search(
            sort="_doc",
            fields=["id"],
        )
        .filter(
            "bool",
            must=[
                {"term": {"is_deleted": True}},
            ],
        )
        .extra(size=500)
    )
    results = search.execute()
    return [hit.meta.id for hit in results]


def image_delete_marked_for_deletion(image_id):
    from backend.dataroom.models.os_image import OSImage

    image = OSImage.all_objects.get(image_id, fields=['id', 'image', 'thumbnail', 'latents', 'is_deleted'])
    if image.is_deleted:
        image.delete_permanently()
