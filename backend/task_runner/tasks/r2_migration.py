import contextlib

import requests

from backend.task_runner.tasks.utils import TaskResult


def r2_migration_get_all_files(search_after=None):
    from backend.dataroom.models.os_image import OSImage

    fields = ["id", "image", "thumbnail", "latents"]
    search = OSImage.all_objects.search(search_after=search_after, fields=fields).extra(size=200)

    response = search.execute()

    if len(response.hits) > 0:
        last_hit = response.hits[-1]
        search_after = last_hit.meta.sort
    else:
        # no more items
        return []

    file_urls = []
    for image in OSImage.list_from_hits(response.hits):
        if image.image_direct_url:
            file_urls.append(image.image_direct_url)
        if image.thumbnail_direct_url:
            file_urls.append(image.thumbnail_direct_url)
        for latent in image.latents.latents.values():
            if latent.file_direct_url:
                file_urls.append(latent.file_direct_url)

    return TaskResult(
        result=file_urls,
        next_kwargs={'search_after': search_after},
    )


def r2_migration_fetch_files(file_url):
    """
    Fetch from R2 to trigger a sip-by-sip migration of the file.
    """
    with contextlib.suppress(Exception):
        requests.get(file_url, stream=True, timeout=0.0001)
