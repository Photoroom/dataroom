import jsonschema
from django.conf import settings
from pgvector.django import VectorField
from rest_framework import serializers
from rest_framework.fields import CharField

from backend.common.validators import AlphanumericValidator, NormalizedVectorValidator, VectorRegexValidator
from backend.dataroom.models.attributes import AttributesFieldNotFoundError, AttributesSchema
from backend.dataroom.models.os_image import OSAttribute, OSImage, OSImageDatasets, RelatedOSImages


class ImageIdField(CharField):
    def __init__(self, **kwargs):
        kwargs['min_length'] = settings.IMAGE_ID_MIN_LENGTH
        kwargs['max_length'] = settings.IMAGE_ID_MAX_LENGTH
        super().__init__(**kwargs)
        self.validators.append(AlphanumericValidator())


class LatentTypeField(CharField):
    def __init__(self, **kwargs):
        kwargs['min_length'] = settings.LATENT_TYPE_MIN_LENGTH
        kwargs['max_length'] = settings.LATENT_TYPE_MAX_LENGTH
        super().__init__(**kwargs)
        self.validators.append(AlphanumericValidator())


class AttributesJSONField(serializers.JSONField):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        try:
            AttributesSchema.validate_json(data=data)
        except jsonschema.ValidationError as e:
            raise serializers.ValidationError(f'Schema validation error: {e.message}') from e
        return data


class AttributesPartialJSONField(serializers.JSONField):
    """Does not require all fields to be present, but validates the ones that are present."""

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        try:
            AttributesSchema.validate_json_partial(data=data)
        except jsonschema.ValidationError as e:
            raise serializers.ValidationError(f'Schema validation error: {e.message}') from e
        return data


class RelatedOSImagesField(serializers.DictField):
    child = ImageIdField(required=True)

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        try:
            return RelatedOSImages.from_json(data)
        except ValueError as e:
            raise serializers.ValidationError(str(e)) from e


class CocaEmbeddingVectorField(serializers.ModelField):
    def __init__(self, **kwargs):
        super().__init__(model_field=VectorField(dimensions=768), **kwargs)
        self.validators.append(VectorRegexValidator())
        self.validators.append(NormalizedVectorValidator())

    def run_validation(self, *args, **kwargs):
        try:
            return super().run_validation(*args, **kwargs)
        except ValueError as e:
            raise serializers.ValidationError('Invalid vector') from e


class OSImageOrAttributeField(serializers.CharField):
    def to_internal_value(self, value):
        value = super().to_internal_value(value)

        if value.startswith('attributes.'):
            attr_name = value.split('.')[1]
            try:
                os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
                is_indexed = AttributesSchema.get_is_indexed_for_field_name(attr_name)
            except AttributesFieldNotFoundError as e:
                raise serializers.ValidationError(f'Field "{value}" not found in attributes schema') from e
            else:
                attr = OSAttribute(name=attr_name, value=None, os_type=os_type, is_indexed=is_indexed)
                return attr.os_name_keyword
        elif value not in OSImage.all_class_fields:
            raise serializers.ValidationError(f'"{value}" is not a valid field')
        return value


class OSImageDatasetsField(serializers.ListField):
    child = serializers.CharField(required=True)

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        for dataset in data:
            try:
                _ = dataset.split('/')
            except ValueError as e:
                raise serializers.ValidationError(f'Invalid dataset: {dataset}') from e
        return OSImageDatasets.from_json(data)
