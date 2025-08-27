from rest_framework import serializers

from backend.dataroom.models import AttributesField, LatentType


class StatsDictSerializer(serializers.Serializer):
    current = serializers.IntegerField()
    date_updated = serializers.DateTimeField()
    prev = serializers.IntegerField()
    prev_date_updated = serializers.DateTimeField()
    change_per_second = serializers.IntegerField()
    time_left = serializers.IntegerField()


class TotalsSerializer(serializers.Serializer):
    images = StatsDictSerializer()


class QueueSerializer(serializers.Serializer):
    total_images = StatsDictSerializer()
    images_missing_thumbnail = StatsDictSerializer()
    images_missing_coca_embedding = StatsDictSerializer()
    images_missing_duplicate_state = StatsDictSerializer()
    images_marked_as_duplicates = StatsDictSerializer()
    images_marked_for_deletion = StatsDictSerializer()
    images_with_disabled_latents = StatsDictSerializer()


class AttributeFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributesField
        fields = ['name', 'field_type', 'string_format', 'is_enabled', 'is_indexed', 'image_count']


class LatentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LatentType
        fields = ['name', 'is_mask', 'image_count']
