import uuid
from collections import defaultdict

import django_filters
import jsonschema
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from backend.api.groups.expand import GroupExpandParamsSerializer, expand_groups
from backend.api.groups.serializers import (
    GroupBulkDeleteResponseSerializer,
    GroupBulkDeleteSerializer,
    GroupSerializer,
    GroupTypeSerializer,
    MembershipSerializer,
    PaginatedMembershipSerializer,
    RoleSerializer,
    batch_cover_thumbnails,
)
from backend.dataroom.datasets.os_sync import recompute_datasets_for_images
from backend.dataroom.groups.os_sync import (
    add_group_entries_to_images,
    apply_delta_to_images,
    remove_groups_from_images,
    scrub_group_from_all_images,
)
from backend.dataroom.models.group import BULK_GROUPS_LIMIT, Group, GroupType, Membership, Role


class GroupTypeFilterSet(django_filters.FilterSet):
    name__prefix = django_filters.CharFilter(field_name='name', lookup_expr='istartswith')
    # CSV: ?required_roles=hero,thumbnail → all listed roles must be required on the type.
    required_roles = django_filters.BaseInFilter(method='_filter_required_roles')
    optional_roles = django_filters.BaseInFilter(method='_filter_optional_roles')
    # CSV: ?roles=hero,thumbnail → the type DECLARES all listed roles, required
    # or optional — the union a plain role selection in the UI means.
    roles = django_filters.BaseInFilter(method='_filter_declared_roles')

    class Meta:
        model = GroupType
        fields = ('name__prefix', 'required_roles', 'optional_roles', 'roles')

    def _filter_required_roles(self, queryset, name, value):
        # Empty value (?required_roles=) is a no-op, matching the convention
        # that an absent filter means "no filter." Use a different param if
        # you want "types with no required roles."
        if not value:
            return queryset
        return self._filter_roles_matching_all(queryset, value, is_required=True)

    def _filter_optional_roles(self, queryset, name, value):
        if not value:
            return queryset
        return self._filter_roles_matching_all(queryset, value, is_required=False)

    def _filter_declared_roles(self, queryset, name, value):
        if not value:
            return queryset
        # Distinct annotation name: this can combine with required_roles /
        # optional_roles, whose annotation is called `matched`.
        return queryset.annotate(
            declared=Count(
                'type_roles',
                filter=Q(type_roles__role__name__in=value),
                distinct=True,
            )
        ).filter(declared=len(value))

    @staticmethod
    def _filter_roles_matching_all(queryset, role_names, *, is_required):
        # "Type has ALL of these roles" via annotate+count, not N chained
        # JOINs — the old loop added one self-join on type_roles per role.
        return queryset.annotate(
            matched=Count(
                'type_roles',
                filter=Q(
                    type_roles__role__name__in=role_names,
                    type_roles__is_required=is_required,
                ),
                distinct=True,
            )
        ).filter(matched=len(role_names))


class GroupTypeViewSet(ModelViewSet):
    """Registry of group types and their allowed/required roles. Open to any
    authenticated dataroom user — the same permission gate that protects
    Group/Role writes.

    GroupTypes are immutable: a type's ``name`` is baked into the OS denorm
    encoding (``<name>::<uuid>``) of every group of that type, and its
    ``metadata_schema``/roles gate validation of those groups — editing any of
    it in place would silently invalidate existing data. So there is no PUT or
    PATCH; create a new type (and migrate) instead. DELETE is still allowed and
    is FK-PROTECTed against removing a type that has groups.
    """

    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    serializer_class = GroupTypeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = GroupTypeFilterSet
    ordering = ['name']  # PK is name, not id, so cursor pagination orders on it
    lookup_field = 'name'
    lookup_value_regex = r'[a-z0-9_]+'

    def get_queryset(self):
        # Annotate group_count (active groups of this type) as a correlated
        # SUBQUERY rather than a JOIN+Count. A join here would multiply rows
        # against the role-filter's Count('type_roles') annotation (cartesian
        # product, #groups x #roles per type) whenever ?required_roles/
        # ?optional_roles is applied; the subquery keeps it a cheap scalar.
        group_count = Coalesce(
            Subquery(
                Group.objects.filter(type=OuterRef('pk'), deleted_at__isnull=True)
                .order_by()
                .values('type')
                .annotate(c=Count('*'))
                .values('c'),
                output_field=IntegerField(),
            ),
            0,
        )
        return GroupType.objects.all().prefetch_related('type_roles__role').annotate(group_count=group_count)


class RoleViewSet(ModelViewSet):
    """Catalog of role names. Open to any authenticated dataroom user — anyone
    spinning up a new GroupType needs to be able to declare its roles, even
    if defining the GroupType itself is admin-only.
    """

    serializer_class = RoleSerializer

    def get_queryset(self):
        # group_count: distinct active groups with an active membership of this role.
        # Membership.role is a plain char column (not an FK), so the join is a
        # correlated subquery on the name - one query for the whole page, no N+1.
        used = (
            Membership.objects.filter(role=OuterRef('name'), deleted_at__isnull=True, group__deleted_at__isnull=True)
            .order_by()
            .values('role')
            .annotate(c=Count('group_id', distinct=True))
            .values('c')
        )
        return (
            Role.objects.all()
            .prefetch_related('type_roles')
            .annotate(group_count=Coalesce(Subquery(used, output_field=IntegerField()), 0))
        )

    filter_backends = [SearchFilter]
    search_fields = ['name', 'description']
    ordering = ['name']
    lookup_field = 'name'
    lookup_value_regex = r'[a-z0-9_]+'


class GroupFilterSet(django_filters.FilterSet):
    # Comma-separated to support multi-select on the frontend (?type=a,b,c).
    type = django_filters.BaseInFilter(field_name='type__name', lookup_expr='in')
    name__prefix = django_filters.CharFilter(field_name='name', lookup_expr='istartswith')
    # CSV: ?dataset=a/1,b/2 → groups that are active members of ANY listed dataset.
    dataset = django_filters.BaseInFilter(method='_filter_dataset')
    # CSV: ?roles=hero,thumbnail → groups whose TYPE declares all listed roles
    # (required OR optional — matches the roles images are actually assigned).
    # Cheap: the role match runs on the small GroupType tables, then groups are
    # filtered by their indexed type FK.
    roles = django_filters.BaseInFilter(method='_filter_roles')
    # CSV: ?has_role=hero,thumbnail → groups that actually have an active
    # membership for each listed role (vs. `roles`, which matches the type's
    # declared roles). Useful to find groups where images are really assigned.
    has_role = django_filters.BaseInFilter(method='_filter_has_role')

    class Meta:
        model = Group
        fields = ('type', 'author', 'name__prefix', 'dataset', 'roles', 'has_role')

    def _filter_dataset(self, queryset, name, value):
        if not value:
            return queryset
        # distinct: a group in several of the listed datasets matches once per
        # membership row otherwise.
        return queryset.filter(
            dataset_memberships__dataset__slug_version__in=value,
            dataset_memberships__deleted_at__isnull=True,
        ).distinct()

    def _filter_has_role(self, queryset, name, value):
        if not value:
            return queryset
        for role in value:
            queryset = queryset.filter(memberships__role=role, memberships__deleted_at__isnull=True)
        return queryset.distinct()

    def _filter_roles(self, queryset, name, value):
        if not value:
            return queryset
        # Resolve matching types in one query (single JOIN + count on the small
        # GroupType tables), then filter groups by their indexed type FK.
        types = (
            GroupType.objects.annotate(
                matched=Count(
                    'type_roles',
                    filter=Q(type_roles__role__name__in=value),
                    distinct=True,
                )
            )
            .filter(matched=len(value))
            .values('name')
        )
        return queryset.filter(type__in=types)


class GroupViewSet(ModelViewSet):
    """Groups are PUT-only on writes: ``PUT /api/groups/<uuid>/`` upserts,
    ``PATCH`` does partial scalar edits, ``DELETE`` soft-deletes. There is no
    POST — clients pick the UUID up front (typically a fresh UUID4) so PUT
    is the only write verb the API exposes.
    """

    # 'post' is enabled only for the bulk action below; the collection POST
    # (create) stays disabled - individual creates are PUT-to-a-chosen-UUID.
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    lookup_field = 'id'
    lookup_value_regex = r'[0-9a-f-]{32,36}'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = GroupFilterSet
    search_fields = ['name', 'id']
    ordering = ['-date_created']
    serializer_class = GroupSerializer

    def get_queryset(self):
        # Annotate image_count so the serializer doesn't fire a COUNT query
        # per group in list/retrieve responses (used to be N+1 on /api/groups/).
        return (
            Group.objects.filter(deleted_at__isnull=True)
            .select_related('author', 'type')
            .annotate(
                image_count=Count(
                    'memberships__image_id',
                    filter=Q(memberships__deleted_at__isnull=True),
                    distinct=True,
                )
            )
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'cover_role',
                str,
                description="Resolve each group's cover_thumbnail as its earliest active member "
                'holding this role, instead of the explicit cover / first member. Groups without '
                'a member in this role get a null cover_thumbnail.',
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        # Batch-resolve cover thumbnails for the whole page in one OS query and
        # hand the {group_id: url} map to the serializer via context. Without
        # this the serializer would fetch one cover per group (N+1).
        params = GroupExpandParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        opts = params.opts()

        cover_role = request.query_params.get('cover_role') or None
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        groups = page if page is not None else list(queryset)
        context = {
            **self.get_serializer_context(),
            'cover_thumbnails': batch_cover_thumbnails(groups, cover_role=cover_role),
        }
        data = self.get_serializer(groups, many=True, context=context).data
        # Merge optional roles + per-image data (group metadata is already on the
        # serializer). Batched: 1 PG + (<=1) OS query for the whole page.
        expanded = expand_groups(groups, opts)
        for item, group in zip(data, groups, strict=True):
            for key in ('roles', 'datasets'):
                if key in expanded[group.id]:
                    item[key] = expanded[group.id][key]

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        params = GroupExpandParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        opts = params.opts()

        group = self.get_object()
        data = self.get_serializer(group).data
        expanded = expand_groups([group], opts)[group.id]
        for key in ('roles', 'datasets'):
            if key in expanded:
                data[key] = expanded[key]
        return Response(data)

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        gid = group.os_encoded_id
        now = timezone.now()
        # Capture the images losing this group before we soft-delete, so we can
        # re-derive their dataset denorm once the group is gone.
        image_ids = list(
            group.memberships.filter(deleted_at__isnull=True).values_list('image_id', flat=True).distinct()
        )
        with transaction.atomic():
            group.deleted_at = now
            group.save(update_fields=['deleted_at', 'date_updated'])
            # os_synced=False so the reconciler can pick this up if the scrub
            # below fails — the group's memberships now need OS removal.
            group.memberships.filter(deleted_at__isnull=True).update(deleted_at=now, os_synced=False)
        # Scrub OS denorm after PG commit so a failure here doesn't leave PG
        # rolled back while OS still references the group. A deleted group can no
        # longer back any dataset membership, so its images' datasets must
        # be re-derived too (they may drop dataset slug_versions held via it).
        scrub_group_from_all_images(gid)
        recompute_datasets_for_images(image_ids)
        # All this group's memberships are now consistent with OS (scrubbed).
        group.memberships.update(os_synced=True)
        return Response(status=status.HTTP_204_NO_CONTENT)

    PATCH_ALLOWED_FIELDS = ('name', 'description', 'cover_image_id', 'metadata')

    def update(self, request, *args, **kwargs):
        """PUT acts as an upsert keyed on the URL UUID:
        - existing group at that UUID -> replace metadata + members atomically;
        - no group at that UUID       -> create it with that UUID + body.

        PATCH only edits the scalar fields in ``PATCH_ALLOWED_FIELDS``; any
        other key in the body is rejected. Members live exclusively on PUT.
        """
        if kwargs.get('partial'):
            extra = set(request.data.keys()) - set(self.PATCH_ALLOWED_FIELDS)
            if extra:
                raise serializers.ValidationError(
                    {
                        'detail': f"PATCH may only update {list(self.PATCH_ALLOWED_FIELDS)}; "
                        f"got disallowed key(s) {sorted(extra)}"
                    }
                )
            return super().update(request, *args, **kwargs)
        return self._upsert(kwargs[self.lookup_field], request)

    def _upsert(self, pk, request):
        # Two-phase: PG inside a transaction, then OS denorm sync. Splitting
        # them keeps OS round-trips off the row locks, and means a PG rollback
        # never leaves OS half-updated. OS failure after PG commit returns 500
        # but the touched rows stay os_synced=False for the periodic reconciler
        # to fix on its next pass.
        with transaction.atomic():
            group, os_delta, touched_pks, created = self._upsert_pg(pk, request)
        self._apply_os_delta(group, os_delta)
        # An image whose group membership changed may have gained/lost dataset
        # slug_versions (via this group's dataset memberships); re-derive
        # the datasets denorm for exactly those images. Part of the same OS sync
        # phase, so a failure here also leaves the rows os_synced=False.
        recompute_datasets_for_images(list(os_delta.keys()))
        # Inline OS sync succeeded — mark the touched rows synced so the
        # reconciler skips them. If we raise above, this line is unreached
        # and the rows stay False for the reconciler to pick up.
        if touched_pks:
            Membership.objects.filter(pk__in=touched_pks).update(os_synced=True)
        # Re-fetch through the annotated queryset so the response carries an
        # up-to-date image_count without the serializer firing a fallback
        # COUNT.
        group = self.get_queryset().get(pk=pk)
        response = Response(self.get_serializer(group).data)
        if created:
            response.status_code = status.HTTP_201_CREATED
        return response

    def _upsert_pg(self, pk, request):
        """PG side of the upsert. Returns (group, os_delta, touched_pks, created)."""
        # Look up across active *and* soft-deleted rows: a PUT to the UUID of a
        # tombstoned group should resurrect it, not collide on the PK.
        group = Group.objects.select_related('type').filter(pk=pk).first()
        created = False
        if group is None:
            # Create a new group with the URL-supplied UUID. Validate via the
            # standard serializer so name/type/metadata are checked, then save
            # with the explicit pk and author.
            serializer = GroupSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save(id=pk, author=request.user)
            group = Group.objects.select_related('type').get(pk=pk)
            created = True
        elif group.deleted_at is not None:
            # Resurrect: clear deleted_at; _bulk_replace_pg's save() below
            # writes it together with the other scalar updates (one UPDATE).
            group.deleted_at = None

        os_delta, touched_pks = self._bulk_replace_pg(group, request.data)
        return group, os_delta, touched_pks, created

    @staticmethod
    def _collect_errors(group, metadata, members):
        """Return a {field: message(s)} dict; explicit checks give better messages
        than the combined JSON Schema (which surfaces opaque `contains`/`enum` errors).
        """
        errors: dict = {}

        # Role-side: enum + required-roles checks split out by hand. One
        # query fetches both pieces; we split allowed/required in Python.
        type_roles = list(group.type.type_roles.values_list('role__name', 'is_required'))
        allowed = {n for n, _ in type_roles}
        required = {n for n, req in type_roles if req}
        present_roles = [m.get('role') for m in members]
        unknown = sorted({r for r in present_roles if r not in allowed})
        if unknown:
            errors['roles'] = f"unknown role(s) {unknown}; allowed: {sorted(allowed)}"
        missing = sorted(required - set(present_roles))
        if missing:
            errors['required_roles'] = f"missing required role(s) {missing}"

        # Metadata: jsonschema gives a clean path + message on its own.
        try:
            jsonschema.validate(metadata, group.type.metadata_schema or {})
        except jsonschema.ValidationError as e:
            path = '.'.join(str(p) for p in e.absolute_path) or '<root>'
            errors['metadata'] = f'{path}: {e.message}'

        return errors

    def _bulk_replace_pg(self, group, data):
        """PG-side of the bulk replace. Caller wraps in transaction.atomic.

        Returns a per-image ``{image_id: {'add': [roles], 'remove': [roles]}}``
        delta for the caller to push to the OS denorm after commit.
        """
        metadata = data.get('metadata', {})
        members = data.get('members', [])

        # Validate the shape before touching it: a malformed body must be a 400,
        # not a 500 from a KeyError/TypeError deeper down.
        if not isinstance(members, list) or not all(
            isinstance(m, dict) and 'image_id' in m and 'role' in m for m in members
        ):
            raise serializers.ValidationError({'members': 'must be a list of objects each with "image_id" and "role"'})

        errors = self._collect_errors(group, metadata, members)
        if errors:
            raise serializers.ValidationError(errors)

        # An image may hold several roles in one group, so the unit of
        # uniqueness is (image_id, role), not image_id.
        keys = [(m['image_id'], m['role']) for m in members]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError({'members': 'duplicate (image_id, role)'})

        # Apply scalar updates and persist with update_fields so unchanged
        # columns aren't rewritten. deleted_at is included because the
        # resurrect path in _upsert_pg sets it to None and relies on this
        # save to persist it.
        for f in ('name', 'description', 'cover_image_id'):
            if f in data:
                setattr(group, f, data[f])
        group.metadata = metadata
        group.save(
            update_fields=['name', 'description', 'cover_image_id', 'metadata', 'deleted_at', 'date_updated'],
        )

        # Diff against the full membership set (active + soft-deleted) keyed by
        # (image_id, role). Soft-deleted rows need to be in the dict so a
        # re-add is registered as an OS-side add — bulk_create's ON CONFLICT
        # below revives them in PG in the same query as the new inserts.
        #
        # Only the four fields we need: skip loading metadata/date_* etc. so
        # the row size stays small even for groups with many soft-deletes.
        existing = {
            (row['image_id'], row['role']): row
            for row in group.memberships.values('id', 'image_id', 'role', 'deleted_at')
        }
        new_keys = set(keys)

        delta: dict = defaultdict(lambda: {'add': [], 'remove': []})

        # Soft-delete currently-active memberships that aren't in the new set,
        # and record their (image_id, role) for OS removal. Rows stay around
        # so the reconciler can see them.
        drop_pks = []
        for (image_id, role), row in existing.items():
            if row['deleted_at'] is not None:
                continue
            if (image_id, role) not in new_keys:
                drop_pks.append(row['id'])
                delta[image_id]['remove'].append(role)
        if drop_pks:
            # os_synced=False so the reconciler will retry the OS removal if
            # the inline scrub below fails.
            Membership.objects.filter(pk__in=drop_pks).update(deleted_at=timezone.now(), os_synced=False)

        # Bulk upsert the new/kept memberships in one round trip. ON CONFLICT
        # on (group, image_id, role) updates metadata and clears deleted_at,
        # which revives soft-deleted rows in place (we can't insert a new row
        # because the unique constraint is unconditional). os_synced is reset
        # to False on both insert and update — the caller marks True after a
        # successful OS write.
        created_rows = []
        if members:
            created_rows = Membership.objects.bulk_create(
                [
                    Membership(
                        group=group,
                        image_id=m['image_id'],
                        role=m['role'],
                        metadata=m.get('metadata', {}),
                        deleted_at=None,
                        os_synced=False,
                    )
                    for m in members
                ],
                update_conflicts=True,
                unique_fields=['group', 'image_id', 'role'],
                update_fields=['metadata', 'deleted_at', 'date_updated', 'os_synced'],
            )

        # OS-side "add" = key was absent before OR was previously soft-deleted.
        # Metadata-only edits on an already-active row stay out of the delta.
        for m in members:
            prev = existing.get((m['image_id'], m['role']))
            if prev is None or prev['deleted_at'] is not None:
                delta[m['image_id']]['add'].append(m['role'])

        touched_pks = drop_pks + [m.pk for m in created_rows]
        return dict(delta), touched_pks

    @staticmethod
    def _apply_os_delta(group, delta):
        """Apply a per-image membership delta to the OS denorm. Idempotent.

        Buckets by the (add-set, remove-set) signature, NOT per-role: an image
        only ever lands in one bucket, which avoids the version-conflict race
        sequential per-role update_by_query calls would hit on multi-role
        images. A PUT that adds 'front' to 500 images becomes ONE call; even a
        heterogeneous PUT collapses to a handful.
        """
        if not delta:
            return
        gid = group.os_encoded_id

        # (add-tuple, remove-tuple) -> [image_id, ...]
        buckets = defaultdict(list)
        for image_id, ops in delta.items():
            key = (tuple(sorted(ops['add'])), tuple(sorted(ops['remove'])))
            buckets[key].append(image_id)

        for (add_roles, remove_roles), image_ids in buckets.items():
            apply_delta_to_images(image_ids, gid, add_roles, remove_roles)

    @extend_schema(responses=MembershipSerializer(many=True))
    def create(self, request, *args, **kwargs):
        # No collection POST: a group is created by PUT to a client-chosen UUID, or in
        # bulk via the action below. (POST is enabled on the class only for that action.)
        return Response(
            {'detail': 'Use PUT /groups/<uuid>/ to create one group, or POST /groups/bulk/ for many.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(
        request=GroupBulkDeleteSerializer,
        responses=GroupBulkDeleteResponseSerializer,
    )
    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Soft-delete up to BULK_GROUPS_LIMIT groups in one transaction + one OS write.

        The per-group DELETE is one HTTP round trip, one PG transaction and one
        update_by_query EACH - the same asymmetry bulk_create fixed on the way in, and
        the reason tearing down an import cost a round trip per group.

        POST, not DELETE, even though it deletes: the ids travel in the body, and
        drf-spectacular (like most OpenAPI tooling) does not emit a requestBody for
        DELETE - so a DELETE here would be a payload the schema never mentions, and no
        generated client could call it. POST keeps the contract honest.

        Two-phase, like every other write here: PG commits the soft-deletes with
        os_synced=False, then the OS write runs. If it raises, the rows stay False and
        the reconciler finishes the job.

        Ids that are unknown or already deleted are ignored rather than rejected, so a
        retry after a partial failure is safe.
        """
        serializer = GroupBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group_ids = serializer.validated_data['group_ids']

        groups = list(Group.objects.filter(id__in=group_ids, deleted_at__isnull=True))
        if not groups:
            return Response({'deleted_count': 0})

        ids = [g.id for g in groups]
        encoded_ids = [g.os_encoded_id for g in groups]
        # The images losing these groups, captured BEFORE the soft-delete hides the rows.
        image_ids = list(
            Membership.objects.filter(group_id__in=ids, deleted_at__isnull=True)
            .values_list('image_id', flat=True)
            .distinct()
        )

        now = timezone.now()
        with transaction.atomic():
            Group.objects.filter(id__in=ids).update(deleted_at=now, date_updated=now)
            Membership.objects.filter(group_id__in=ids, deleted_at__isnull=True).update(deleted_at=now, os_synced=False)

        # OS phase, after the PG commit. One bulk write strips every one of these groups
        # from every affected image; a deleted group can no longer back a dataset
        # membership either, so those images' datasets are re-derived.
        remove_groups_from_images(image_ids, encoded_ids)
        recompute_datasets_for_images(image_ids)
        Membership.objects.filter(group_id__in=ids).update(os_synced=True)

        return Response({'deleted_count': len(ids)})

    @extend_schema(
        request=None,
        responses=GroupSerializer(many=True),
        description='Create many groups in one request. Body: {"groups": [{name, type, '
        'metadata?, members?}, ...]}. Each group is created with a server-assigned UUID; '
        'the whole batch is one transaction and one OpenSearch write.',
    )
    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk_create(self, request):
        """Create up to BULK_GROUPS_LIMIT groups in one transaction + one OS write.

        The per-group PUT path is one HTTP round trip, one PG transaction and one OS
        write EACH - fine for a handful, hopeless for importing a whole source (tens of
        thousands). This collapses N groups into a few requests: bulk_create the Group
        and Membership rows, then a single bulk OS append keyed by image _id.
        """
        specs = request.data.get('groups')
        if not isinstance(specs, list) or not specs:
            raise serializers.ValidationError({'groups': 'must be a non-empty list'})
        if len(specs) > BULK_GROUPS_LIMIT:
            raise serializers.ValidationError({'groups': f'at most {BULK_GROUPS_LIMIT} groups per request'})

        # Validate every referenced type and its roles in ONE query, not per group.
        type_names = {spec.get('type') for spec in specs}
        types = {t.name: t for t in GroupType.objects.filter(name__in=type_names).prefetch_related('type_roles__role')}
        missing_types = sorted(n for n in type_names if n not in types)
        if missing_types:
            raise serializers.ValidationError({'type': f'unknown group type(s): {missing_types}'})
        roles_by_type = {name: {tr.role.name: tr.is_required for tr in t.type_roles.all()} for name, t in types.items()}

        errors = {}
        groups = []
        memberships = []
        entries_by_image = defaultdict(lambda: {'group_ids': [], 'memberships': []})
        for i, spec in enumerate(specs):
            type_name = spec.get('type')
            name = spec.get('name')
            metadata = spec.get('metadata', {})
            members = spec.get('members', [])
            if not name:
                errors[i] = {'name': 'required'}
                continue
            if not isinstance(members, list) or not all(
                isinstance(m, dict) and 'image_id' in m and 'role' in m for m in members
            ):
                errors[i] = {'members': 'must be a list of {image_id, role}'}
                continue

            allowed = set(roles_by_type[type_name])
            required = {r for r, req in roles_by_type[type_name].items() if req}
            present = [m['role'] for m in members]
            unknown = sorted({r for r in present if r not in allowed})
            missing = sorted(required - set(present))
            keys = [(m['image_id'], m['role']) for m in members]
            item_err = {}
            if unknown:
                item_err['roles'] = f'unknown role(s) {unknown}'
            if missing:
                item_err['required_roles'] = f'missing required role(s) {missing}'
            if len(set(keys)) != len(keys):
                item_err['members'] = 'duplicate (image_id, role)'
            try:
                jsonschema.validate(metadata, types[type_name].metadata_schema or {})
            except jsonschema.ValidationError as e:
                item_err['metadata'] = e.message
            if item_err:
                errors[i] = item_err
                continue

            gid = uuid.uuid4()
            group = Group(
                id=gid,
                name=name,
                type=types[type_name],
                description=spec.get('description', ''),
                metadata=metadata,
                author=request.user,
            )
            groups.append(group)
            encoded = f'{type_name}::{gid}'
            for m in members:
                memberships.append(Membership(group_id=gid, image_id=m['image_id'], role=m['role'], os_synced=False))
                e = entries_by_image[m['image_id']]
                if encoded not in e['group_ids']:
                    e['group_ids'].append(encoded)
                e['memberships'].append(f"{m['role']}::{encoded}")

        if errors:
            raise serializers.ValidationError({'groups': errors})

        with transaction.atomic():
            Group.objects.bulk_create(groups, batch_size=1000)
            if memberships:
                Membership.objects.bulk_create(memberships, batch_size=2000)

        # OS phase after the PG commit: one bulk append per <=1000 images. If it raises
        # the memberships stay os_synced=False for the reconciler.
        if entries_by_image:
            add_group_entries_to_images(dict(entries_by_image))
            Membership.objects.filter(group__in=groups, os_synced=False).update(os_synced=True)

        created = self.get_queryset().filter(id__in=[g.id for g in groups])
        cover = batch_cover_thumbnails(list(created))
        data = GroupSerializer(
            created, many=True, context={**self.get_serializer_context(), 'cover_thumbnails': cover}
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id='groups_members_list',
        responses=PaginatedMembershipSerializer,
        parameters=[
            OpenApiParameter('cursor', str, description='Opaque cursor from a previous page.'),
            OpenApiParameter('page_size', int, description='Memberships per page.'),
        ],
    )
    @action(detail=True, methods=['get'], url_path='members')
    def members(self, request, id=None):  # noqa: A002 (lookup_field='id')
        """Read-only listing of a group's memberships. All writes go through PUT."""
        group = self.get_object()
        qs = group.memberships.filter(deleted_at__isnull=True)
        page = self.paginate_queryset(qs)
        data = MembershipSerializer(page or qs, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)
