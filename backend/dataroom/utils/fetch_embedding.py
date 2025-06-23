import mimetypes
from io import BytesIO

import httpx
from ddtrace import tracer
from django.conf import settings
from PIL import Image


@tracer.wrap()
def fetch_coca_embedding(pil_image: Image, image_name):
    if not settings.FETCH_EMBEDDING_FOR_IMAGE_API_URL:
        return None

    content_type, encoding = mimetypes.guess_type(image_name)

    # resize the image to make the network call faster
    # the endpoint will resize to 224 anyway
    pil_image.resize((224, 224), Image.Resampling.LANCZOS)

    with BytesIO() as temp_thumb:
        pil_image.save(temp_thumb, pil_image.format)
        temp_thumb.seek(0)

        files = {
            'imageFile': (image_name, temp_thumb, content_type),
        }
        try:
            with httpx.Client() as client:
                headers = {}
                if settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY:
                    k = settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY
                    headers[k] = settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_VALUE
                response = client.request(
                    timeout=30,
                    method="post",
                    url=settings.FETCH_EMBEDDING_FOR_IMAGE_API_URL,
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise e
        else:
            if response.content:
                return response.json()['imageEmbedding']
            else:
                raise ValueError("No content in response")


@tracer.wrap()
async def fetch_coca_embedding_async(pil_image: Image, image_name):
    if not settings.FETCH_EMBEDDING_FOR_IMAGE_API_URL:
        return None

    content_type, encoding = mimetypes.guess_type(image_name)

    # resize the image to make the network call faster
    # the endpoint will resize to 224 anyway
    pil_image.resize((224, 224), Image.Resampling.LANCZOS)

    with BytesIO() as temp_thumb:
        pil_image.save(temp_thumb, pil_image.format)
        temp_thumb.seek(0)

        files = {
            'imageFile': (image_name, temp_thumb, content_type),
        }
        try:
            async with httpx.AsyncClient() as client:
                headers = {}
                if settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY:
                    k = settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY
                    headers[k] = settings.FETCH_EMBEDDING_FOR_IMAGE_HEADER_VALUE
                response = await client.request(
                    timeout=30,
                    method="post",
                    url=settings.FETCH_EMBEDDING_FOR_IMAGE_API_URL,
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise e
        else:
            if response.content:
                return response.json()['imageEmbedding']
            else:
                raise ValueError("No content in response")


@tracer.wrap()
def fetch_text_for_image(pil_image: Image, image_name):
    if not settings.FETCH_TEXT_FOR_IMAGE_API_URL:
        return None

    content_type, encoding = mimetypes.guess_type(image_name)

    # resize the image to make the network call faster
    # the endpoint will resize to 224 anyway
    pil_image.resize((224, 224), Image.Resampling.LANCZOS)

    with BytesIO() as temp_thumb:
        pil_image.save(temp_thumb, pil_image.format)
        temp_thumb.seek(0)

        files = {
            'imageFile': (image_name, temp_thumb, content_type),
        }
        try:
            with httpx.Client() as client:
                headers = {}
                if settings.FETCH_TEXT_FOR_IMAGE_HEADER_KEY:
                    k = settings.FETCH_TEXT_FOR_IMAGE_HEADER_KEY
                    headers[k] = settings.FETCH_TEXT_FOR_IMAGE_HEADER_VALUE
                response = client.request(
                    timeout=30,
                    method="post",
                    url=settings.FETCH_TEXT_FOR_IMAGE_API_URL,
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise e
        else:
            if response.content:
                return response.json()['caption']
            else:
                raise ValueError("No content in response")


@tracer.wrap()
def fetch_coca_embedding_for_text(text):
    if not settings.FETCH_EMBEDDING_FOR_TEXT_API_URL:
        return None

    try:
        with httpx.Client() as client:
            headers = {}
            if settings.FETCH_EMBEDDING_FOR_TEXT_HEADER_KEY:
                k = settings.FETCH_EMBEDDING_FOR_TEXT_HEADER_KEY
                headers[k] = settings.FETCH_EMBEDDING_FOR_TEXT_HEADER_VALUE
            response = client.request(
                timeout=30,
                method="post",
                url=settings.FETCH_EMBEDDING_FOR_TEXT_API_URL,
                files={
                    "caption": (None, text),
                },
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise e
    else:
        if response.content:
            return response.json()['textEmbedding']
        else:
            raise ValueError("No content in response")
