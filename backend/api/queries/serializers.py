from rest_framework import serializers

from backend.api.images.filters import compile_filters
from backend.api.users.serializers import UserSerializer
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.query import Query


class QuerySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    # The stored source filters live in the `query_dict` column, exposed as `filters`.
    # Read-only: filters are only ever set via QueryCreateUpdateSerializer's validated input.
    filters = serializers.JSONField(source='query_dict', read_only=True)

    class Meta:
        model = Query
        fields = (
            'slug',
            'name',
            'description',
            'author',
            'filters',
        )
        read_only_fields = (
            'slug',
            'author',
        )


class QueryCreateUpdateSerializer(serializers.ModelSerializer):
    # Stored verbatim in query_dict and compiled on demand. Accepts flat OSImageFilterSet
    # params or the query builder's multi-lane shape ({filter_lanes: [...]}), validated by
    # compiling in validated_filters.
    filters = serializers.JSONField(required=False)

    class Meta:
        model = Query
        fields = (
            'slug',
            'name',
            'description',
            'filters',
        )

    def validate_slug(self, value):
        if self.instance and self.instance.pk and self.instance.slug == value:
            return value
        if Query.objects.filter(slug=value).exists():
            raise serializers.ValidationError(f'Query with slug "{value}" already exists')
        return value

    def validated_filters(self, filters):
        # A saved query may not embed another query (would recurse at compile time).
        if isinstance(filters, dict) and 'query' in filters:
            raise serializers.ValidationError({'filters': 'Nested "query" filters are not allowed.'})
        # Compile once to validate. We store the filters, not the result.
        compile_filters(filters, OSImage.objects.search(), self.context.get('request'))
        return filters

    def create(self, validated_data):
        filters = self.validated_filters(validated_data.get('filters', {}))
        query = Query.objects.create(
            slug=validated_data['slug'],
            name=validated_data['name'],
            # description is optional (blank=True on the model), default to ''.
            description=validated_data.get('description', ''),
            author=self.context['request'].user,
            # query_dict holds the source filters (compiled to OpenSearch on demand).
            query_dict=filters,
        )
        return query

    def update(self, instance, validated_data):
        if 'slug' in validated_data:
            instance.slug = validated_data['slug']
        if 'name' in validated_data:
            instance.name = validated_data['name']
        if 'description' in validated_data:
            instance.description = validated_data['description']
        if 'filters' in validated_data:
            instance.query_dict = self.validated_filters(validated_data['filters'])
        instance.save()
        return instance
