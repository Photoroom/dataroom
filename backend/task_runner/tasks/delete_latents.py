import logging

logger = logging.getLogger('task_runner')


def get_disabled_latent_types():
    from backend.dataroom.models.latents import LatentType

    return list(LatentType.objects.filter(is_enabled=False).values_list('name', flat=True))


def get_images_with_disabled_latents(latent_types):
    from backend.dataroom.models.os_image import OSImage, OSLatent

    assert isinstance(latent_types, list)
    if not latent_types:
        return []

    OSImage.objects.refresh()

    search = (
        OSImage.all_objects.search(
            sort="_doc",
            fields=["id"],
        )
        .filter(
            "bool",
            should=[
                {"exists": {"field": OSLatent(latent_type=latent_type).os_name_file}} for latent_type in latent_types
            ],
            minimum_should_match=1,
            _expand__to_dot=False,
        )
        .extra(size=500)
    )
    results = search.execute()
    return [hit.meta.id for hit in results]


def image_delete_latents(image_id, latent_types, refresh=False):
    from backend.dataroom.models.os_image import OSImage

    assert isinstance(latent_types, list)
    if not latent_types:
        return

    image = OSImage.all_objects.get(image_id, fields=['id', 'latents'])
    for latent_type in latent_types:
        if latent_type in image.latents.latents:
            image.remove_latent(latent_type, refresh=refresh)
