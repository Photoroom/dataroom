import uuid
from mimetypes import guess_extension

import httpx
from django.core.files.base import ContentFile


def download_image_from_url(image_url):
    try:
        response = httpx.get(image_url)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise e
    else:
        content_type = response.headers.get('Content-Type')
        extension = guess_extension(content_type) or ''
        return ContentFile(response.content, name=f'{uuid.uuid4().hex}{extension}')
