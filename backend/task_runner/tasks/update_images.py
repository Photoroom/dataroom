import logging

logger = logging.getLogger('task_runner')


def get_images_without_thumbnail():
    from backend.dataroom.models.os_image import OSImage

    search = (
        OSImage.objects.search(sort="_doc", fields=["id", "image", "thumbnail", "date_updated"])
        .filter(
            "bool",
            must_not=[
                {"exists": {"field": "thumbnail"}},
                {"term": {"thumbnail_error": True}},  # skip previously failed thumbnails
            ],
        )
        .extra(size=500)
    )
    results = search.execute()
    return OSImage.list_from_hits(results)


def image_update_thumbnail(image):
    image.update_thumbnail()


def get_images_without_embedding():
    from backend.dataroom.models.os_image import OSImage

    search = (
        OSImage.objects.search(sort="_doc", fields=["id", "image", "coca_embedding", "date_updated"])
        .filter(
            "term",
            coca_embedding_exists=False,
        )
        .extra(size=500)
    )
    results = search.execute()
    return OSImage.list_from_hits(results)


def image_update_coca_embedding(image):
    image.update_coca_embedding()


def get_images_without_duplicate_state(exclude_sources=None):
    from backend.dataroom.models.os_image import OSImage

    if not exclude_sources:
        from django.conf import settings

        exclude_sources = settings.DUPLICATE_FINDER_EXCLUDED_SOURCES

    search = (
        OSImage.objects.search(
            sort="_doc",
            fields=["id", "duplicate_state", "coca_embedding", "width", "height"],
        )
        .filter(
            "bool",
            must_not=[
                {"exists": {"field": "duplicate_state"}},
                {"terms": {"source": exclude_sources}},
            ],
            must=[
                {"term": {"coca_embedding_exists": True}},
                {"term": {"is_deleted": False}},
            ],
        )
        .extra(size=500)
    )
    results = search.execute()
    return [hit.meta.id for hit in results]


def image_mark_duplicates(image_id):
    from backend.dataroom.models.os_image import OSImage

    OSImage.mark_duplicates(image_id=image_id)
