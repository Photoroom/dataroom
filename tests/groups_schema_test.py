import jsonschema
import pytest

from backend.dataroom.groups.schemas import build_group_schema, build_group_schema_for_type
from backend.dataroom.models.group import GroupType


# ----------------------------------------------------------------------
# Pure builder tests — no DB. Drive build_group_schema with plain inputs.
# ----------------------------------------------------------------------

PRODUCT_META = {"type": "object", "additionalProperties": False, "properties": {}}
DATASET_META = {
    "type": "object",
    "additionalProperties": False,
    "required": ["author"],
    "properties": {"author": {"type": "string", "maxLength": 128}},
}
RELATIONSHIP_META = {
    "type": "object",
    "additionalProperties": False,
    "required": ["context"],
    "properties": {"context": {"type": "object"}},
}


def test_allows_known_roles_in_members():
    schema = build_group_schema(PRODUCT_META, ["onhang", "front", "side"], [])
    jsonschema.validate({"metadata": {}, "members": []}, schema)
    jsonschema.validate({"metadata": {}, "members": ["onhang", "front", "side"]}, schema)


def test_rejects_unknown_role_in_members():
    schema = build_group_schema(PRODUCT_META, ["onhang", "front", "side"], [])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {}, "members": ["ghost"]}, schema)


def test_metadata_schema_is_enforced():
    schema = build_group_schema(DATASET_META, ["member", "main"], ["main"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {}, "members": ["main"]}, schema)
    jsonschema.validate({"metadata": {"author": "alice"}, "members": ["main"]}, schema)


def test_required_role_must_appear_at_least_once():
    schema = build_group_schema(DATASET_META, ["member", "main"], ["main"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {"author": "alice"}, "members": ["member"]}, schema)
    jsonschema.validate(
        {"metadata": {"author": "alice"}, "members": ["member", "main"]}, schema
    )


def test_multiple_required_roles_each_must_appear():
    schema = build_group_schema(RELATIONSHIP_META, ["from", "to"], ["from", "to"])
    metadata = {"context": {"kind": "view"}}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": metadata, "members": ["from"]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": metadata, "members": ["to"]}, schema)
    jsonschema.validate({"metadata": metadata, "members": ["from", "to"]}, schema)


def test_top_level_keys_are_required_and_closed():
    schema = build_group_schema(PRODUCT_META, ["onhang"], [])

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"members": []}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {}, "members": [], "extra": 1}, schema)


# ----------------------------------------------------------------------
# DB-bound wrapper smoke test — uses the seeded GroupType / GroupTypeRole.
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_build_group_schema_for_type_pulls_from_db():
    gt = GroupType.objects.get(pk='recolor_dresses')
    schema = build_group_schema_for_type(gt)

    # roles & required pulled from GroupTypeRole; metadata_schema pulled from the column
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {}, "members": ["main"]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"metadata": {"author": "a"}, "members": ["member"]}, schema)
    jsonschema.validate({"metadata": {"author": "a"}, "members": ["member", "main"]}, schema)
