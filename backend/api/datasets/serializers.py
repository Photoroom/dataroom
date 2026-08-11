from rest_framework import serializers

from backend.api.groups.serializers import batch_cover_thumbnails, resolve_cover_thumbnail
from backend.api.images.fields import ImageIdField
from backend.api.users.serializers import UserSerializer
from backend.dataroom.models.dataset import (
    DATASET_UPDATE_GROUPS_LIMIT,
    Dataset,
    DatasetMembership,
)
from backend.dataroom.models.group import Group, GroupType


def batch_dataset_covers(datasets):
    """{dataset_id: thumbnail_url} for a page of datasets.

    A dataset's cover is its earliest active member group's cover image — "the
    first group's picture". DISTINCT ON (dataset_id) with a matching order_by
    gives that one first group per dataset; ``batch_cover_thumbnails`` then turns
    those groups into urls (1 PG + 1 OS query), so the list needs no per-card
    fetch (mirrors GroupViewSet.list).
    """
    dataset_ids = [d.id for d in datasets]
    if not dataset_ids:
        return {}
    first_memberships = list(
        DatasetMembership.objects.filter(
            dataset_id__in=dataset_ids, deleted_at__isnull=True, group__deleted_at__isnull=True
        )
        .order_by('dataset_id', 'date_created')
        .distinct('dataset_id')
        .select_related('group')
    )
    group_covers = batch_cover_thumbnails([m.group for m in first_memberships])
    return {m.dataset_id: group_covers.get(m.group_id) for m in first_memberships}


class DatasetSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    # Rendered as the GroupType name. Read-only here, so PUT/PATCH can never
    # change the dataset's type — the immutability guarantee.
    type = serializers.SlugRelatedField(slug_field='name', read_only=True)
    group_count = serializers.SerializerMethodField()
    # The first member group's cover image — batched by DatasetViewSet.list.
    cover_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = (
            'slug_version',
            'slug',
            'version',
            'name',
            'type',
            'author',
            'group_count',
            'description',
            'is_frozen',
            'cover_image_id',
            'cover_thumbnail',
            'date_created',
            'date_updated',
        )
        read_only_fields = (
            'slug_version',
            'slug',
            'version',
            'type',
            'author',
            'group_count',
            'cover_thumbnail',
            'date_created',
            'date_updated',
        )

    def get_group_count(self, obj) -> int:
        # DatasetViewSet.get_queryset annotates group_count; fall back to a
        # live PG count for un-annotated instances (e.g. the create response).
        count = getattr(obj, 'group_count', None)
        if count is not None:
            return count
        return obj.memberships.filter(deleted_at__isnull=True).count()

    def get_cover_thumbnail(self, obj) -> str | None:
        # List passes a batched {dataset_id: url} map via context; for a single
        # instance (retrieve/create) fall back to resolving the first group once.
        cover_map = self.context.get('cover_thumbnails')
        if cover_map is not None:
            return cover_map.get(obj.id)
        first_group = (
            Group.objects.filter(
                dataset_memberships__dataset=obj,
                dataset_memberships__deleted_at__isnull=True,
                deleted_at__isnull=True,
            )
            .order_by('dataset_memberships__date_created')
            .first()
        )
        return resolve_cover_thumbnail(first_group) if first_group else None

    def validate(self, attrs):
        # `type` is read_only on update, so DRF would otherwise *silently drop*
        # a `type` in the body — a client trying to change it would get a 200
        # and no change. Detect the attempt in the raw payload and 400 instead,
        # but allow a no-op round-trip (PUT echoing back the current type).
        if self.instance is not None and 'type' in self.initial_data:
            requested = self.initial_data['type']
            if requested != self.instance.type_id:
                raise serializers.ValidationError(
                    {'type': "A dataset's type is immutable and cannot be changed after creation."}
                )
        return super().validate(attrs)


class DatasetCreateSerializer(DatasetSerializer):
    # type is writable only at creation, then read-only forever after.
    type = serializers.SlugRelatedField(slug_field='name', queryset=GroupType.objects.all())

    class Meta(DatasetSerializer.Meta):
        read_only_fields = (
            'slug_version',
            'version',
            'author',
            'group_count',
            'date_created',
            'date_updated',
        )

    def validate(self, attrs):
        # A create against an existing slug makes a new *version*, not a new dataset.
        # Versioning is not a way around the type being immutable: every version of a
        # slug collects the same kind of Group. The model manager enforces this too;
        # catching it here turns it into a 400 rather than a 500.
        existing = Dataset.objects.filter(slug=attrs.get('slug')).order_by('-version').first()
        if existing and attrs.get('type') and attrs['type'].name != existing.type_id:
            raise serializers.ValidationError(
                {
                    'type': (
                        f"Dataset '{existing.slug}' is of type '{existing.type_id}'. Every version of a "
                        f"slug shares one type, so a new version cannot be '{attrs['type'].name}'. "
                        f'Use a different slug.'
                    )
                }
            )
        return super().validate(attrs)

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class DatasetMemberSerializer(serializers.Serializer):
    """A member Group as it appears inside a Dataset listing."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    type = serializers.CharField(source='type_id')
    cover_thumbnail = serializers.SerializerMethodField()

    def get_cover_thumbnail(self, obj) -> str | None:
        # The groups action builds a {group_id: thumbnail_url} map for the page
        # in one OS query and passes it via context; fall back to one fetch.
        cover_map = self.context.get('cover_thumbnails')
        if cover_map is not None:
            return cover_map.get(obj.id)
        return resolve_cover_thumbnail(obj)


class DatasetGroupsSerializer(serializers.Serializer):
    """Response for GET .../groups/: one cursor page of active member groups.

    No `group_count`: cursor pagination does not count, and the dataset already
    carries the number (GET /datasets/<slug>/<version>/ annotates `group_count`).
    """

    next = serializers.CharField(required=True, allow_null=True)
    previous = serializers.CharField(required=True, allow_null=True)
    results = DatasetMemberSerializer(many=True)


class DatasetUpdateGroupsSerializer(serializers.Serializer):
    group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=DATASET_UPDATE_GROUPS_LIMIT,
    )


class DatasetUpdateGroupsResponseSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()


class DatasetAddImagesSerializer(serializers.Serializer):
    """POST .../images/ body: images to wrap in single_image groups and add."""

    image_ids = serializers.ListField(
        child=ImageIdField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=DATASET_UPDATE_GROUPS_LIMIT,
    )


class DatasetCopySerializer(serializers.Serializer):
    """Request body for POST .../copy/. The new dataset inherits the source's type."""

    name = serializers.CharField(max_length=100)
    slug = serializers.SlugField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default='')
