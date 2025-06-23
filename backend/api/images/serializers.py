import httpx
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from backend.api.images.fields import (
    AttributesJSONField,
    AttributesPartialJSONField,
    CocaEmbeddingVectorField,
    ImageIdField,
    LatentTypeField,
    OSImageDatasetsField,
    OSImageOrAttributeField,
    RelatedOSImagesField,
)
from backend.api.pagination import API_MAX_PAGE_SIZE, API_PAGE_SIZE
from backend.api.tags.fields import TagNameField
from backend.dataroom.models.os_image import OSAttributes, OSImage
from backend.dataroom.utils.download_image import download_image_from_url


class OSImageLatentSerializer(serializers.Serializer):
    latent_type = LatentTypeField(required=True)
    file_direct_url = serializers.CharField(required=False)
    is_mask = serializers.BooleanField(required=False)


class OSImageCocaEmbeddingSerializer(serializers.Serializer):
    vector = serializers.ListField(child=serializers.FloatField(), required=False, allow_null=True)
    author = serializers.CharField(required=False, allow_null=True)


class OSImageSerializer(serializers.Serializer):
    id = ImageIdField(required=True)
    source = serializers.CharField(required=False)
    image = serializers.CharField(required=False)
    image_direct_url = serializers.CharField(required=False)
    date_created = serializers.DateTimeField(required=False)
    date_updated = serializers.DateTimeField(required=False)
    author = serializers.CharField(required=False)
    image_hash = serializers.CharField(required=False)
    width = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True)
    short_edge = serializers.IntegerField(required=False, allow_null=True)
    pixel_count = serializers.IntegerField(required=False, allow_null=True)
    aspect_ratio = serializers.FloatField(required=False, allow_null=True)
    aspect_ratio_fraction = serializers.CharField(required=False, allow_null=True)
    thumbnail = serializers.CharField(required=False, allow_null=True)
    thumbnail_direct_url = serializers.CharField(required=False, allow_null=True)
    thumbnail_error = serializers.BooleanField(required=False, allow_null=True)
    original_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tags = serializers.ListField(child=TagNameField(), required=False, allow_empty=True)
    coca_embedding = OSImageCocaEmbeddingSerializer(required=False, allow_null=True)
    latents = OSImageLatentSerializer(required=False, many=True)
    attributes = serializers.JSONField(required=False)
    duplicate_state = serializers.IntegerField(required=False, allow_null=True)
    related_images = RelatedOSImagesField(required=False, allow_null=True)
    datasets = OSImageDatasetsField(required=False, allow_null=True)


@extend_schema_serializer(many=False)
class PaginatedOSImageSerializer(serializers.Serializer):
    next = serializers.CharField(required=True, allow_null=True)
    results = OSImageSerializer(required=True, many=True)


class CountSerializer(serializers.Serializer):
    count = serializers.IntegerField(required=True)


class SimilarOSImageSerializer(OSImageSerializer):
    similarity = serializers.FloatField(required=True)


class SimilarOSImageListSerializer(serializers.ListSerializer):
    child = SimilarOSImageSerializer()


class RelatedOSImageSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    image_id = serializers.CharField(required=True)
    image = OSImageSerializer(required=False, allow_null=True)


class RelatedOSImageListSerializer(serializers.ListSerializer):
    child = RelatedOSImageSerializer()


class OSImageSegmentationSerializer(serializers.Serializer):
    captions = serializers.ListField(child=serializers.CharField(), required=True)
    segments = serializers.ListField(child=serializers.ListField(child=serializers.IntegerField()), required=True)


class RetrieveOSImageParamsSerializer(serializers.Serializer):
    fields = serializers.CharField(
        required=False,
        help_text='You can specify the exact fields with ?fields=id,image',
    )
    all_fields = serializers.BooleanField(
        required=False,
        help_text='Return all available fields with ?all_fields=true',
    )
    include_fields = serializers.CharField(
        required=False,
        help_text='Include fields that are not there by default with ?include_fields=image,thumbnail',
    )
    exclude_fields = serializers.CharField(
        required=False,
        help_text='Exclude fields that are there by default with ?exclude_fields=thumbnail',
    )
    return_latents = serializers.CharField(
        required=False,
        help_text='Return specific latents only with ?return_latents=latent_type',
    )

    def get_fields_list(self):
        available_api_fields = OSImage.available_api_fields
        default_api_fields = OSImage.default_api_fields

        # ?fields is specified manually
        if self.validated_data.get('fields'):
            fields = ['id']  # always include id
            for field in self.validated_data['fields'].split(','):
                if field in available_api_fields and field not in fields:
                    fields.append(field)
            return fields

        # all fields
        if self.validated_data.get('all_fields'):
            return list(available_api_fields)

        # if ?fields is not specified, use default fields
        fields = list(default_api_fields)

        # include
        if self.validated_data.get('include_fields'):
            for field in self.validated_data['include_fields'].split(','):
                if field in available_api_fields and field not in fields:
                    fields.append(field)

        # exclude
        if self.validated_data.get('exclude_fields'):
            for field in self.validated_data['exclude_fields'].split(','):
                if field != 'id' and field in fields:
                    fields.remove(field)

        return fields

    def get_latents_list(self):
        if 'return_latents' in self.validated_data:
            return self.validated_data['return_latents'].split(',')
        return None


class ListOSImageParamsSerializer(RetrieveOSImageParamsSerializer):
    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=API_MAX_PAGE_SIZE,
        default=API_PAGE_SIZE,
        help_text="The number of images to return per page.",
    )
    cursor = serializers.CharField(required=False)

    def get_page_size(self):
        return min(self.validated_data.get('page_size', API_PAGE_SIZE), API_MAX_PAGE_SIZE)

    def get_search_after(self):
        cursor = self.validated_data.get('cursor')
        if cursor:
            return [cursor]


class RandomOSImageParamsSerializer(RetrieveOSImageParamsSerializer):
    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=API_MAX_PAGE_SIZE,
        default=API_PAGE_SIZE,
        help_text="The number of images to return per page.",
    )
    prefix_length = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=64,
        default=5,
        help_text="Filter image_hash by a number of random prefixes. "
        "A smaller prefix_length will give you more samples, but less random.",
    )
    num_prefixes = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=300,
        default=100,
        help_text="Filter image_hash by a number of random prefixes. "
        "A higher num_prefixes will give you more samples, but slow down the query.",
    )

    def get_page_size(self):
        return min(self.validated_data.get('page_size', API_PAGE_SIZE), API_MAX_PAGE_SIZE)

    def get_prefix_length(self):
        return self.validated_data.get('prefix_length', 5)

    def get_num_prefixes(self):
        return self.validated_data.get('num_prefixes', 100)


class SimilarOSImageParamsSerializer(RetrieveOSImageParamsSerializer):
    number = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)

    def get_number(self):
        return self.validated_data.get('number', 10)


class SimilarToOSImageParamsSerializer(RetrieveOSImageParamsSerializer):
    pass


class OSImageCreateSerializer(serializers.Serializer):
    id = ImageIdField(required=False)
    image = serializers.ImageField(write_only=True, required=False)
    image_url = serializers.URLField(write_only=True, required=False)
    source = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    attributes = AttributesJSONField(required=False)
    tags = serializers.ListField(child=TagNameField(), required=False, allow_empty=True, write_only=True)
    related_images = RelatedOSImagesField(required=False, allow_null=True)
    datasets = OSImageDatasetsField(required=False, allow_null=True)

    def validate(self, data):
        image = data.get('image', None)
        image_url = data.get('image_url', None)
        image_id = data.get('id', None)
        source = data.get('source', None)

        if not image and not image_url:
            raise serializers.ValidationError('Please provide either an "image" or "image_url" field')

        if not image_id and not image_url:
            raise serializers.ValidationError('Please provide either an "image_id" or "image_url" field')

        if not source:
            raise serializers.ValidationError('Please provide a "source" field')

        if image_url:
            del data['image_url']
            data['original_url'] = image_url
            try:
                data['image'] = download_image_from_url(image_url)
            except httpx.HTTPError as e:
                raise serializers.ValidationError('Unable to download image from URL') from e
            else:
                # if image_id is not provided, use the image hash as the image ID
                image_hash = OSImage.get_image_hash_without_prefix(data['image'])
                data['image_hash'] = OSImage.get_image_hash(data['image'], image_hash=image_hash)
                if not image_id:
                    data['id'] = image_hash

        return data

    def validate_datasets(self, value):
        valid_datasets = self.context.get('valid_datasets', [])
        invalid_datasets = []
        for dataset in value:
            if dataset not in valid_datasets:
                invalid_datasets.append(dataset)
        if invalid_datasets:
            raise serializers.ValidationError(f'Invalid datasets: {", ".join(invalid_datasets)}')
        return value

    def update(self, instance, validated_data):
        raise NotImplementedError('This serializer should not be used for updates')

    def create(self, validated_data, bulk_index=None):
        os_image = OSImage(
            id=validated_data['id'],
            image_file=validated_data['image'],
            source=validated_data['source'],
            author=validated_data['author'],
            attributes=OSAttributes.from_json(validated_data.get('attributes', None)),
            tags=validated_data.get('tags', None),
            image_hash=validated_data['image_hash'],
            original_url=validated_data['original_url'],
            related_images=validated_data.get('related_images', None),
            datasets=validated_data.get('datasets', None),
        )
        os_image.create(bulk_index=bulk_index)
        return os_image


class ImageLatentCreateSerializer(serializers.Serializer):
    latent_type = LatentTypeField(required=True)
    file = serializers.FileField(required=True)


class OSImageUpdateSerializer(serializers.Serializer):
    source = serializers.CharField(required=False, allow_null=False, allow_blank=False)
    attributes = AttributesJSONField(required=False)
    latents = ImageLatentCreateSerializer(required=False, many=True)
    tags = serializers.ListField(child=TagNameField(), required=False, allow_empty=True, write_only=True)
    coca_embedding = CocaEmbeddingVectorField(required=False, allow_null=False)
    related_images = RelatedOSImagesField(required=False, allow_null=True)
    datasets = OSImageDatasetsField(required=False, allow_null=True)

    def validate_datasets(self, value):
        valid_datasets = self.context.get('valid_datasets', [])
        value = list(set(value))
        invalid_datasets = []
        for dataset in value:
            if dataset not in valid_datasets:
                invalid_datasets.append(dataset)
        if invalid_datasets:
            raise serializers.ValidationError(f'Invalid datasets: {", ".join(invalid_datasets)}')
        return value


class OSImageBulkUpdateSerializer(OSImageUpdateSerializer):
    id = ImageIdField()


class ImageIdSerializer(serializers.Serializer):
    image_id = ImageIdField()


class ImageIdsSerializer(serializers.Serializer):
    image_ids = serializers.ListSerializer(child=ImageIdField())


class ImageAttributesSerializer(serializers.Serializer):
    attributes = AttributesPartialJSONField(required=True)


class ImageIdWithAttributesSerializer(serializers.Serializer):
    image_id = ImageIdField()
    attributes = AttributesPartialJSONField(required=True)


class NumberSerializer(serializers.Serializer):
    number = serializers.IntegerField(min_value=1, max_value=100)


class CocaEmbeddingSerializer(serializers.Serializer):
    vector = CocaEmbeddingVectorField(required=True, allow_null=False)


class SimilarToVectorSerializer(serializers.Serializer):
    vector = CocaEmbeddingVectorField(required=True, allow_null=False)
    number = serializers.IntegerField(min_value=1, max_value=100)


class SimilarToTextSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, allow_null=False, min_length=1, max_length=180)
    number = serializers.IntegerField(min_value=1, max_value=100)


class ImageLatentTypeSerializer(serializers.Serializer):
    latent_type = LatentTypeField(required=True)


class OSImageAggregateSerializer(serializers.Serializer):
    field = OSImageOrAttributeField(required=True)
    type = serializers.ChoiceField(
        required=True,
        choices=['avg', 'sum', 'min', 'max', 'value_count', 'cardinality', 'stats', 'percentiles'],
    )


class OSImageBucketSerializer(serializers.Serializer):
    field = OSImageOrAttributeField(required=True)
    size = serializers.IntegerField(required=True, min_value=1, max_value=1000)
