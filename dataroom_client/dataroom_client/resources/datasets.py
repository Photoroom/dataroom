"""``client.datasets`` - versioned collections of groups.

The flat client methods (``get_datasets``, ``create_dataset``, ...) are thin
delegates to this class - see ``_compat.py``.
"""

from __future__ import annotations

from .base import Resource, dict_filter_none


class DatasetsResource(Resource):
    """``client.datasets``.

    Versioned collections of groups, addressed as ``slug/version``: assemble
    groups into a dataset, freeze it so a training run sees a fixed
    membership, copy it to start the next iteration.
    """

    async def list(self, limit: int = 1000, slug: str = None, type: str = None, search: str = None) -> list[dict]:
        """List datasets, every version, newest version first within each slug.

        Optionally filtered by slug, type or search."""
        params = dict_filter_none({"slug": slug, "type": type, "search": search})
        return await self._c._make_paginated_request(url="datasets/", limit=limit, params=params or None)

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, slug_version: str) -> dict:
        """Retrieve a single dataset by its ``slug/version``."""
        return await self._c._make_request(url=f"datasets/{slug_version}/")

    async def create(self, name: str, slug: str, type: str, description: str = None) -> dict:
        """Create a dataset. The version auto-increments per slug."""
        return await self._c._make_request(
            url="datasets/",
            method="POST",
            json=dict_filter_none({"name": name, "slug": slug, "type": type, "description": description}),
        )

    async def update(self, slug_version: str, name: str = None, description: str = None, type: str = None) -> dict:
        """Update a dataset's name or description. The ``type`` is immutable; passing a
        different one is rejected by the server."""
        return await self._c._make_request(
            url=f"datasets/{slug_version}/",
            method="PATCH",
            json=dict_filter_none({"name": name, "description": description, "type": type}),
        )

    async def delete(self, slug_version: str) -> None:
        """Delete a dataset."""
        await self._c._make_request(url=f"datasets/{slug_version}/", method="DELETE")

    async def add_groups(self, slug_version: str, group_ids: list[str]) -> dict:
        """Add groups to a dataset. Re-adding a previously removed group revives it."""
        return await self._c._make_request(
            url=f"datasets/{slug_version}/groups/", method="POST", json={"group_ids": list(group_ids)},
        )

    async def remove_groups(self, slug_version: str, group_ids: list[str]) -> dict:
        """Remove groups from a dataset (soft-deletes the membership)."""
        return await self._c._make_request(
            url=f"datasets/{slug_version}/groups/", method="DELETE", json={"group_ids": list(group_ids)},
        )

    async def add_images(self, slug_version: str, image_ids: list[str]) -> dict:
        """Add loose images to a ``single_image`` dataset. Each image is wrapped in a one-image group."""
        return await self._c._make_request(
            url=f"datasets/{slug_version}/images/", method="POST", json={"image_ids": list(image_ids)},
        )

    async def freeze(self, slug_version: str) -> None:
        """Freeze a dataset. Membership changes are rejected until it is unfrozen."""
        await self._c._make_request(url=f"datasets/{slug_version}/freeze/", method="POST")

    async def unfreeze(self, slug_version: str) -> None:
        """Unfreeze a dataset."""
        await self._c._make_request(url=f"datasets/{slug_version}/unfreeze/", method="POST")

    async def copy(self, slug_version: str, name: str, slug: str, description: str = None) -> dict:
        """Copy a dataset's members into a new dataset that inherits the source's type."""
        return await self._c._make_request(
            url=f"datasets/{slug_version}/copy/",
            method="POST",
            json=dict_filter_none({"name": name, "slug": slug, "description": description}),
        )

    async def groups(self, slug_version: str, **expand) -> list[dict]:
        """A dataset's member groups - the groups list filtered by dataset.

        Accepts every ``groups.list`` expansion kwarg (include_roles,
        include_metadata, include_datasets, include_thumbnail_urls,
        include_presigned_urls, ...).
        """
        return await self._c.groups.list(dataset=slug_version, **expand)
