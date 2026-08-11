"""``client.tags``.

The flat client methods (``get_tags``, ``tag_images``, ...) are thin delegates
to this class - see ``_compat.py``.
"""

from __future__ import annotations

from .base import Resource, dict_filter_none


class TagsResource(Resource):
    """``client.tags``.

    Free-form labels on images. ``apply`` tags a batch of images in one call;
    filter by tag with ``images.list(tags=[...])``.
    """

    async def list(self, limit: int = 1000) -> list[dict]:
        """
        Retrieves a list of all tags.

        @param limit: The maximum number of tags to return.
        @return: A list of tag dictionaries.
        """
        return await self._c._make_paginated_request(
            url=f"tags/",
            limit=limit,
        )

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, tag_id: str) -> dict:
        """
        Retrieves a single tag by its ID.

        @param tag_id: The ID of the tag to retrieve.
        @return: A dictionary representing the tag.
        """
        return await self._c._make_request(
            url=f"tags/{tag_id}/",
        )

    async def create(self, name: str, description: str = None) -> dict:
        """
        Creates a new tag.

        @param name: The name of the new tag.
        @param description: An optional description for the tag.
        @return: A dictionary representing the newly created tag.
        """
        return await self._c._make_request(
            url="tags/",
            method="POST",
            json=dict_filter_none(
                {
                    "name": name,
                    "description": description,
                }
            ),
        )

    async def apply(self, image_ids: list[str], tag_names: list[str]) -> list[dict]:
        """
        Associates a list of tags with a list of images.

        @param image_ids: A list of image UUIDs to tag.
        @param tag_names: A list of tag names to apply to the images.
        @return: A list of dictionaries representing the tagged images.
        """
        return await self._c._make_request(
            url="tags/tag_images/",
            method="PUT",
            json={
                "image_ids": image_ids,
                "tag_names": tag_names,
            },
        )
