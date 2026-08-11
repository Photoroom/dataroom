"""Shared plumbing for the resource namespaces: the bound-client base class
and the parameter-shaping helpers the endpoint implementations use."""

from __future__ import annotations

from ..models import DataRoomError


class Resource:
    """A resource namespace bound to the client it was reached through.

    ``self._c`` supplies the HTTP transport (``_make_request``,
    ``_make_paginated_request``, ``_make_paginated_request_iter``) and the
    sibling namespaces for cross-resource calls. Bound to ``DataRoomClient``
    the methods return awaitables; ``DataRoomClientSync`` wraps each namespace
    so the same methods block (see ``_SyncResource`` in ``client.py``).
    """

    def __init__(self, client):
        self._c = client


def dict_filter_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def get_attributes_filter(attributes: dict | None) -> str | None:
    if not attributes:
        return None
    for key, val in attributes.items():
        val = str(val)
        if "," in key or "," in val:
            raise DataRoomError(
                "Commas are not allowed in attribute keys or values"
            )
        if ":" in key or ":" in val:
            raise DataRoomError(
                "Colons are not allowed in attribute keys or values"
            )
    attrs_str = ",".join([f"{key}:{val}" for key, val in attributes.items()])
    return attrs_str


def validate_vector(vector: str) -> None:
    err_msg = "Argument vector must be a string representing a list of 768 floats."
    if not isinstance(vector, str) or not len(vector) > 0:
        raise DataRoomError(f"{err_msg} Not a string.")
    if vector[0] != "[" or vector[-1] != "]":
        raise DataRoomError(f"{err_msg} Not a list.")
    if len(vector[1:-1].split(',')) != 768:
        raise DataRoomError(f"{err_msg} Incorrect length.")


def group_expand_params(
    include_roles: bool = False,
    return_roles: list[str] = None,
    include_metadata: bool = False,
    include_presigned_urls: bool = False,
    include_os_metadata: bool = False,
    include_thumbnail_urls: bool = False,
    include_datasets: bool = False,
) -> dict | None:
    """Query params for the group-expansion options, or None when nothing is asked
    for, so an unexpanded call stays a plain GET. presigned_url/os_metadata imply roles."""
    include_fields = []
    if include_roles or return_roles or include_presigned_urls or include_os_metadata or include_thumbnail_urls:
        include_fields.append("roles")
    if include_presigned_urls:
        include_fields.append("presigned_url")
    if include_thumbnail_urls:
        include_fields.append("thumbnail_url")
    if include_os_metadata:
        include_fields.append("os_metadata")
    if include_datasets:
        include_fields.append("datasets")

    params = {}
    if include_fields:
        params["include_fields"] = ",".join(include_fields)
    if return_roles:
        params["return_roles"] = ",".join(return_roles)
    if include_metadata:
        params["include_metadata"] = "true"
    return params or None
