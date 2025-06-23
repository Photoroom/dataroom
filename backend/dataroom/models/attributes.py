import jsonschema
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import JSONField
from django.utils import timezone

from backend.common.base_model import BaseModel
from backend.common.validators import AlphanumericValidator
from backend.dataroom.choices import AttributesFieldStringFormat, AttributesFieldType, OSFieldType


class AttributesFieldNotFoundError(Exception):
    pass


class AttributesField(BaseModel):
    name = models.CharField(
        max_length=100,
        unique=True,
        validators=[
            MinLengthValidator(1),
            AlphanumericValidator(),
        ],
    )
    description = models.TextField(max_length=300, default='', blank=True)
    field_type = models.CharField(
        max_length=20,
        choices=AttributesFieldType.choices,
        default=AttributesFieldType.STRING,
    )
    string_format = models.CharField(max_length=20, choices=AttributesFieldStringFormat.choices, blank=True, null=True)
    array_type = models.CharField(max_length=20, choices=AttributesFieldType.choices, blank=True, null=True)
    enum_choices = JSONField(null=True, blank=True)
    is_required = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True, help_text="Is validation for this field enabled?")
    is_mapped = models.BooleanField(
        default=False,
        editable=False,
        help_text="Is this field present in OpenSearch mapping?",
    )
    image_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    @property
    def json_schema(self):
        schema = {
            "type": self.field_type,
        }
        if self.description:
            schema["description"] = self.description
        if self.field_type == AttributesFieldType.STRING and self.string_format:
            schema["format"] = self.string_format
        if self.field_type == AttributesFieldType.ARRAY:
            schema["items"] = {"type": self.array_type}
        if self.enum_choices:
            schema["enum"] = self.enum_choices
        return schema

    @property
    def os_field_name(self):
        from backend.dataroom.models.os_image import OSAttribute

        os_type = AttributesSchema.get_os_type(
            field_type=self.field_type,
            string_format=self.string_format,
            array_type=self.array_type,
        )
        attr = OSAttribute(name=self.name, value=None, os_type=os_type)
        return attr.os_name

    @classmethod
    def from_os_attribute(cls, os_attribute):
        """
        Convert OSAttribute to AttributesField
        """
        field_type, string_format = AttributesSchema.get_field_type_from_os_type(os_attribute.os_type)
        return cls(
            name=os_attribute.name,
            field_type=field_type,
            string_format=string_format,
            is_enabled=False,
        )


class AttributesSchemaClass:
    def __init__(self):
        self._json_schema = None
        self._cache_date = None
        self._cache_expiration_seconds = 60 * 5  # 5 minutes

    def _is_cache_expired(self):
        return self._cache_date and (timezone.now() - self._cache_date).total_seconds() > self._cache_expiration_seconds

    @property
    def json_schema(self):
        if not self._json_schema or self._is_cache_expired():
            self._json_schema = self.get_json_schema()
            self._cache_date = timezone.now()
        return self._json_schema

    def json_schema_fn(self):
        return self.json_schema

    @classmethod
    def get_field_type_from_os_type(cls, os_type):
        """
        Convert OpenSearch type to jsonschema type + format
        """
        if os_type == OSFieldType.TEXT:
            return AttributesFieldType.STRING, None
        if os_type == OSFieldType.DATE:
            return AttributesFieldType.STRING, AttributesFieldStringFormat.DATE
        if os_type == OSFieldType.DOUBLE:
            return AttributesFieldType.NUMBER, None
        if os_type == OSFieldType.LONG:
            return AttributesFieldType.INTEGER, None
        if os_type == OSFieldType.BOOLEAN:
            return AttributesFieldType.BOOLEAN, None
        raise ValueError(f'Unsupported OS type: "{os_type}"')

    @classmethod
    def get_os_type(cls, field_type, string_format=None, array_type=None):
        """
        Convert jsonschema type to OpenSearch type
        """
        if array_type:
            # if it's an array, we're only interested in the type of the items
            field_type = array_type

        if field_type == AttributesFieldType.STRING:
            if string_format in [AttributesFieldStringFormat.DATE_TIME, AttributesFieldStringFormat.DATE]:
                return OSFieldType.DATE
            return OSFieldType.TEXT
        if field_type == AttributesFieldType.NUMBER:
            return OSFieldType.DOUBLE
        if field_type == AttributesFieldType.INTEGER:
            return OSFieldType.LONG
        if field_type == AttributesFieldType.BOOLEAN:
            return OSFieldType.BOOLEAN
        raise ValueError(f'Unsupported OS type: "{field_type}" with format "{string_format}"')

    def get_os_type_for_field_name(self, field_name):
        field = self.json_schema["properties"].get(field_name)
        if not field:
            raise AttributesFieldNotFoundError(f'Field "{field_name}" not found in schema')
        return self.get_os_type(
            field_type=field["type"],
            string_format=field.get("format"),
            array_type=field.get("items", {}).get("type"),
        )

    def invalidate_cache(self):
        self._json_schema = None
        self._cache_date = None

    def get_json_schema(self):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "dataroom-image-attributes",
            "type": "object",
            "properties": {field.name: field.json_schema for field in AttributesField.objects.filter(is_enabled=True)},
            "required": [field.name for field in AttributesField.objects.filter(is_enabled=True, is_required=True)],
            "additionalProperties": False,  # do not allow any other fields
        }

    def validate_json(self, data):
        """Will raise jsonschema.ValidationError if data is invalid"""
        schema = self.json_schema
        jsonschema.validate(
            instance=data,
            schema=schema,
            format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
        )

    def validate_json_partial(self, data):
        """Validates the data against the schema, but does not require all required fields"""
        schema = dict(self.json_schema)
        schema["required"] = []  # remove required fields
        jsonschema.validate(
            instance=data,
            schema=schema,
            format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
        )


AttributesSchema = AttributesSchemaClass()
