import jsonschema
import pytest

from backend.dataroom.choices import AttributesFieldType, AttributesFieldStringFormat
from backend.dataroom.models.attributes import AttributesField, AttributesSchema, AttributesFieldNotFoundError


@pytest.fixture
def all_attributes():
    return [
        AttributesField.objects.create(name="name", field_type="string", is_indexed=True),
        AttributesField.objects.create(name="width", field_type="integer"),
        AttributesField.objects.create(name="approved", field_type="boolean", is_required=True, is_indexed=True),
        AttributesField.objects.create(name="date", field_type="string", string_format="date-time"),
        AttributesField.objects.create(name="numbers", field_type="array", array_type="number", is_indexed=True),
        AttributesField.objects.create(name="some_number", field_type="number", enum_choices=[1, 2, 3], is_indexed=True),
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
                "is_indexed": True,
            },
            "width": {
                "type": "integer",
                "is_indexed": False,
            },
            "approved": {
                "type": "boolean",
                "is_indexed": True,
            },
            "date": {
                "type": "string",
                "format": "date-time",
                "is_indexed": False,
            },
            "numbers": {
                "type": "array",
                "items": {"type": "number"},
                "is_indexed": True,
            },
            "some_number": {
                "type": "number",
                "enum": [1, 2, 3],
                "is_indexed": True,
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


@pytest.mark.django_db
def test_indexed_vs_non_indexed_attributes():
    """Test indexed vs non-indexed attributes functionality."""
    from backend.dataroom.models.os_image import OSAttribute
    from backend.dataroom.choices import OSFieldType
    
    # Test indexed attribute (default behavior)
    indexed_attr = AttributesField.objects.create(
        name="indexed_field",
        field_type="string",
        is_indexed=True
    )
    assert indexed_attr.is_indexed is True
    assert indexed_attr.os_field_name == "attr_indexed_field_text"
    
    # Test non-indexed attribute
    nonindexed_attr = AttributesField.objects.create(
        name="nonindexed_field", 
        field_type="string",
        is_indexed=False
    )
    assert nonindexed_attr.is_indexed is False
    assert nonindexed_attr.os_field_name == "attr_noidx_nonindexed_field_keyword"
    
    # Test OSAttribute with indexed=True
    os_attr_indexed = OSAttribute("test", "value", OSFieldType.TEXT, is_indexed=True)
    assert os_attr_indexed.os_name == "attr_test_text"
    assert os_attr_indexed.os_name_keyword == "attr_test_text.keyword"
    
    # Test OSAttribute with indexed=False, no nested keyword field, the main field is of type keyword
    os_attr_nonindexed = OSAttribute("test", "value", OSFieldType.KEYWORD, is_indexed=False)
    assert os_attr_nonindexed.os_name == "attr_noidx_test_keyword"  
    assert os_attr_nonindexed.os_name_keyword == "attr_noidx_test_keyword"
    
    # Test default is_indexed behavior
    default_attr = AttributesField.objects.create(name="default_field", field_type="integer")
    assert default_attr.is_indexed is False # Model default should be False


@pytest.mark.django_db  
def test_os_attributes_from_mapping_with_prefixes():
    """Test OSAttributes parsing from OpenSearch mapping with both prefixes."""
    from backend.dataroom.models.os_image import OSAttributes
    
    # Mock mapping with both indexed and non-indexed attributes
    mock_mapping = {
        "attr_indexed_field_text": {"type": "text"},
        "attr_noidx_nonindexed_field_text": {"type": "text", "index": False},
        "attr_count_long": {"type": "long"},
        "attr_noidx_metadata_double": {"type": "double", "index": False},
        "other_field": {"type": "keyword"}  # Should be ignored
    }
    
    attributes = OSAttributes.from_mapping(mock_mapping)
    
    # Should have parsed 4 attributes (2 indexed, 2 non-indexed)
    assert len(attributes.attributes) == 4
    
    # Check indexed attributes
    assert "indexed_field" in attributes.attributes
    assert attributes.attributes["indexed_field"].is_indexed is True
    assert attributes.attributes["indexed_field"].os_name == "attr_indexed_field_text"
    
    assert "count" in attributes.attributes  
    assert attributes.attributes["count"].is_indexed is True
    assert attributes.attributes["count"].os_name == "attr_count_long"
    
    # Check non-indexed attributes
    assert "nonindexed_field" in attributes.attributes
    assert attributes.attributes["nonindexed_field"].is_indexed is False
    assert attributes.attributes["nonindexed_field"].os_name == "attr_noidx_nonindexed_field_text"
    
    assert "metadata" in attributes.attributes
    assert attributes.attributes["metadata"].is_indexed is False  
    assert attributes.attributes["metadata"].os_name == "attr_noidx_metadata_double"


@pytest.mark.django_db
def test_object_attribute_functionality():
    """Test OBJECT type attributes functionality."""
    from backend.dataroom.models.os_image import OSAttribute
    from backend.dataroom.choices import OSFieldType, AttributesFieldType
    from django.core.exceptions import ValidationError
    
    # Test creating an OBJECT attribute
    obj_attr = AttributesField.objects.create(
        name="metadata",
        field_type=AttributesFieldType.OBJECT
    )
    
    # OBJECT attributes should always be non-indexed
    assert obj_attr.field_type == AttributesFieldType.OBJECT
    assert obj_attr.os_field_name == "attr_noidx_metadata_object"
    
    # Test OSAttribute with object data
    nested_data = {
        "product_info": {
            "name": "Widget",
            "specs": {
                "dimensions": {"width": 10, "height": 5},
                "features": ["waterproof", "durable"]
            }
        }
    }
    
    os_attr = OSAttribute("metadata", nested_data, OSFieldType.OBJECT, is_indexed=False)
    assert os_attr.os_name == "attr_noidx_metadata_object"
    assert os_attr.value == nested_data
    
    # Test object validation - should accept dict
    valid_object = {"key": "value", "nested": {"inner": 123}}
    os_attr_valid = OSAttribute("test", valid_object, OSFieldType.OBJECT, is_indexed=False)
    assert os_attr_valid.value == valid_object
    
    # Test object validation - should reject non-dict
    with pytest.raises(ValueError, match="Object attribute values must be dictionaries"):
        OSAttribute("test", "not an object", OSFieldType.OBJECT)
    
    with pytest.raises(ValueError, match="Object attribute values must be dictionaries"):
        OSAttribute("test", 123, OSFieldType.OBJECT)
    
    with pytest.raises(ValueError, match="Object attribute values must be dictionaries"):
        OSAttribute("test", ["array"], OSFieldType.OBJECT)

    # Test object validation - should reject indexed objects
    with pytest.raises(ValueError, match="Object attributes cannot be indexed"):
        OSAttribute("test", valid_object, OSFieldType.OBJECT, is_indexed=True)


@pytest.mark.django_db  
def test_object_attribute_validation():
    """Test validation rules for OBJECT attributes."""
    from django.core.exceptions import ValidationError
    
    # Test that arrays of objects are not allowed
    with pytest.raises(ValidationError, match="Arrays of objects are not supported"):
        AttributesField.objects.create(
            name="obj_array",
            field_type=AttributesFieldType.ARRAY,
            array_type=AttributesFieldType.OBJECT
        )
    
    # Test that object types cannot have string_format
    with pytest.raises(ValidationError, match="Object types cannot have a string format"):
        AttributesField.objects.create(
            name="bad_obj",
            field_type=AttributesFieldType.OBJECT,
            string_format=AttributesFieldStringFormat.DATE
        )

    # Test that object types cannot be indexed
    with pytest.raises(ValidationError, match=""):
        AttributesField.objects.create(
            name="bad_obj",
            field_type=AttributesFieldType.OBJECT,
            is_indexed=True,
        )


@pytest.mark.django_db
def test_object_schema_conversion():
    """Test schema conversion methods for OBJECT type."""
    from backend.dataroom.models.attributes import AttributesSchema
    from backend.dataroom.choices import OSFieldType, AttributesFieldType
    
    # Test converting from field type to OS type
    os_type = AttributesSchema.get_os_type(AttributesFieldType.OBJECT)
    assert os_type == OSFieldType.OBJECT
    
    # Test converting from OS type to field type  
    field_type, string_format = AttributesSchema.get_field_type_from_os_type(OSFieldType.OBJECT)
    assert field_type == AttributesFieldType.OBJECT
    assert string_format is None


@pytest.mark.django_db
def test_object_attributes_from_mapping():
    """Test parsing OBJECT attributes from OpenSearch mapping."""
    from backend.dataroom.models.os_image import OSAttributes
    from backend.dataroom.choices import OSFieldType
    
    # Mock mapping with object attribute
    mock_mapping = {
        "attr_noidx_metadata_object": {
            "type": "object", 
            "dynamic": False, 
            "enabled": False
        },
        "attr_title_text": {"type": "text"},
        "other_field": {"type": "keyword"}  # Should be ignored
    }
    
    attributes = OSAttributes.from_mapping(mock_mapping)
    
    # Should have parsed 2 attributes (1 object, 1 text)
    assert len(attributes.attributes) == 2
    
    # Check object attribute
    assert "metadata" in attributes.attributes
    obj_attr = attributes.attributes["metadata"]
    assert obj_attr.is_indexed is False
    assert obj_attr.os_type == OSFieldType.OBJECT
    assert obj_attr.os_name == "attr_noidx_metadata_object"
    
    # Check text attribute
    assert "title" in attributes.attributes
    text_attr = attributes.attributes["title"]
    assert text_attr.is_indexed is True
    assert text_attr.os_type == OSFieldType.TEXT

