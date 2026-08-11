"""Build a single JSON Schema for a whole-group payload.

The schema combines two sources:
- a metadata schema (raw JSON Schema, validates Group.metadata)
- a members schema derived from a list of allowed roles + required roles

Two entry points:
- ``build_group_schema``: pure function, no DB. Takes plain inputs.
- ``build_group_schema_for_type``: thin DB wrapper that pulls the inputs
  from a ``GroupType`` row and its ``GroupTypeRole`` children.
"""


def build_group_schema(
    metadata_schema: dict,
    allowed_roles: list[str],
    required_roles: list[str],
) -> dict:
    """Return a JSON Schema that validates ``{metadata, members}``.

    ``members`` is expected to be an array of role strings. Each must be
    in ``allowed_roles``; each role in ``required_roles`` must appear
    at least once.
    """
    members_schema: dict = {
        "type": "array",
        "items": {"type": "string", "enum": list(allowed_roles)},
    }
    if required_roles:
        members_schema["allOf"] = [{"contains": {"const": role}, "minContains": 1} for role in required_roles]

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["metadata", "members"],
        "properties": {
            "metadata": metadata_schema,
            "members": members_schema,
        },
    }


def build_group_schema_for_type(group_type) -> dict:
    """DB-bound variant: pulls allowed / required roles off the ``GroupType``."""
    allowed = list(group_type.type_roles.values_list('role__name', flat=True))
    required = list(group_type.type_roles.filter(is_required=True).values_list('role__name', flat=True))
    return build_group_schema(group_type.metadata_schema or {}, allowed, required)
