import asyncio
import functools
import inspect
import logging
import os
import queue
from io import BytesIO
from typing import Any, AsyncIterable
from urllib.parse import urljoin

import httpx

from ._compat import FlatAPI
from .models import (  # noqa: F401 - re-exported for backward compatibility
    ClientDuplicateState,
    DataRoomError,
    DataRoomFile,
    ImageCreate,
    ImageUpdate,
    LatentType,
    arg_deprecation_msg,
)
from .resources import install_resources
from .runner import AsyncRunner

logger = logging.getLogger(__name__)


@install_resources
class DataRoomClient(FlatAPI):
    """
    The official client of the DataRoom API. See notebooks for usage examples.

    The API is exposed twice: as resource namespaces (``client.images.list()``,
    ``client.datasets.create()``, ...), which own the implementations, and as
    the original flat methods (``get_images()``, ``create_dataset()``, ...),
    which are thin delegates kept for backward compatibility (``FlatAPI``).
    """

    def __init__(self, api_key=None, api_url=None, timeout=120) -> None:
        """
        @param api_key: API key for DataRoom API
        @param api_url: URL of the DataRoom backend API
        @param timeout: Timeout for the API requests
        """
        self.api_key = api_key or os.environ.get("DATAROOM_API_KEY")
        self.api_url = (
            api_url
            or os.environ.get("DATAROOM_API_URL")
        )
        if not self.api_url:
            raise DataRoomError("DataRoom api_url is not set")
        self.client = httpx.AsyncClient()
        self.timeout = timeout

    def _make_resource(self, resource_cls):
        """install_resources hook: bind a namespace to this client."""
        return resource_cls(self)

    # -------------------- Transport --------------------

    async def _make_request(
        self, url, params=None, method="GET", json=None, files=None, headers=None,
    ) -> dict:
        absolute_url = urljoin(self.api_url, url)
        if headers is None:
            headers = {}
        headers.update({
            "Authorization": f"Token {self.api_key}",
        })
        try:
            response = await self.client.request(
                method=method,
                url=absolute_url,
                params=params,
                json=json,
                files=files,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            response = None
            if hasattr(e, "response"):
                response = e.response
            raise DataRoomError(e, response=response) from e
        else:
            if response.content:
                return response.json()

    async def _make_paginated_request(
        self, url, limit=1000, params=None, method="GET", json=None, headers=None,
    ) -> list[dict]:
        items = []
        next_url = url
        first_request = True
        while next_url:
            # Only pass params on the first request; subsequent requests use the server's next URL
            # which already contains the necessary parameters
            response = await self._make_request(
                next_url, params=params if first_request else None, method=method, json=json, headers=headers,
            )
            first_request = False
            if "results" not in response:
                raise NotImplementedError(f'No "results" in response to {url}')
            if "next" not in response:
                raise NotImplementedError(f'No "next" in response to {url}')
            next_url = response["next"]
            items += response["results"]
            if limit is not None and len(items) >= limit:
                break

        if limit is not None:
            return items[:limit]
        return items

    async def _make_paginated_request_iter(
        self, url, limit=1000, params=None, method="GET", json=None, headers=None,
    ) -> AsyncIterable[dict]:
        next_url = url
        returned_items = 0
        first_request = True
        while next_url:
            # Only pass params on the first request; subsequent requests use the server's next URL
            # which already contains the necessary parameters
            response = await self._make_request(
                next_url, params=params if first_request else None, method=method, json=json, headers=headers,
            )
            first_request = False
            if "results" not in response:
                raise NotImplementedError(f'No "results" in response to {url}')
            if "next" not in response:
                raise NotImplementedError(f'No "next" in response to {url}')
            next_url = response["next"]
            for item in response["results"]:
                yield item
                returned_items += 1
                if limit is not None and returned_items >= limit:
                    break
            if limit is not None and returned_items >= limit:
                break

    # -------------------- Utils --------------------

    @classmethod
    async def download_image_from_url(cls, image_url: str) -> DataRoomFile:
        """
        Downloads an image from a URL and returns it as a DataRoomFile.

        @param image_url: The URL of the image to download.
        @return: A DataRoomFile instance containing the downloaded image.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
                response.raise_for_status()
        except httpx.HTTPError as e:
            response = None
            if hasattr(e, "response"):
                response = e.response
            raise DataRoomError(e, response=response) from e
        else:
            content_type = response.headers.get("Content-Type")
            return DataRoomFile(
                bytes_io=BytesIO(response.content),
                content_type=content_type,
            )


def _syncify(attr):
    """Make an async-client callable blocking: awaitables run to completion on
    the shared background loop, async iterables become blocking iterators."""

    @functools.wraps(attr)
    def sync_wrapper(*args, **kwargs):
        result = attr(*args, **kwargs)
        if inspect.isawaitable(result):
            return AsyncRunner.run(result)
        # If the result is an async generator or async iterable, wrap it into a blocking iterator
        if inspect.isasyncgen(result) or hasattr(result, "__aiter__"):
            return _wrap_async_iterable(result)
        return result

    return sync_wrapper


def _wrap_async_iterable(async_iterable):
    """
    Convert an AsyncIterable into a synchronous, blocking Python iterator.
    Items are streamed via a thread-safe queue from a background task.
    """
    sentinel = object()
    q: queue.Queue = queue.Queue(maxsize=10)
    stop_flag = {"stop": False}

    async def aclose_safe(ait):
        aclose = getattr(ait, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    async def producer():
        try:
            async for item in async_iterable:
                if stop_flag["stop"]:
                    await aclose_safe(async_iterable)
                    break
                while True:
                    try:
                        q.put_nowait(item)
                        break
                    except queue.Full:
                        if stop_flag["stop"]:
                            await aclose_safe(async_iterable)
                            return
                        await asyncio.sleep(0.01)
        except Exception as e:
            # pass exception to consumer then terminate
            try:
                q.put_nowait(e)
            except queue.Full:
                # If full, block briefly in thread to ensure delivery
                q.put(e)
        finally:
            # Signal completion
            try:
                q.put_nowait(sentinel)
            except queue.Full:
                q.put(sentinel)

    # Start the producer without blocking
    AsyncRunner.submit(producer())

    def iterator():
        try:
            while True:
                item = q.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            # Signal producer to stop; it will close the async generator promptly
            stop_flag["stop"] = True

    return iterator()


class _SyncResource:
    """A resource namespace whose methods block: wraps a namespace bound to the
    async client and runs every call through ``_syncify``."""

    def __init__(self, resource):
        self._resource = resource

    def __getattr__(self, name):
        attr = getattr(self._resource, name)
        if not callable(attr):
            return attr
        return _syncify(attr)

    def __dir__(self):
        """Attribute list for introspection and autocompletion in tools like IPython."""
        return sorted(set(object.__dir__(self)) | set(dir(self._resource)))


@install_resources
class DataRoomClientSync:
    """
    The official client of the DataRoom API using synchronous method and requests.
    """

    def __init__(self, api_key=None, api_url=None, timeout=120) -> None:
        """
        @param api_key: API key for DataRoom API.
        @param api_url: URL of the DataRoom backend API
        @param timeout: Timeout for the requests to the DataRoom backend API
        """
        self.api_key = api_key or os.environ.get("DATAROOM_API_KEY")
        self.api_url = (
            api_url
            or os.environ.get("DATAROOM_API_URL")
        )
        if not self.api_url:
            raise DataRoomError("DataRoom api_url is not set")
        self._async_client = DataRoomClient(api_key=self.api_key, api_url=self.api_url, timeout=timeout)

    def _make_resource(self, resource_cls):
        """install_resources hook: namespaces block on the sync client."""
        return _SyncResource(resource_cls(self._async_client))

    def __getattr__(self, name) -> Any:
        # Dynamically create sync methods for all methods of the async client.
        attr = getattr(self._async_client, name)

        if not callable(attr):
            return attr

        return _syncify(attr)

    def __dir__(self) -> list[str]:
        """
        Provide a list of attributes for introspection and autocompletion in tools like IPython.
        """
        # include all attributes from the async client and the sync client.
        return sorted(list(set(super().__dir__()) | set(dir(self._async_client))))

    @classmethod
    def download_image_from_url(cls, *args, **kwargs) -> DataRoomFile:
        """
        Downloads an image from a URL and returns it as a DataRoomFile.

        @param image_url: The URL of the image to download.
        @return: A DataRoomFile instance containing the downloaded image.
        """
        # Class methods are not covered by the automatic wrapping of async methods in __getattr__.
        return AsyncRunner.run(DataRoomClient.download_image_from_url(*args, **kwargs))
