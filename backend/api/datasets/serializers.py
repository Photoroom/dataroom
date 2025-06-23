from rest_framework import serializers

from backend.api.images.fields import ImageIdField
from backend.api.users.serializers import UserSerializer
from backend.dataroom.models.dataset import DATASET_UPDATE_IMAGES_LIMIT, Dataset


class DatasetSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Dataset
        fields = (
            'slug_version',
            'slug',
            'version',
            'name',
            'author',
            'image_count',
            'description',
            'is_frozen',
        )
        read_only_fields = (
            'slug_version',
            'slug',
            'version',
            'author',
            'image_count',
        )


class DatasetCreateSerializer(DatasetSerializer):
    class Meta:
        model = Dataset
        fields = (
            'slug',
            'version',
            'name',
            'author',
            'image_count',
            'description',
            'is_frozen',
        )
        read_only_fields = (
            'slug_version',
            'version',
            'author',
            'image_count',
        )

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class DatasetPreviewImageSerializer(serializers.Serializer):
    id = ImageIdField(required=True)
    image = serializers.CharField(required=False)
    thumbnail = serializers.CharField(required=False, allow_null=True)


class DatasetPreviewImagesSerializer(serializers.Serializer):
    image_count = serializers.IntegerField()
    preview_images = DatasetPreviewImageSerializer(many=True)


class DatasetUpdateImagesResponseSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()


class DatasetUpdateImagesSerializer(serializers.Serializer):
    image_ids = serializers.ListField(
        child=ImageIdField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=DATASET_UPDATE_IMAGES_LIMIT,
    )
