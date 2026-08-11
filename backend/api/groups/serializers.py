import jsonschema
from rest_framework import serializers

from backend.api.images.fields import ImageIdField
from backend.api.users.serializers import UserSerializer
from backend.dataroom.models.group import BULK_GROUPS_LIMIT, Group, GroupType, GroupTypeRole, Membership, Role
from backend.dataroom.models.os_image import OSImage


def _first_member_image_id(group_id):
    """Earliest active member's image_id, used as a cover fallback."""
    return (
        Membership.objects.filter(group_id=group_id, deleted_at__isnull=True)
        .order_by('date_created')
        .values_list('image_id', flat=True)
        .first()
    )


def resolve_cover_thumbnail(group):
    """Cover thumbnail URL for ONE group. Explicit cover_image_id, else the
    earliest member. Single OS fetch — use batch_cover_thumbnails for lists."""
    image_id = group.cover_image_id or _first_member_image_id(group.id)
    if not image_id:
        return None
    try:
        img = OSImage.objects.get(image_id, fields=['thumbnail', 'image'])
    except OSImage.DoesNotExist:
        return None
    return img.thumbnail_url or img.image_url


def _earliest_member_by_group(group_ids, role=None):
    """{group_id: image_id} of each group's earliest active member, in one PG
    query. DISTINCT ON (group_id) + matching order_by returns one row per group.
    """
    memberships = Membership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True)
    if role:
        memberships = memberships.filter(role=role)
    rows = memberships.order_by('group_id', 'date_created').distinct('group_id').values_list('group_id', 'image_id')
    return dict(rows)


def batch_cover_thumbnails(groups, cover_role=None):
    """{group_id: thumbnail_url} for a page of groups in 1 PG + 1 OS query.

    Resolves each group's cover image_id (explicit cover, else earliest active
    member) then fetches all those images from OS in a single terms query.

    With ``cover_role`` set, the explicit cover is ignored and every group
    resolves to its earliest active member holding that role; groups without
    such a member get no thumbnail (None) rather than a fallback, so the UI
    can show "this group has no <role> image" honestly.
    """
    group_to_image = {}
    remaining = list(groups)
    if cover_role:
        group_to_image = _earliest_member_by_group([g.id for g in remaining], role=cover_role)
        remaining = []

    # Default chain for whatever's left: explicit cover, else earliest member.
    no_cover = []
    for g in remaining:
        if g.cover_image_id:
            group_to_image[g.id] = g.cover_image_id
        else:
            no_cover.append(g.id)
    if no_cover:
        group_to_image.update(_earliest_member_by_group(no_cover))

    image_ids = list(set(group_to_image.values()))
    if not image_ids:
        return {}

    # One OS query fetches every cover image for the page.
    result = (
        OSImage.objects.search(fields=['thumbnail', 'image'])
        .filter('terms', id=image_ids)
        .extra(size=len(image_ids))
        .execute()
    )
    url_by_image = {img.id: (img.thumbnail_url or img.image_url) for img in OSImage.list_from_hits(result.hits.hits)}

    return {gid: url_by_image.get(image_id) for gid, image_id in group_to_image.items()}


class RoleSerializer(serializers.ModelSerializer):
    # Which GroupTypes declare this role (via the through table, prefetched by the
    # viewset), and how many active groups actually hold a membership with it
    # (annotated by the viewset). Mirrors the roles/has_role filter duality on the
    # groups list: declared vs. actually used.
    group_types = serializers.SerializerMethodField()
    group_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Role
        fields = ('name', 'description', 'group_types', 'group_count')

    def get_group_types(self, obj) -> list[str]:
        return sorted(tr.group_type_id for tr in obj.type_roles.all())


class GroupTypeRoleNestedSerializer(serializers.Serializer):
    """Nested representation of a (role, is_required) pair on a GroupType.

    The role must already exist in the Role table — create roles via
    ``POST /roles/`` before declaring a GroupType that references them.
    """

    role = serializers.SlugRelatedField(slug_field='name', queryset=Role.objects.all())
    is_required = serializers.BooleanField(default=False)


class GroupTypeSerializer(serializers.ModelSerializer):
    # ``roles`` is the writable nested list of {role, is_required} pairs. Reads
    # return the same shape from the GroupTypeRole through-table.
    roles = GroupTypeRoleNestedSerializer(source='type_roles', many=True, required=False)
    # Active groups of this type. Annotated by GroupTypeViewSet.get_queryset;
    # falls back to 0 for a freshly created type (create response isn't annotated).
    group_count = serializers.SerializerMethodField()

    class Meta:
        model = GroupType
        fields = ('name', 'description', 'metadata_schema', 'roles', 'group_count', 'date_created', 'date_updated')
        read_only_fields = ('date_created', 'date_updated')

    def get_group_count(self, obj) -> int:
        return getattr(obj, 'group_count', 0)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Override the nested 'roles' to use the through-table values directly.
        data['roles'] = [{'role': tr.role_id, 'is_required': tr.is_required} for tr in instance.type_roles.all()]
        return data

    def _apply_roles(self, group_type, roles_data):
        # Replace the full set of GroupTypeRole rows. Roles must already exist
        # in the Role table; SlugRelatedField has resolved the names to instances.
        group_type.type_roles.all().delete()
        for r in roles_data:
            GroupTypeRole.objects.create(
                group_type=group_type,
                role=r['role'],
                is_required=r.get('is_required', False),
            )

    def create(self, validated_data):
        roles_data = validated_data.pop('type_roles', [])
        gt = GroupType.objects.create(**validated_data)
        self._apply_roles(gt, roles_data)
        return gt

    # No update(): GroupTypes are immutable — the viewset rejects PUT/PATCH.


class GroupSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    image_count = serializers.SerializerMethodField()
    cover_thumbnail = serializers.SerializerMethodField()
    # Type is exposed as the GroupType.name string both ways. The FK handles
    # existence validation; we only need to add the immutable + metadata-schema
    # checks below.
    type = serializers.SlugRelatedField(slug_field='name', queryset=GroupType.objects.all())

    class Meta:
        model = Group
        fields = (
            'id',
            'name',
            'type',
            'description',
            'cover_image_id',
            'cover_thumbnail',
            'metadata',
            'author',
            'image_count',
            'date_created',
            'date_updated',
        )
        read_only_fields = (
            'author',
            'image_count',
            'cover_thumbnail',
            'date_created',
            'date_updated',
        )

    def get_image_count(self, obj) -> int:
        # Callers must annotate image_count on the queryset (see
        # GroupViewSet.get_queryset and the bulk-attach in /images/{id}/groups);
        # distinct images, not membership rows, excluding soft-deletes.
        return obj.image_count

    def get_cover_thumbnail(self, obj):
        # The list endpoint builds a {group_id: thumbnail_url} map for the whole
        # page in one OS query and passes it via context (see
        # GroupViewSet.list) — so this is O(1) per group there. For single-object
        # responses (retrieve / PUT) there's no map, so fall back to one fetch.
        cover_map = self.context.get('cover_thumbnails')
        if cover_map is not None:
            return cover_map.get(obj.id)
        return resolve_cover_thumbnail(obj)

    def validate(self, data):
        # No existing group means we're making a new one
        creating = self.instance is None

        if creating:
            # New group: use whatever type the user provided. The SlugRelatedField
            # already checked it exists and resolved it to a GroupType object.
            group_type = data['type']
        else:
            # Editing: the type can't change. Reject a different one; otherwise
            # keep the type already saved.
            if 'type' in data and data['type'] != self.instance.type:
                raise serializers.ValidationError({'type': 'type is immutable'})
            group_type = self.instance.type

        # Pick which metadata to validate: the one in the request if present.
        # If the request has no metadata, fall back to {} for a new group, or
        # the group's already-saved metadata when editing.
        metadata = data.get('metadata', {} if creating else self.instance.metadata)
        # The type defines a JSON Schema; the metadata must match it. A type
        # with no schema for metadata (None) accepts anything as metadata.
        try:
            jsonschema.validate(metadata, group_type.metadata_schema or {})
        except jsonschema.ValidationError as e:
            raise serializers.ValidationError({'metadata': e.message}) from e

        return data


class MembershipSerializer(serializers.ModelSerializer):
    """Read-only output shape for memberships. Writes go through the bulk PUT."""

    image_id = ImageIdField()
    role = serializers.CharField(max_length=64)

    class Meta:
        model = Membership
        fields = (
            'id',
            'image_id',
            'role',
            'metadata',
            'date_created',
            'date_updated',
        )
        read_only_fields = fields


class PaginatedMembershipSerializer(serializers.Serializer):
    """Cursor page of a group's memberships (GET /groups/{id}/members/)."""

    next = serializers.CharField(required=False, allow_null=True)
    previous = serializers.CharField(required=False, allow_null=True)
    results = MembershipSerializer(many=True)


class GroupBulkDeleteSerializer(serializers.Serializer):
    """POST /groups/bulk-delete/ body. Unknown or already-deleted ids are ignored, so the
    cap is on what one request may carry, not on how many must exist."""

    group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        allow_empty=False,
        min_length=1,
        max_length=BULK_GROUPS_LIMIT,
    )


class GroupBulkDeleteResponseSerializer(serializers.Serializer):
    deleted_count = serializers.IntegerField()
