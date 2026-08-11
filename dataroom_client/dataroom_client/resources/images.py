"""``client.images`` - every image endpoint, implemented here.

The flat client methods (``get_images``, ``create_image``, ...) are thin
delegates to this class - see ``_compat.py``.
"""

from __future__ import annotations

import json as json_module
import logging
from datetime import datetime
from typing import AsyncIterable

from ..models import (
    ClientDuplicateState,
    DataRoomError,
    DataRoomFile,
    ImageCreate,
    ImageUpdate,
    LatentType,
    arg_deprecation_msg,
)
from .base import Resource, dict_filter_none, get_attributes_filter, validate_vector

logger = logging.getLogger(__name__)


class ImagesResource(Resource):
    """``client.images``.

    Upload images one by one (``create``) or in bulk (``create_many``), filter
    the collection by size/source/tags/attributes/dates (``list``, ``iter``,
    ``count``), and search by visual similarity to an image, a vector or a
    text prompt (``similar``).
    """

    async def list(
        self,
        limit: int | None = 1000,
        page_size: int = None,
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
        cache_ttl: int = None,
        partitions_count: int = None,
        partition: int = None,
        # filters
        short_edge: int = None,
        short_edge__gt: int = None,
        short_edge__gte: int = None,
        short_edge__lt: int = None,
        short_edge__lte: int = None,
        pixel_count: int = None,
        pixel_count__gt: int = None,
        pixel_count__gte: int = None,
        pixel_count__lt: int = None,
        pixel_count__lte: int = None,
        aspect_ratio_fraction: str = None,
        aspect_ratio: float = None,
        aspect_ratio__gt: float = None,
        aspect_ratio__gte: float = None,
        aspect_ratio__lt: float = None,
        aspect_ratio__lte: float = None,
        source: str = None,
        sources: list[str] = None,
        sources__ne: list[str] = None,
        attributes: dict = None,
        has_attributes: list = None,
        lacks_attributes: list = None,
        has_latents: list[str] = None,
        lacks_latents: list[str] = None,
        has_masks: list[str] = None,
        lacks_masks: list[str] = None,
        tags: list = None,
        tags__ne: list = None,
        tags__all: list = None,
        tags__ne_all: list = None,
        tags__empty: bool = None,
        coca_embedding__empty: bool = None,
        duplicate_state: ClientDuplicateState = None,
        date_created__gt: datetime = None,
        date_created__gte: datetime = None,
        date_created__lt: datetime = None,
        date_created__lte: datetime = None,
        date_updated__gt: datetime = None,
        date_updated__gte: datetime = None,
        date_updated__lt: datetime = None,
        date_updated__lte: datetime = None,
        datasets: list = None,
        datasets__ne: list = None,
        datasets__all: list = None,
        datasets__ne_all: list = None,
        datasets__prefix: list = None,
        datasets__empty: bool = None,
        query: str = None,
        group_ids: list[str] = None,
        roles: list[str] = None,
        group_type: str = None,
    ) -> list[dict]:
        """
        Retrieves a paginated list of images, with optional filtering and field selection.

        @param limit: The maximum number of images to return.
        @param page_size: The number of images to return per page.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for each image.
        @param cache_ttl: The time-to-live for caching of this request in seconds.
        @param partitions_count: The total number of partitions to divide the data into.
        @param partition: The specific partition number to retrieve.
        @param ...: Various filter parameters to narrow down the image search.
        @return: A list of image dictionaries.
        """
        headers = {}
        if cache_ttl:
            headers["Cache-Control"] = f"max-age={cache_ttl}"

        if source is not None:
            sources = [source]
            logger.warning(arg_deprecation_msg('source', 'Pass a list instead: sources=["..."].'))

        return await self._c._make_paginated_request(
            url="images/",
            limit=limit,
            params=dict_filter_none(
                {
                    "fields": ",".join(fields) if fields else None,
                    "include_fields": ",".join(include_fields) if include_fields else None,
                    "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
                    "all_fields": all_fields if all_fields else None,
                    "return_latents": ",".join(return_latents) if return_latents else None,
                    "page_size": page_size,
                    "partitions_count": partitions_count,
                    "partition": partition,
                    # filters
                    "short_edge": short_edge,
                    "short_edge__gt": short_edge__gt,
                    "short_edge__gte": short_edge__gte,
                    "short_edge__lt": short_edge__lt,
                    "short_edge__lte": short_edge__lte,
                    "pixel_count": pixel_count,
                    "pixel_count__gt": pixel_count__gt,
                    "pixel_count__gte": pixel_count__gte,
                    "pixel_count__lt": pixel_count__lt,
                    "pixel_count__lte": pixel_count__lte,
                    "aspect_ratio_fraction": aspect_ratio_fraction,
                    "aspect_ratio": aspect_ratio,
                    "aspect_ratio__gt": aspect_ratio__gt,
                    "aspect_ratio__gte": aspect_ratio__gte,
                    "aspect_ratio__lt": aspect_ratio__lt,
                    "aspect_ratio__lte": aspect_ratio__lte,
                    "sources": ",".join(sources) if sources else None,
                    "sources__ne": ",".join(sources__ne) if sources__ne else None,
                    "attributes": get_attributes_filter(attributes),
                    "has_attributes": ",".join(has_attributes) if has_attributes else None,
                    "lacks_attributes": ",".join(lacks_attributes) if lacks_attributes else None,
                    "has_latents": ",".join(has_latents) if has_latents else None,
                    "lacks_latents": ",".join(lacks_latents) if lacks_latents else None,
                    "has_masks": ",".join(has_masks) if has_masks else None,
                    "lacks_masks": ",".join(lacks_masks) if lacks_masks else None,
                    "tags": ",".join(tags) if tags else None,
                    "tags__ne": ",".join(tags__ne) if tags__ne else None,
                    "tags__all": ",".join(tags__all) if tags__all else None,
                    "tags__ne_all": ",".join(tags__ne_all) if tags__ne_all else None,
                    "tags__empty": tags__empty,
                    "coca_embedding__empty": coca_embedding__empty,
                    "duplicate_state": duplicate_state.value if duplicate_state else None,
                    "date_created__gt": date_created__gt.isoformat() if date_created__gt else None,
                    "date_created__gte": date_created__gte.isoformat() if date_created__gte else None,
                    "date_created__lt": date_created__lt.isoformat() if date_created__lt else None,
                    "date_created__lte": date_created__lte.isoformat() if date_created__lte else None,
                    "date_updated__gt": date_updated__gt.isoformat() if date_updated__gt else None,
                    "date_updated__gte": date_updated__gte.isoformat() if date_updated__gte else None,
                    "date_updated__lt": date_updated__lt.isoformat() if date_updated__lt else None,
                    "date_updated__lte": date_updated__lte.isoformat() if date_updated__lte else None,
                    "datasets": ",".join(datasets) if datasets else None,
                    "datasets__ne": ",".join(datasets__ne) if datasets__ne else None,
                    "datasets__all": ",".join(datasets__all) if datasets__all else None,
                    "datasets__ne_all": ",".join(datasets__ne_all) if datasets__ne_all else None,
                    "datasets__prefix": ",".join(datasets__prefix) if datasets__prefix else None,
                    "datasets__empty": datasets__empty,
                    "query": query,
                    "group_ids": ",".join(group_ids) if group_ids else None,
                    "roles": ",".join(roles) if roles else None,
                    "group_type": group_type,
                }
            ),
            headers=headers,
        )

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def iter(
        self,
        limit: int | None = 1000,
        page_size: int = None,
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
        cache_ttl: int = None,
        partitions_count: int = None,
        partition: int = None,
        # filters
        short_edge: int = None,
        short_edge__gt: int = None,
        short_edge__gte: int = None,
        short_edge__lt: int = None,
        short_edge__lte: int = None,
        pixel_count: int = None,
        pixel_count__gt: int = None,
        pixel_count__gte: int = None,
        pixel_count__lt: int = None,
        pixel_count__lte: int = None,
        aspect_ratio_fraction: str = None,
        aspect_ratio: float = None,
        aspect_ratio__gt: float = None,
        aspect_ratio__gte: float = None,
        aspect_ratio__lt: float = None,
        aspect_ratio__lte: float = None,
        source: str = None,
        sources: list[str] = None,
        sources__ne: list[str] = None,
        attributes: dict = None,
        has_attributes: list = None,
        lacks_attributes: list = None,
        has_latents: list[str] = None,
        lacks_latents: list[str] = None,
        has_masks: list[str] = None,
        lacks_masks: list[str] = None,
        tags: list = None,
        tags__ne: list = None,
        tags__all: list = None,
        tags__ne_all: list = None,
        tags__empty: bool = None,
        coca_embedding__empty: bool = None,
        duplicate_state: ClientDuplicateState = None,
        date_created__gt: datetime = None,
        date_created__gte: datetime = None,
        date_created__lt: datetime = None,
        date_created__lte: datetime = None,
        date_updated__gt: datetime = None,
        date_updated__gte: datetime = None,
        date_updated__lt: datetime = None,
        date_updated__lte: datetime = None,
        datasets: list = None,
        datasets__ne: list = None,
        datasets__all: list = None,
        datasets__ne_all: list = None,
        datasets__prefix: list = None,
        datasets__empty: bool = None,
        query: str = None,
    ) -> AsyncIterable[dict]:
        """
        Retrieves an iterator of images, with optional filtering and field selection.

        This method is useful for processing a large number of images without loading them all into memory at once.

        @param limit: The maximum number of images to return.
        @param page_size: The number of images to return per page.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for each image.
        @param cache_ttl: The time-to-live for caching of this request in seconds.
        @param partitions_count: The total number of partitions to divide the data into.
        @param partition: The specific partition number to retrieve.
        @param ...: Various filter parameters to narrow down the image search.
        @yields: An image dictionary.
        """
        headers = {}
        if cache_ttl:
            headers["Cache-Control"] = f"max-age={cache_ttl}"

        if source is not None:
            sources = [source]
            logger.warning(arg_deprecation_msg('source', 'Pass a list instead: sources=["..."].'))

        async for item in self._c._make_paginated_request_iter(
            url="images/",
            limit=limit,
            params=dict_filter_none(
                {
                    "fields": ",".join(fields) if fields else None,
                    "include_fields": ",".join(include_fields) if include_fields else None,
                    "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
                    "all_fields": all_fields if all_fields else None,
                    "return_latents": ",".join(return_latents) if return_latents else None,
                    "page_size": page_size,
                    "partitions_count": partitions_count,
                    "partition": partition,
                    # filters
                    "short_edge": short_edge,
                    "short_edge__gt": short_edge__gt,
                    "short_edge__gte": short_edge__gte,
                    "short_edge__lt": short_edge__lt,
                    "short_edge__lte": short_edge__lte,
                    "pixel_count": pixel_count,
                    "pixel_count__gt": pixel_count__gt,
                    "pixel_count__gte": pixel_count__gte,
                    "pixel_count__lt": pixel_count__lt,
                    "pixel_count__lte": pixel_count__lte,
                    "aspect_ratio_fraction": aspect_ratio_fraction,
                    "aspect_ratio": aspect_ratio,
                    "aspect_ratio__gt": aspect_ratio__gt,
                    "aspect_ratio__gte": aspect_ratio__gte,
                    "aspect_ratio__lt": aspect_ratio__lt,
                    "aspect_ratio__lte": aspect_ratio__lte,
                    "sources": ",".join(sources) if sources else None,
                    "sources__ne": ",".join(sources__ne) if sources__ne else None,
                    "attributes": get_attributes_filter(attributes),
                    "has_attributes": ",".join(has_attributes) if has_attributes else None,
                    "lacks_attributes": ",".join(lacks_attributes) if lacks_attributes else None,
                    "has_latents": ",".join(has_latents) if has_latents else None,
                    "lacks_latents": ",".join(lacks_latents) if lacks_latents else None,
                    "has_masks": ",".join(has_masks) if has_masks else None,
                    "lacks_masks": ",".join(lacks_masks) if lacks_masks else None,
                    "tags": ",".join(tags) if tags else None,
                    "tags__ne": ",".join(tags__ne) if tags__ne else None,
                    "tags__all": ",".join(tags__all) if tags__all else None,
                    "tags__ne_all": ",".join(tags__ne_all) if tags__ne_all else None,
                    "tags__empty": tags__empty,
                    "coca_embedding__empty": coca_embedding__empty,
                    "duplicate_state": duplicate_state.value if duplicate_state else None,
                    "date_created__gt": date_created__gt.isoformat() if date_created__gt else None,
                    "date_created__gte": date_created__gte.isoformat() if date_created__gte else None,
                    "date_created__lt": date_created__lt.isoformat() if date_created__lt else None,
                    "date_created__lte": date_created__lte.isoformat() if date_created__lte else None,
                    "date_updated__gt": date_updated__gt.isoformat() if date_updated__gt else None,
                    "date_updated__gte": date_updated__gte.isoformat() if date_updated__gte else None,
                    "date_updated__lt": date_updated__lt.isoformat() if date_updated__lt else None,
                    "date_updated__lte": date_updated__lte.isoformat() if date_updated__lte else None,
                    "datasets": ",".join(datasets) if datasets else None,
                    "datasets__ne": ",".join(datasets__ne) if datasets__ne else None,
                    "datasets__all": ",".join(datasets__all) if datasets__all else None,
                    "datasets__ne_all": ",".join(datasets__ne_all) if datasets__ne_all else None,
                    "datasets__prefix": ",".join(datasets__prefix) if datasets__prefix else None,
                    "datasets__empty": datasets__empty,
                    "query": query,
                }
            ),
            headers=headers,
        ):
            yield item

    async def random(
        self,
        limit: int | None = 1000,
        page_size: int = None,
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
        cache_ttl: int = None,
        prefix_length: int = None,
        num_prefixes: int = None,
        # filters
        short_edge: int = None,
        short_edge__gt: int = None,
        short_edge__gte: int = None,
        short_edge__lt: int = None,
        short_edge__lte: int = None,
        pixel_count: int = None,
        pixel_count__gt: int = None,
        pixel_count__gte: int = None,
        pixel_count__lt: int = None,
        pixel_count__lte: int = None,
        aspect_ratio_fraction: str = None,
        aspect_ratio: float = None,
        aspect_ratio__gt: float = None,
        aspect_ratio__gte: float = None,
        aspect_ratio__lt: float = None,
        aspect_ratio__lte: float = None,
        source: str = None,
        sources: list[str] = None,
        sources__ne: list[str] = None,
        attributes: dict = None,
        has_attributes: list = None,
        lacks_attributes: list = None,
        has_latents: list[str] = None,
        lacks_latents: list[str] = None,
        has_masks: list[str] = None,
        lacks_masks: list[str] = None,
        tags: list = None,
        tags__ne: list = None,
        tags__all: list = None,
        tags__ne_all: list = None,
        tags__empty: bool = None,
        coca_embedding__empty: bool = None,
        duplicate_state: ClientDuplicateState = None,
        date_created__gt: datetime = None,
        date_created__gte: datetime = None,
        date_created__lt: datetime = None,
        date_created__lte: datetime = None,
        date_updated__gt: datetime = None,
        date_updated__gte: datetime = None,
        date_updated__lt: datetime = None,
        date_updated__lte: datetime = None,
        datasets: list = None,
        datasets__ne: list = None,
        datasets__all: list = None,
        datasets__ne_all: list = None,
        datasets__prefix: list = None,
        datasets__empty: bool = None,
        query: str = None,
    ) -> list[dict]:
        """
        Get a list of random images.

        Random sampling works by filtering image_hash by a number of random hex prefixes. Use prefix_length and
        num_prefixes to adjust the randomness factor. In general, a smaller prefix_length will give you more samples,
        but less random and a higher num_prefixes will give you more samples, but slow down the query. The default
        values are prefix_length=5 and num_prefixes=100.

        @param limit: The maximum number of images to return.
        @param page_size: The number of images to return per page.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for each image.
        @param cache_ttl: The time-to-live for caching of this request in seconds.
        @param partitions_count: The total number of partitions to divide the data into.
        @param partition: The specific partition number to retrieve.
        @param ...: Various filter parameters to narrow down the image search.
        @return: A list of image dictionaries.
        """
        headers = {}
        if cache_ttl:
            headers["Cache-Control"] = f"max-age={cache_ttl}"

        if source is not None:
            sources = [source]
            logger.warning(arg_deprecation_msg('source', 'Pass a list instead: sources=["..."].'))

        return await self._c._make_paginated_request(
            url="images/random/",
            limit=limit,
            params=dict_filter_none(
                {
                    "fields": ",".join(fields) if fields else None,
                    "include_fields": ",".join(include_fields) if include_fields else None,
                    "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
                    "all_fields": all_fields if all_fields else None,
                    "return_latents": ",".join(return_latents) if return_latents else None,
                    "page_size": page_size,
                    "prefix_length": prefix_length,
                    "num_prefixes": num_prefixes,
                    # filters
                    "short_edge": short_edge,
                    "short_edge__gt": short_edge__gt,
                    "short_edge__gte": short_edge__gte,
                    "short_edge__lt": short_edge__lt,
                    "short_edge__lte": short_edge__lte,
                    "pixel_count": pixel_count,
                    "pixel_count__gt": pixel_count__gt,
                    "pixel_count__gte": pixel_count__gte,
                    "pixel_count__lt": pixel_count__lt,
                    "pixel_count__lte": pixel_count__lte,
                    "aspect_ratio_fraction": aspect_ratio_fraction,
                    "aspect_ratio": aspect_ratio,
                    "aspect_ratio__gt": aspect_ratio__gt,
                    "aspect_ratio__gte": aspect_ratio__gte,
                    "aspect_ratio__lt": aspect_ratio__lt,
                    "aspect_ratio__lte": aspect_ratio__lte,
                    "sources": ",".join(sources) if sources else None,
                    "sources__ne": ",".join(sources__ne) if sources__ne else None,
                    "attributes": get_attributes_filter(attributes),
                    "has_attributes": ",".join(has_attributes) if has_attributes else None,
                    "lacks_attributes": ",".join(lacks_attributes) if lacks_attributes else None,
                    "has_latents": ",".join(has_latents) if has_latents else None,
                    "lacks_latents": ",".join(lacks_latents) if lacks_latents else None,
                    "has_masks": ",".join(has_masks) if has_masks else None,
                    "lacks_masks": ",".join(lacks_masks) if lacks_masks else None,
                    "tags": ",".join(tags) if tags else None,
                    "tags__ne": ",".join(tags__ne) if tags__ne else None,
                    "tags__all": ",".join(tags__all) if tags__all else None,
                    "tags__ne_all": ",".join(tags__ne_all) if tags__ne_all else None,
                    "tags__empty": tags__empty,
                    "coca_embedding__empty": coca_embedding__empty,
                    "duplicate_state": duplicate_state.value if duplicate_state else None,
                    "date_created__gt": date_created__gt.isoformat() if date_created__gt else None,
                    "date_created__gte": date_created__gte.isoformat() if date_created__gte else None,
                    "date_created__lt": date_created__lt.isoformat() if date_created__lt else None,
                    "date_created__lte": date_created__lte.isoformat() if date_created__lte else None,
                    "date_updated__gt": date_updated__gt.isoformat() if date_updated__gt else None,
                    "date_updated__gte": date_updated__gte.isoformat() if date_updated__gte else None,
                    "date_updated__lt": date_updated__lt.isoformat() if date_updated__lt else None,
                    "date_updated__lte": date_updated__lte.isoformat() if date_updated__lte else None,
                    "datasets": ",".join(datasets) if datasets else None,
                    "datasets__ne": ",".join(datasets__ne) if datasets__ne else None,
                    "datasets__all": ",".join(datasets__all) if datasets__all else None,
                    "datasets__ne_all": ",".join(datasets__ne_all) if datasets__ne_all else None,
                    "datasets__prefix": ",".join(datasets__prefix) if datasets__prefix else None,
                    "datasets__empty": datasets__empty,
                    "query": query,
                }
            ),
            headers=headers,
        )

    async def count(
        self,
        partitions_count: int = None,
        partition: int = None,
        # filters
        short_edge: int | None = None,
        short_edge__gt: int = None,
        short_edge__gte: int = None,
        short_edge__lt: int = None,
        short_edge__lte: int = None,
        pixel_count: int | None = None,
        pixel_count__gt: int = None,
        pixel_count__gte: int = None,
        pixel_count__lt: int = None,
        pixel_count__lte: int = None,
        aspect_ratio_fraction: str = None,
        aspect_ratio: float = None,
        aspect_ratio__gt: float = None,
        aspect_ratio__gte: float = None,
        aspect_ratio__lt: float = None,
        aspect_ratio__lte: float = None,
        source: str = None,
        sources: list[str] = None,
        sources__ne: list[str] = None,
        attributes: dict = None,
        has_attributes: list = None,
        lacks_attributes: list = None,
        has_latents: list[str] = None,
        lacks_latents: list[str] = None,
        has_masks: list[str] = None,
        lacks_masks: list[str] = None,
        tags: list = None,
        tags__ne: list = None,
        tags__all: list = None,
        tags__ne_all: list = None,
        tags__empty: bool = None,
        coca_embedding__empty: bool = None,
        duplicate_state: ClientDuplicateState = None,
        date_created__gt: datetime = None,
        date_created__gte: datetime = None,
        date_created__lt: datetime = None,
        date_created__lte: datetime = None,
        date_updated__gt: datetime = None,
        date_updated__gte: datetime = None,
        date_updated__lt: datetime = None,
        date_updated__lte: datetime = None,
        datasets: list = None,
        datasets__ne: list = None,
        datasets__all: list = None,
        datasets__ne_all: list = None,
        datasets__prefix: list = None,
        datasets__empty: bool = None,
        query: str = None,
    ) -> int:
        """
        Returns the total count of images based on the provided filters.

        @param partitions_count: The total number of partitions to divide the data into.
        @param partition: The specific partition number to retrieve.
        @param ...: Various filter parameters to narrow down the image count.
        @return: The total number of images matching the filters.
        """
        if source is not None:
            sources = [source]
            logger.warning(arg_deprecation_msg('source', 'Pass a list instead: sources=["..."].'))

        response = await self._c._make_request(
            url="images/count/",
            params=dict_filter_none(
                {
                    "partitions_count": partitions_count,
                    "partition": partition,
                    # filters
                    "short_edge": short_edge,
                    "short_edge__gt": short_edge__gt,
                    "short_edge__gte": short_edge__gte,
                    "short_edge__lt": short_edge__lt,
                    "short_edge__lte": short_edge__lte,
                    "pixel_count": pixel_count,
                    "pixel_count__gt": pixel_count__gt,
                    "pixel_count__gte": pixel_count__gte,
                    "pixel_count__lt": pixel_count__lt,
                    "pixel_count__lte": pixel_count__lte,
                    "aspect_ratio_fraction": aspect_ratio_fraction,
                    "aspect_ratio": aspect_ratio,
                    "aspect_ratio__gt": aspect_ratio__gt,
                    "aspect_ratio__gte": aspect_ratio__gte,
                    "aspect_ratio__lt": aspect_ratio__lt,
                    "aspect_ratio__lte": aspect_ratio__lte,
                    "sources": ",".join(sources) if sources else None,
                    "sources__ne": ",".join(sources__ne) if sources__ne else None,
                    "attributes": get_attributes_filter(attributes),
                    "has_attributes": ",".join(has_attributes) if has_attributes else None,
                    "lacks_attributes": ",".join(lacks_attributes) if lacks_attributes else None,
                    "has_latents": ",".join(has_latents) if has_latents else None,
                    "lacks_latents": ",".join(lacks_latents) if lacks_latents else None,
                    "has_masks": ",".join(has_masks) if has_masks else None,
                    "lacks_masks": ",".join(lacks_masks) if lacks_masks else None,
                    "tags": ",".join(tags) if tags else None,
                    "tags__ne": ",".join(tags__ne) if tags__ne else None,
                    "tags__all": ",".join(tags__all) if tags__all else None,
                    "tags__ne_all": ",".join(tags__ne_all) if tags__ne_all else None,
                    "tags__empty": tags__empty,
                    "coca_embedding__empty": coca_embedding__empty,
                    "duplicate_state": duplicate_state.value if duplicate_state else None,
                    "date_created__gt": date_created__gt.isoformat() if date_created__gt else None,
                    "date_created__gte": date_created__gte.isoformat() if date_created__gte else None,
                    "date_created__lt": date_created__lt.isoformat() if date_created__lt else None,
                    "date_created__lte": date_created__lte.isoformat() if date_created__lte else None,
                    "date_updated__gt": date_updated__gt.isoformat() if date_updated__gt else None,
                    "date_updated__gte": date_updated__gte.isoformat() if date_updated__gte else None,
                    "date_updated__lt": date_updated__lt.isoformat() if date_updated__lt else None,
                    "date_updated__lte": date_updated__lte.isoformat() if date_updated__lte else None,
                    "datasets": ",".join(datasets) if datasets else None,
                    "datasets__ne": ",".join(datasets__ne) if datasets__ne else None,
                    "datasets__all": ",".join(datasets__all) if datasets__all else None,
                    "datasets__ne_all": ",".join(datasets__ne_all) if datasets__ne_all else None,
                    "datasets__prefix": ",".join(datasets__prefix) if datasets__prefix else None,
                    "datasets__empty": datasets__empty,
                    "query": query,
                }
            ),
        )
        return response["count"]

    async def get(
        self,
        image_id: str,
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
        fetch_image_bytes: bool = False,
    ) -> dict:
        """
        Retrieves a single image by its ID.

        @param image_id: The UUID of the image to retrieve.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for the image.
        @param fetch_image_bytes: whether to return the image bytes or not. Will query `image_direct_url`.
        @return: A dictionary representing the image.
        """
        response = await self._c._make_request(
            url=f"images/{image_id}/",
            params=dict_filter_none({
                "fields": ",".join(fields) if fields else None,
                "include_fields": ",".join(include_fields) if include_fields else None,
                "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
                "all_fields": all_fields if all_fields else None,
                "return_latents": ",".join(return_latents) if return_latents else None,
            }),
        )
        if fetch_image_bytes:
            assert "image_direct_url" in response
            image_bytes_response = await self._c.client.request(method="GET", url=response["image_direct_url"])
            image_bytes_response.raise_for_status()
            response["image_bytes"] = image_bytes_response.content
        return response

    async def create(
        self,
        image_id: str = None,
        source: str = None,
        image_file: DataRoomFile = None,
        image_url: str = None,
        attributes: dict = None,
        tags: list[str] = None,
        related_images: dict[str, str] | None = None,
    ) -> dict:
        """
        Creates a new image from a local file or a URL.

        @param image_id: Optional. The UUID for the new image.
        @param source: The source of the image (e.g. a project or website name).
        @param image_file: A DataRoomFile object for a local image.
        @param image_url: A URL for a remote image.
        @param attributes: A dictionary of attributes to associate with the image.
        @param tags: A list of tags to associate with the image.
        @param related_images: A dictionary mapping relation names to image IDs. E.g.
            `{
                "img1": "im2",
                "img2": "im2",
                "another image": "im3",
            }`.
        @return: A dictionary representing the newly created image.
        """
        if not image_file and not image_url:
            raise DataRoomError('Please provide either an "image_file" or "image_url" field')

        if not image_id and not image_url:
            raise DataRoomError('Please provide either an "image_id" or "image_url" field')

        if not source:
            raise DataRoomError('Please provide a "source" field')

        json_data = dict_filter_none(
            {
                "id": image_id,
                "image_url": image_url,
                "source": source,
                "attributes": attributes,
                "tags": tags,
                "related_images": related_images,
            }
        )

        if image_file:
            # when uploading an image, we need to send a multipart/form-data request, not JSON
            # the image is sent as a file, and the rest of the data is sent as text/plain
            if not isinstance(image_file, DataRoomFile):
                raise DataRoomError("Argument image_file must be a DataRoomFile")
            files = {
                "image": (
                    image_file.filename,
                    image_file.bytes_io,
                    image_file.content_type,
                ),
                "json": (None, json_module.dumps(json_data), "text/plain"),
            }
            return await self._c._make_request(url="images/", method="POST", files=files)
        else:
            # application/json request
            return await self._c._make_request(
                url="images/",
                method="POST",
                json=json_data,
            )

    async def create_many(
        self,
        images: list[ImageCreate],
    ) -> list[dict]:
        """
        Creates multiple images in a single bulk request.

        @param images: A list of ImageCreate dictionaries, each defining an image to create.
        @return: A list of dictionaries representing the newly created images.
        """
        files = []
        for i, image in enumerate(images):
            if 'id' not in image:
                raise DataRoomError("Missing 'id' field in image")
            if 'source' not in image:
                raise DataRoomError("Missing 'source' field in image")
            if 'image_file' not in image and 'image_url' not in image:
                raise DataRoomError('Please provide either an "image_file" or "image_url" field')

            image_file = image.get('image_file')
            if image_file and not isinstance(image_file, DataRoomFile):
                raise DataRoomError("Argument image_file must be a DataRoomFile")

            if image_file:
                files.append((
                    f"image_{i}",
                    (
                        image_file.filename,
                        image_file.bytes_io,
                        image_file.content_type,
                    ),
                ))

            json_data = dict_filter_none({
                "id": image['id'],
                "source": image['source'],
                "image_url": image.get('image_url'),
                "attributes": image.get('attributes'),
                "tags": image.get('tags'),
                "related_images": image.get('related_images'),
            })
            files.append((
                f"json_{i}",
                (None, json_module.dumps(json_data), "text/plain")
            ))

        return await self._c._make_request(url="images/", method="POST", files=files)

    async def update(
        self,
        image_id: str,
        source: str = None,
        attributes: dict = None,
        latents: list[LatentType] = None,
        tags: list[str] = None,
        coca_embedding: str = None,
        related_images: dict[str, str] | None = None,
    ) -> dict:
        """
        Update the image.

         * overwrite tags
         * merge attributes
         * merge latents
         * merge related_images

        @param image_id: The UUID of the image to update.
        @param source: The source of the image (e.g. a project or website name).
        @param attributes: A dictionary of attributes to associate with the image.
        @param latents: A list of latent types to associate with the image.
        @param tags: A list of tags to associate with the image.
        @param coca_embedding: A string representing a list of 768 floats, e.g. `"[0.12345,1.23456,...]"`.
        @param related_images: A dictionary mapping relation names to image IDs. E.g.
            `{
                "img1": "im2",
                "img2": "im2",
                "another image": "im3",
            }`.
        @return: A dictionary representing the updated image.
        """

        if coca_embedding:
            validate_vector(coca_embedding)

        if latents:
            files = []
            for i, latent in enumerate(latents):
                if 'latent_type' not in latent:
                    raise DataRoomError("Missing 'latent_type' field in latent")
                if 'file' not in latent:
                    raise DataRoomError("Missing 'file' field in latent")
                if not isinstance(latent['file'], DataRoomFile):
                    raise DataRoomError("Property 'file' must be a DataRoomFile")

                latent_file = latent['file']
                files.append((
                    f"latent_{i}",
                    (
                        latent_file.filename,
                        latent_file.bytes_io,
                        latent_file.content_type,
                    ),
                ))

                json_data = dict_filter_none({
                    "latent_type": latent['latent_type'],
                })
                files.append((
                    f"latent_json_{i}",
                    (None, json_module.dumps(json_data), "text/plain")
                ))

            image_data = dict_filter_none({
                "source": source,
                "attributes": attributes,
                "tags": tags,
                "coca_embedding": coca_embedding,
                "related_images": related_images,
            })
            files.append((
                "json",
                (None, json_module.dumps(image_data), "text/plain")
            ))
            return await self._c._make_request(url=f"images/{image_id}/", method="PUT", files=files)
        else:
            return await self._c._make_request(
                url=f"images/{image_id}/",
                method="PUT",
                json=dict_filter_none({
                    "source": source,
                    "attributes": attributes,
                    "tags": tags,
                    "coca_embedding": coca_embedding,
                    "related_images": related_images,
                }),
            )

    async def update_many(
        self,
        images: list[ImageUpdate],
    ) -> list[dict]:
        """
        Bulk update images.

         * overwrite tags
         * merge attributes
         * merge latents
         * merge related_images

        @param images: A list of ImageUpdate dictionaries, each defining an image to update.
        @return: A list of dictionaries representing the updated images.
        """
        for image in images:
            if 'id' not in image:
                raise DataRoomError("Missing 'id' field in image")
            image.setdefault('source', None)
            image.setdefault('attributes', None)
            image.setdefault('tags', None)
            image.setdefault('coca_embedding', None)
            image.setdefault('related_images', None)

        return await self._c._make_request(
            url=f"images/bulk_update/",
            method="PUT",
            json=[
                dict_filter_none({
                    "id": image['id'],
                    "source": image['source'],
                    "attributes": image['attributes'],
                    "tags": image['tags'],
                    "coca_embedding": image['coca_embedding'],
                    "related_images": image['related_images'],
                })
                for image in images
            ],
        )

    async def delete(self, image_id: str) -> dict:
        """
        Deletes a single image by its ID.

        @param image_id: The UUID of the image to delete.
        """
        return await self._c._make_request(
            url=f"images/{image_id}/",
            method="DELETE",
        )

    async def similarity(self, image_id_1: str, image_id_2: str) -> dict:
        """
        Calculates the similarity score between two images.

        @param image_id_1: The UUID of the first image.
        @param image_id_2: The UUID of the second image.
        @return: A dictionary containing the similarity score.
        """
        response = await self._c._make_request(
            url=f"images/{image_id_1}/similarity/",
            method="POST",
            json={
                "image_id": image_id_2,
            },
        )
        return response["similarity"]

    async def similar(
        self,
        # similarity by
        image_id: str = None,
        image_file: DataRoomFile = None,
        image_vector: str = None,
        image_text: str = None,
        # options
        number=5,
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
        # filters
        short_edge: int | None = None,
        short_edge__gt: int = None,
        short_edge__gte: int = None,
        short_edge__lt: int = None,
        short_edge__lte: int = None,
        pixel_count: int | None = None,
        pixel_count__gt: int = None,
        pixel_count__gte: int = None,
        pixel_count__lt: int = None,
        pixel_count__lte: int = None,
        aspect_ratio_fraction: str = None,
        aspect_ratio: float = None,
        aspect_ratio__gt: float = None,
        aspect_ratio__gte: float = None,
        aspect_ratio__lt: float = None,
        aspect_ratio__lte: float = None,
        sources: list[str] = None,
        sources__ne: list[str] = None,
        attributes: dict = None,
        has_attributes: list = None,
        lacks_attributes: list = None,
        has_latents: list[str] = None,
        lacks_latents: list[str] = None,
        has_masks: list[str] = None,
        lacks_masks: list[str] = None,
        tags: list = None,
        tags__ne: list = None,
        tags__all: list = None,
        tags__ne_all: list = None,
        tags__empty: bool = None,
        coca_embedding__empty: bool = None,
        duplicate_state: ClientDuplicateState = None,
        date_created__gt: datetime = None,
        date_created__gte: datetime = None,
        date_created__lt: datetime = None,
        date_created__lte: datetime = None,
        date_updated__gt: datetime = None,
        date_updated__gte: datetime = None,
        date_updated__lt: datetime = None,
        date_updated__lte: datetime = None,
        datasets: list = None,
        datasets__ne: list = None,
        datasets__all: list = None,
        datasets__ne_all: list = None,
        datasets__prefix: list = None,
        datasets__empty: bool = None,
        query: str = None,
    ) -> list[dict]:
        """
        Finds images similar to a given image, vector, or text query.

        You must provide exactly one of `image_id`, `image_file`, `image_vector`, or `image_text`.

        @param image_id: Find images similar to the image with this UUID.
        @param image_file: Find images similar to this local image file.
        @param image_vector: Find images similar to this image embedding vector formatted as
            a string of 768 floats, e.g. `"[0.12345,1.23456,...]"`.
        @param image_text: Find images similar to this text query.
        @param number: The number of similar images to return.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for each image.
        @param ...: Various filter and field selection parameters.
        @return: A list of similar image dictionaries.
        """
        search_args = {
            'image_id': image_id, 'image_file': image_file, 'image_vector': image_vector, 'image_text': image_text,
        }
        if sum([bool(arg) for arg in search_args.values()]) != 1:
            raise DataRoomError(f'Please provide one of the following arguments: {", ".join(search_args.keys())}')

        params = dict_filter_none({
            "fields": ",".join(fields) if fields else None,
            "include_fields": ",".join(include_fields) if include_fields else None,
            "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
            "all_fields": all_fields if all_fields else None,
            "return_latents": ",".join(return_latents) if return_latents else None,
            # filters
            "short_edge": short_edge,
            "short_edge__gt": short_edge__gt,
            "short_edge__gte": short_edge__gte,
            "short_edge__lt": short_edge__lt,
            "short_edge__lte": short_edge__lte,
            "pixel_count": pixel_count,
            "pixel_count__gt": pixel_count__gt,
            "pixel_count__gte": pixel_count__gte,
            "pixel_count__lt": pixel_count__lt,
            "pixel_count__lte": pixel_count__lte,
            "aspect_ratio_fraction": aspect_ratio_fraction,
            "aspect_ratio": aspect_ratio,
            "aspect_ratio__gt": aspect_ratio__gt,
            "aspect_ratio__gte": aspect_ratio__gte,
            "aspect_ratio__lt": aspect_ratio__lt,
            "aspect_ratio__lte": aspect_ratio__lte,
            "sources": ",".join(sources) if sources else None,
            "sources__ne": ",".join(sources__ne) if sources__ne else None,
            "attributes": get_attributes_filter(attributes),
            "has_attributes": ",".join(has_attributes) if has_attributes else None,
            "lacks_attributes": ",".join(lacks_attributes) if lacks_attributes else None,
            "has_latents": ",".join(has_latents) if has_latents else None,
            "lacks_latents": ",".join(lacks_latents) if lacks_latents else None,
            "has_masks": ",".join(has_masks) if has_masks else None,
            "lacks_masks": ",".join(lacks_masks) if lacks_masks else None,
            "tags": ",".join(tags) if tags else None,
            "tags__ne": ",".join(tags__ne) if tags__ne else None,
            "tags__all": ",".join(tags__all) if tags__all else None,
            "tags__ne_all": ",".join(tags__ne_all) if tags__ne_all else None,
            "tags__empty": tags__empty,
            "coca_embedding__empty": coca_embedding__empty,
            "duplicate_state": duplicate_state.value if duplicate_state else None,
            "date_created__gt": date_created__gt.isoformat() if date_created__gt else None,
            "date_created__gte": date_created__gte.isoformat() if date_created__gte else None,
            "date_created__lt": date_created__lt.isoformat() if date_created__lt else None,
            "date_created__lte": date_created__lte.isoformat() if date_created__lte else None,
            "date_updated__gt": date_updated__gt.isoformat() if date_updated__gt else None,
            "date_updated__gte": date_updated__gte.isoformat() if date_updated__gte else None,
            "date_updated__lt": date_updated__lt.isoformat() if date_updated__lt else None,
            "date_updated__lte": date_updated__lte.isoformat() if date_updated__lte else None,
            "datasets": ",".join(datasets) if datasets else None,
            "datasets__ne": ",".join(datasets__ne) if datasets__ne else None,
            "datasets__all": ",".join(datasets__all) if datasets__all else None,
            "datasets__ne_all": ",".join(datasets__ne_all) if datasets__ne_all else None,
            "datasets__prefix": ",".join(datasets__prefix) if datasets__prefix else None,
            "datasets__empty": datasets__empty,
            "query": query,
        })

        if image_file:
            # by image file
            if not isinstance(image_file, DataRoomFile):
                raise DataRoomError("Argument image_file must be a DataRoomFile")
            json_data = {
                "number": number,
            }
            files = {
                "image": (
                    image_file.filename,
                    image_file.bytes_io,
                    image_file.content_type,
                ),
                "json": (None, json_module.dumps(json_data), "text/plain"),
            }
            return await self._c._make_request(
                url=f"images/similar_to_file/",
                method="POST",
                files=files,
                params=params,
            )
        elif image_id:
            # by image id
            response = await self._c._make_request(
                url=f"images/{image_id}/similar/",
                params={
                    "number": number,
                    **params,
                },
            )
            return response
        elif image_vector:
            # by image vector
            validate_vector(image_vector)
            return await self._c._make_request(
                url=f"images/similar_to_vector/",
                method="POST",
                json={
                    "vector": image_vector,
                    "number": number,
                },
                params=params,
            )
        elif image_text:
            # by text
            return await self._c._make_request(
                url=f"images/similar_to_text/",
                method="POST",
                json={
                    "text": image_text,
                    "number": number,
                },
                params=params,
            )
        else:
            raise DataRoomError("Invalid arguments")

    async def related(
        self,
        image_id: str,
        # options
        fields: list[str] = None,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
        all_fields: bool = False,
        return_latents: list[str] = None,
    ) -> list[dict]:
        """
        Retrieves images related to a specific image.

        @param image_id: The UUID of the image to find related images for.
        @param fields: A list of fields to return for each image. This overrides the default fields.
        @param include_fields: A list of fields to include in the response, in addition to `fields` or the default fields.
        @param exclude_fields: A list of fields to exclude from the response.
        @param all_fields: If True and `fields` is None, returns all available fields for each image.
        @param return_latents: A list of latent types to return for each image.
        @return: A list of related image dictionaries.
        """
        params = dict_filter_none({
            "fields": ",".join(fields) if fields else None,
            "include_fields": ",".join(include_fields) if include_fields else None,
            "exclude_fields": ",".join(exclude_fields) if exclude_fields else None,
            "all_fields": all_fields if all_fields else None,
            "return_latents": ",".join(return_latents) if return_latents else None,
        })
        return await self._c._make_request(
            url=f"images/{image_id}/related/",
            params=params,
        )

    async def delete_latent(self, image_id: str, latent_type: str) -> dict:
        """
        Deletes a latent representation from an image.

        @param image_id: The UUID of the image to update.
        @param latent_type: The type of the latent to delete.
        @return: A dictionary representing the updated image.
        """
        return await self._c._make_request(
            url=f"images/{image_id}/delete_latent/",
            method="POST",
            json={
                "latent_type": latent_type,
            },
        )

    async def aggregate(self, field, type) -> dict:
        """
        Performs an aggregation operation on a specified field across all images.

        @param field: The field to aggregate on (e.g., 'source', 'aspect_ratio').
        @param type: The type of aggregation to perform (e.g., 'value_counts').
        @return: The result of the aggregation.
        """
        return await self._c._make_request(
            url="images/aggregate/",
            method="POST",
            json={
                "field": field,
                "type": type,
            },
        )

    async def bucket(self, field, size) -> list[dict]:
        """
        Groups images into buckets based on a specified field and bucket size.

        @param field: The field to bucket on (e.g., 'date_created').
        @param size: The size or interval for each bucket (e.g., 'day', 'month').
        @return: A list of buckets with counts.
        """
        return await self._c._make_request(
            url="images/bucket/",
            method="POST",
            json={
                "field": field,
                "size": size,
            },
        )

    async def groups(self, image_id: str) -> list[dict]:
        """
        Lists all (non-deleted) groups this image is a member of, hydrated.

        Each item: {group: {...}, role, metadata}.
        """
        return await self._c._make_request(url=f"images/{image_id}/groups/", method="GET")

