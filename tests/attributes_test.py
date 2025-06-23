import jsonschema
import pytest

from backend.dataroom.choices import AttributesFieldType, AttributesFieldStringFormat
from backend.dataroom.models.attributes import AttributesField, AttributesSchema, AttributesFieldNotFoundError


@pytest.fixture
def all_attributes():
    return [
        AttributesField.objects.create(name="name", field_type="string"),
        AttributesField.objects.create(name="width", field_type="integer"),
        AttributesField.objects.create(name="approved", field_type="boolean", is_required=True),
        AttributesField.objects.create(name="date", field_type="string", string_format="date-time"),
        AttributesField.objects.create(name="numbers", field_type="array", array_type="number"),
        AttributesField.objects.create(name="some_number", field_type="number", enum_choices=[1, 2, 3]),
        AttributesField.objects.create(name="disabled", field_type="string", is_enabled=False),
    ]


@pytest.mark.django_db
def test_get_json_schema(all_attributes):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    schema = AttributesSchema.get_json_schema()
    assert schema == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "dataroom-image-attributes",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
            "width": {
                "type": "integer",
            },
            "approved": {
                "type": "boolean",
            },
            "date": {
                "type": "string",
                "format": "date-time",
            },
            "numbers": {
                "type": "array",
                "items": {"type": "number"},
            },
            "some_number": {
                "type": "number",
                "enum": [1, 2, 3],
            },
        },
        "required": ["approved"],
        "additionalProperties": False,
    }

    # fail on missing required property
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        AttributesSchema.validate_json({
            "name": "",
            "width": 1024,
            "date": "2023-02-01T00:00:00+00:00"
        })
    assert "'approved' is a required property" in str(excinfo.value)

    # fail on non-defined property
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        AttributesSchema.validate_json({
            "width": 1024,
            "approved": False,
            "disabled": "hmm",
        })
    assert "Additional properties are not allowed ('disabled' was unexpected)" in str(excinfo.value)

    # fail on wrong datetime format
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        AttributesSchema.validate_json({
            "width": 1024,
            "approved": False,
            "date": "2023-02-31"
        })
    assert "Failed validating 'format' in schema['properties']['date']" in str(excinfo.value)

    # fail on wrong integer
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        AttributesSchema.validate_json({
            "width": 3.14159,
            "approved": False,
        })
    assert "3.14159 is not of type 'integer'" in str(excinfo.value)

    # valid example
    AttributesSchema.validate_json({
        "name": "hello",
        "width": 1024,
        "approved": True,
        "date": "2023-02-01T00:00:00+00:00",
        "numbers": [1, 2, 3],
        "some_number": 1,
    })


@pytest.mark.django_db
def test_attributes_get_os_type(all_attributes):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    assert AttributesSchema.get_os_type_for_field_name('name') == "text"
    assert AttributesSchema.get_os_type_for_field_name('width') == "long"
    assert AttributesSchema.get_os_type_for_field_name('approved') == "boolean"
    assert AttributesSchema.get_os_type_for_field_name('date') == "date"
    assert AttributesSchema.get_os_type_for_field_name('numbers') == "double"
    assert AttributesSchema.get_os_type_for_field_name('some_number') == "double"

    # fail on disabled field
    with pytest.raises(AttributesFieldNotFoundError) as excinfo:
        AttributesSchema.get_os_type_for_field_name("disabled")
    assert 'Field "disabled" not found in schema' in str(excinfo.value)

    # fail on wrong field
    with pytest.raises(AttributesFieldNotFoundError) as excinfo:
        AttributesSchema.get_os_type_for_field_name("fail")
    assert 'Field "fail" not found in schema' in str(excinfo.value)


@pytest.mark.django_db
def test_attributes_get_field_type_from_os_type(all_attributes):
    # force invalidate cache from other tests
    AttributesSchema.invalidate_cache()

    assert AttributesSchema.get_field_type_from_os_type("text") == (AttributesFieldType.STRING, None)
    assert AttributesSchema.get_field_type_from_os_type("date") == (
        AttributesFieldType.STRING, AttributesFieldStringFormat.DATE
    )
    assert AttributesSchema.get_field_type_from_os_type("double") == (AttributesFieldType.NUMBER, None)
    assert AttributesSchema.get_field_type_from_os_type("long") == (AttributesFieldType.INTEGER, None)
    assert AttributesSchema.get_field_type_from_os_type("boolean") == (AttributesFieldType.BOOLEAN, None)

    # fail on unsupported type
    with pytest.raises(ValueError) as excinfo:
        AttributesSchema.get_field_type_from_os_type("unsupported")
    assert 'Unsupported OS type: "unsupported"' in str(excinfo.value)

