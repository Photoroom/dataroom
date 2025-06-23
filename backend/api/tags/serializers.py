import re

from rest_framework import serializers

from backend.api.images.fields import ImageIdField
from backend.api.tags.fields import TagNameField
from backend.dataroom.models.tag import Tag

TAG_IMAGES_IMAGE_LIMIT = 1000
TAG_IMAGES_TAGS_LIMIT = 10


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            'id',
            'name',
            'description',
            'image_count',
        )
        read_only_fields = (
            'id',
            'image_count',
        )

    def validate_name(self, value):
        disallowed_chars = r'[^a-zA-Z0-9_-]'
        if re.search(disallowed_chars, value):
            raise serializers.ValidationError(
                'Tags can only contain alphanumeric characters, dashes, and underscores',
            )
        return value


class ImageIdsWithTagNamesSerializer(serializers.Serializer):
    image_ids = serializers.ListField(
        child=ImageIdField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=TAG_IMAGES_IMAGE_LIMIT,
    )
    tag_names = serializers.ListField(
        child=TagNameField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=TAG_IMAGES_TAGS_LIMIT,
    )


class TagImagesResponseSerializer(serializers.Serializer):
    tags_created = serializers.IntegerField()
    images_tagged = serializers.IntegerField()
