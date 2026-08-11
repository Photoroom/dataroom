"""``client.groups`` / ``client.roles`` / ``client.group_types``.

Setup flow when starting from an empty DB:
  1. ``roles.create(name)`` for each allowed role
  2. ``group_types.create(name, roles=[{role, is_required}, ...])`` with
     admin credentials
  3. ``groups.upsert(name, type=..., members=...)`` to create groups and
     attach memberships
All four (Roles, GroupTypes, Groups, Memberships) are open to any
token-authenticated dataroom user.
Group ids are plain UUIDs in Postgres; the type is its own column.
Membership rows carry a canonical role plus free-form metadata.

The flat client methods (``get_groups``, ``upsert_group``, ...) are thin
delegates to these classes - see ``_compat.py``.
"""

from __future__ import annotations

import uuid

from .base import Resource, dict_filter_none, group_expand_params


class RolesResource(Resource):
    """``client.roles``.

    The vocabulary of member roles. A GroupType declares which of these roles
    its groups use, so create the roles first, then the type.
    """

    async def list(self, limit: int = 1000) -> list[dict]:
        """Lists all roles."""
        return await self._c._make_paginated_request(url="roles/", limit=limit)

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def create(self, name: str, description: str = None) -> dict:
        """Creates a role. Roles are referenced by name from GroupTypeRole rows."""
        payload = dict_filter_none({"name": name, "description": description})
        return await self._c._make_request(url="roles/", method="POST", json=payload)

    async def delete(self, name: str) -> None:
        """Deletes a role. Fails if any GroupTypeRole still references it."""
        return await self._c._make_request(url=f"roles/{name}/", method="DELETE")



class GroupTypesResource(Resource):
    """``client.group_types``.

    Immutable templates for groups: each type names its allowed (role,
    is_required) pairs and a JSON schema for group metadata.
    """

    async def list(self, limit: int = 1000) -> list[dict]:
        """Lists all GroupTypes with their (role, is_required) pairs."""
        return await self._c._make_paginated_request(url="group-types/", limit=limit)

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, name: str) -> dict:
        """Retrieves a single GroupType by name."""
        return await self._c._make_request(url=f"group-types/{name}/", method="GET")

    async def create(
        self,
        name: str,
        roles: list[dict] = None,
        description: str = None,
        metadata_schema: dict = None,
    ) -> dict:
        """Creates a GroupType.

        @param name: lowercase alphanumeric/underscore; doubles as the OS-encoding
                     prefix (``<name>::<uuid>``).
        @param roles: list of ``{"role": <existing role name>, "is_required": bool}``.
                      Roles must already exist - create them with ``roles.create`` first.
        @param description: optional free-form description.
        @param metadata_schema: JSON Schema applied to ``Group.metadata`` for groups
                                of this type.
        """
        payload = dict_filter_none({
            "name": name,
            "description": description,
            "metadata_schema": metadata_schema,
            "roles": roles,
        })
        return await self._c._make_request(url="group-types/", method="POST", json=payload)

    # No update_group_type: GroupTypes are immutable. A type's name is baked
    # into the OS encoding of its groups and its schema/roles gate their
    # validation, so the server rejects PUT/PATCH on group-types. Create a new
    # type (and migrate) instead.

    async def delete(self, name: str) -> None:
        """Deletes a GroupType. Fails if any Group of this type exists."""
        return await self._c._make_request(url=f"group-types/{name}/", method="DELETE")



class GroupsResource(Resource):
    """``client.groups`` - typed buckets of images.

    A group ties related images together under one GroupType, each member
    carrying a role from that type - the shots of one garment, the frames of
    one scene. ``upsert`` is the idempotent create-or-replace for one group;
    ``create_many`` and ``delete_many`` are the batch paths for imports.
    """

    async def list(
        self,
        type: str = None,
        search: str = None,
        limit: int = 1000,
        *,
        dataset: str = None,
        name_prefix: str = None,
        roles: list[str] = None,
        has_role: list[str] = None,
        include_roles: bool = False,
        return_roles: list[str] = None,
        include_metadata: bool = False,
        include_presigned_urls: bool = False,
        include_os_metadata: bool = False,
        include_thumbnail_urls: bool = False,
        include_datasets: bool = False,
    ) -> list[dict]:
        """
        Lists groups. This is the one entry point for fetching groups, whatever the
        angle: by type, by dataset membership, by role, or by text search.

        @param type: Optional group type filter (a GroupType.name).
        @param search: Optional substring search over name and id.
        @param limit: Maximum number of groups to return.
        @param dataset: Only groups that are active members of this dataset
            (``"<slug>/<version>"``). Replaces the removed ``get_dataset_groups``.
        @param name_prefix: Only groups whose name starts with this (case-insensitive).
        @param roles: Only groups whose TYPE declares all of these roles.
        @param has_role: Only groups that actually have an active membership for each
            of these roles (vs. ``roles``, which matches the type's declaration).
        @param include_roles: Attach each group's members as ``roles``:
            ``[{image_id, role}, ...]``.
        @param return_roles: Narrow the attached members to these role names.
        @param include_metadata: Include group and membership metadata.
        @param include_presigned_urls: Attach a presigned url per member image
            (implies ``include_roles``).
        @param include_os_metadata: Attach each member image's attributes
            (implies ``include_roles``).
        @param include_thumbnail_urls: Attach a thumbnail url per member image
            (implies ``include_roles``). ``include_presigned_urls`` is the original
            image's url, or null when the image has no original - it never falls
            back to the thumbnail.
        @param include_datasets: Attach each group's dataset memberships as
            ``datasets``: ``["<slug>/<version>", ...]``.
        @return: List of group dicts.
        """
        params = dict_filter_none({
            "type": type,
            "search": search,
            "dataset": dataset,
            "name__prefix": name_prefix,
            "roles": ",".join(roles) if roles else None,
            "has_role": ",".join(has_role) if has_role else None,
        })
        expand = group_expand_params(
            include_roles, return_roles, include_metadata, include_presigned_urls,
            include_os_metadata, include_thumbnail_urls, include_datasets,
        )
        if expand:
            params.update(expand)
        return await self._c._make_paginated_request(url="groups/", params=params or None, limit=limit)

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, group_id: str, include_members: bool = False) -> dict:
        """
        Retrieves a single group by id.

        @param group_id: Group UUID.
        @param include_members: When True, also fetch the group's memberships
            (a second request to the members endpoint, which is paginated and
            not part of the group representation) and attach them under a
            ``members`` key as ``[{image_id, role, metadata}, ...]`` - the
            shape ``upsert`` accepts, so a fetched group round-trips
            without silently dropping members.
        @return: Group dict (with ``members`` when ``include_members``).
        """
        group = await self._c._make_request(url=f"groups/{group_id}/", method="GET")
        if include_members:
            group["members"] = [
                {"image_id": m["image_id"], "role": m["role"], "metadata": m.get("metadata", {})}
                for m in await self.members(group_id)
            ]
        return group

    async def update(
        self,
        group_id: str,
        name: str = None,
        description: str = None,
        metadata: dict = None,
        cover_image_id: str = None,
    ) -> dict:
        """
        Partially updates a group. The `type` is immutable and cannot be changed.

        @param group_id: Group UUID.
        @return: Updated group dict.
        """
        payload = dict_filter_none({
            "name": name,
            "description": description,
            "metadata": metadata,
            "cover_image_id": cover_image_id,
        })
        return await self._c._make_request(
            url=f"groups/{group_id}/",
            method="PATCH",
            json=payload,
        )

    async def delete(self, group_id: str) -> None:
        """
        Soft-deletes a group and queues the OS scrub. The Postgres row is
        finalized by the reconciler once OS is clean.
        """
        return await self._c._make_request(url=f"groups/{group_id}/", method="DELETE")

    async def members(self, group_id: str, limit: int = 1000) -> list[dict]:
        """
        Lists memberships of a group.

        @return: List of {id, image_id, role, metadata, ...}.
        """
        return await self._c._make_paginated_request(url=f"groups/{group_id}/members/", limit=limit)

    async def upsert(
        self,
        name: str,
        type: str,
        metadata: dict = None,
        members: list[dict] = None,
        description: str = None,
        cover_image_id: str = None,
        group_id: str = None,
    ) -> dict:
        """Create-or-replace a group by name. One PUT round-trip in the common case.

        Re-running the same call with the same ``name`` is idempotent: the client
        looks up an existing group with that name (or uses the explicit ``group_id``
        when supplied), and PUTs the whole ``{metadata, members}`` payload to its
        UUID. New groups get a fresh UUID4 generated client-side and committed via
        the same PUT. The server validates roles + metadata in one transaction.
        """
        if group_id is None:
            matches = [g for g in await self.list(search=name) if g['name'] == name]
            group_id = matches[0]['id'] if matches else str(uuid.uuid4())

        payload = dict_filter_none({
            "name": name,
            "type": type,
            "metadata": metadata if metadata is not None else {},
            "members": members if members is not None else [],
            "description": description,
            "cover_image_id": cover_image_id,
        })
        return await self._c._make_request(
            url=f"groups/{group_id}/",
            method="PUT",
            json=payload,
        )

    async def create_many(self, groups: list[dict]) -> list[dict]:
        """Create many groups in one request - the fast path for importing at scale.

        Each entry: ``{"name", "type", "members"?, "metadata"?, "description"?}``, where
        members is ``[{"image_id", "role"}, ...]``. The whole batch is one transaction and
        one OpenSearch write server-side, vs one round trip per group with ``upsert``.
        At most 1000 groups per call. Returns the created group dicts.
        """
        return await self._c._make_request(url="groups/bulk/", method="POST", json={"groups": list(groups)})

    async def delete_many(self, group_ids: list[str]) -> dict:
        """Delete many groups in one request - the counterpart of ``create_many``.

        One transaction and one OpenSearch write server-side, vs one round trip per group
        with ``delete``. At most 1000 ids per call. Ids that are unknown or already
        deleted are ignored, so a retry is safe. Returns ``{"deleted_count": n}``.

        POST, not DELETE: the ids ride in the body, and OpenAPI does not describe a body on
        DELETE - so the endpoint is a POST to keep the generated schema honest.
        """
        return await self._c._make_request(
            url="groups/bulk-delete/", method="POST", json={"group_ids": [str(g) for g in group_ids]}
        )

