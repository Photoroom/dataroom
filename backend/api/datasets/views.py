from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from backend.api.datasets.serializers import (
    DatasetAddImagesSerializer,
    DatasetCopySerializer,
    DatasetCreateSerializer,
    DatasetGroupsSerializer,
    DatasetMemberSerializer,
    DatasetSerializer,
    DatasetUpdateGroupsResponseSerializer,
    DatasetUpdateGroupsSerializer,
    batch_dataset_covers,
)
from backend.api.groups.expand import GroupExpandParamsSerializer, expand_groups
from backend.api.groups.serializers import batch_cover_thumbnails
from backend.api.pagination import API_MAX_PAGE_SIZE, CustomCursorPagination
from backend.dataroom.datasets.os_sync import (
    append_dataset_to_images,
    recompute_datasets_for_groups,
)
from backend.dataroom.datasets.single_image import (
    SINGLE_IMAGE_TYPE,
    SingleImageGroupNameConflictError,
    add_images_to_dataset,
)
from backend.dataroom.models.dataset import Dataset, DatasetMembership, DatasetVersionTypeMismatchError
from backend.dataroom.models.group import Group, Membership


class DatasetGroupsPagination(CustomCursorPagination):
    """Cursor pages of a dataset's member Groups, newest first.

    `get_ordering` is overridden because the base class returns ``view.ordering``
    when the view has one, and DatasetViewSet orders Datasets by ``slug``/``-version``
    - fields a Group does not have. This sub-resource pages over Groups.
    """

    ordering = '-date_created'  # matches Group.Meta.ordering and its index

    def get_ordering(self, request, queryset, view):
        # ?order=asc flips to oldest-first — page one then starts at the
        # dataset's earliest member, i.e. its cover group.
        if request.query_params.get('order') == 'asc':
            return ('date_created',)
        return (self.ordering,)


def _changed_group_ids(dataset, group_ids):
    """The subset of group_ids whose membership in this dataset actually changed.

    ``os_synced=False`` already means exactly "Postgres moved and OpenSearch has not
    caught up", so it is the authoritative list of what needs writing - add_groups sets
    it on insert and revive, remove_groups on soft-delete. A group_id passed in with no
    unsynced row is one where nothing happened (re-adding a group that is already a
    member, removing one that was not one).

    Filtering on it matters more than it looks. A scripted update is a whole-document
    rewrite, and OpenSearch has to load the document's _source to even evaluate the
    script - so a write that turns out to be a no-op still costs the read. Where the
    index keeps its vectors on s3vector that read is a per-document S3 fetch, which
    means an idempotent re-add used to cost a full S3 round trip per image to write
    precisely nothing.
    """
    return list(
        DatasetMembership.objects.filter(dataset=dataset, group_id__in=group_ids, os_synced=False)
        .values_list('group_id', flat=True)
        .distinct()
    )


def _sync_dataset_groups(dataset, group_ids):
    """OS phase of a dataset<->group change: recompute ``datasets`` for every
    image in the affected groups, then mark those memberships os_synced=True.

    Runs after the PG commit (mirrors the group sync's two-phase design): if the
    OS write raises, the touched rows stay os_synced=False for the reconciler.

    Only the groups that actually changed are written - see _changed_group_ids.

    Synchronous, so a failure is a 500 the caller sees and the rows stay unsynced.
    Bounded by DATASET_UPDATE_GROUPS_LIMIT. Not for copy - see the async variant.
    """
    changed = _changed_group_ids(dataset, group_ids)
    if not changed:
        return
    recompute_datasets_for_groups(changed)
    DatasetMembership.objects.filter(dataset=dataset, group_id__in=changed).update(os_synced=True)


def _sync_dataset_copy(dataset, group_ids):
    """OS phase for a copy: every image in the copied groups gains exactly this dataset.

    A copy only ADDS membership, so instead of recomputing each image's whole dataset
    list from PG (what _sync_dataset_groups does, for the add/remove case that can drop
    slugs) it appends the one new slug_version. One image query, one bulk append, wait,
    mark synced - or leave unsynced for the reconciler if the write raises.
    """
    changed = _changed_group_ids(dataset, group_ids)
    if not changed:
        return
    image_ids = list(
        Membership.objects.filter(group_id__in=changed, deleted_at__isnull=True)
        .values_list('image_id', flat=True)
        .distinct()
    )
    append_dataset_to_images(image_ids, dataset.slug_version)
    DatasetMembership.objects.filter(dataset=dataset, group_id__in=changed).update(os_synced=True)


class DatasetViewSet(ModelViewSet):
    """Versioned collections of Groups of one immutable GroupType, stored in
    Postgres. Looked up by ``slug/version``, with freeze/unfreeze and a
    sub-resource for membership."""

    ordering = ['slug', '-version']
    lookup_field = 'slug_version'
    lookup_value_regex = r'[^/.]+\/[0-9]+'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['slug', 'type', 'is_frozen']
    search_fields = ['slug', 'slug_version', 'name']

    def get_queryset(self):
        return (
            Dataset.objects.all()
            .select_related('author', 'type')
            .annotate(group_count=Count('memberships', filter=Q(memberships__deleted_at__isnull=True)))
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return DatasetCreateSerializer
        return DatasetSerializer

    def perform_destroy(self, instance):
        """Delete the dataset, and strip its slug_version from its images' denorm.

        Deleting the row on its own CASCADEs the membership rows away, which leaves
        nothing behind with os_synced=False - so the reconciler cannot see the damage,
        and every member image keeps this dataset's slug_version in OpenSearch forever:
        filterable, and pointing at a dataset that no longer exists.

        So the memberships are soft-deleted and synced FIRST, under the same os_synced
        net as every other membership change (if the OS write raises, the rows stay
        False, the dataset survives, and the reconciler repairs it - the caller sees a
        500 and can retry the delete). Only then is the row itself deleted, taking the
        now-synced rows with it.

        Frozen is deliberately not checked: a freeze protects the membership list of a
        dataset that exists, not the right to delete the dataset.
        """
        group_ids = list(instance.memberships.filter(deleted_at__isnull=True).values_list('group_id', flat=True))
        with transaction.atomic():
            instance.memberships.filter(group_id__in=group_ids, deleted_at__isnull=True).update(
                deleted_at=timezone.now(), os_synced=False
            )
        _sync_dataset_groups(instance, group_ids)
        instance.delete()

    def list(self, request, *args, **kwargs):
        # Batch-resolve each dataset's cover (its first group's image) for the
        # whole page in a few queries, handed to the serializer via context —
        # avoids an N+1 cover fetch per card (mirrors GroupViewSet.list).
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        datasets = page if page is not None else list(queryset)
        context = {**self.get_serializer_context(), 'cover_thumbnails': batch_dataset_covers(datasets)}
        serializer = self.get_serializer(datasets, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(methods=['POST'])
    @action(detail=True, methods=['post'])
    def freeze(self, request, slug_version=None):
        self.get_object().freeze()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(methods=['POST'])
    @action(detail=True, methods=['post'])
    def unfreeze(self, request, slug_version=None):
        self.get_object().unfreeze()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=DatasetCopySerializer, responses=DatasetSerializer, methods=['POST'])
    @action(detail=True, methods=['post'])
    def copy(self, request, slug_version=None):
        """Create a new dataset of the SAME type, copying the source's members."""
        source = self.get_object()
        serializer = DatasetCopySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            # Copying into an existing slug makes a new version of it, so the source's
            # type has to match that slug's type. The manager enforces it; surface a 400.
            new_dataset = Dataset.objects.create(
                name=data['name'],
                slug=data['slug'],
                description=data.get('description', ''),
                type=source.type,
                author=request.user,
            )
        except DatasetVersionTypeMismatchError as exc:
            raise serializers.ValidationError({'slug': str(exc)}) from exc
        with transaction.atomic():
            new_dataset.copy_groups_from(source)
        copied_ids = list(new_dataset.memberships.filter(deleted_at__isnull=True).values_list('group_id', flat=True))
        _sync_dataset_copy(new_dataset, copied_ids)
        return Response(DatasetSerializer(new_dataset).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=DatasetGroupsSerializer,
        methods=['GET'],
        # Declared by hand: this action reads them straight off request.query_params,
        # so nothing else tells the schema (and therefore the generated clients) they exist.
        parameters=[
            OpenApiParameter('cursor', str, description='Opaque cursor from a previous page.'),
            OpenApiParameter('page_size', int, description=f'Groups per page, at most {API_MAX_PAGE_SIZE}.'),
            OpenApiParameter(
                'include_fields', str, description='CSV of roles, presigned_url, thumbnail_url, os_metadata, datasets.'
            ),
            OpenApiParameter('return_roles', str, description='CSV of roles to keep; default all.'),
            OpenApiParameter('include_metadata', bool, description='Include group and membership metadata.'),
            OpenApiParameter(
                'order',
                str,
                enum=['asc', 'desc'],
                description='Member order by group creation date; default desc (newest first). '
                'asc starts at the earliest member — the cover group.',
            ),
        ],
    )
    @extend_schema(
        request=DatasetUpdateGroupsSerializer,
        responses=DatasetUpdateGroupsResponseSerializer,
        methods=['POST', 'DELETE'],
    )
    @action(detail=True, methods=['get', 'post', 'delete'])
    def groups(self, request, slug_version=None):
        dataset = self.get_object()

        if request.method == 'GET':
            params = GroupExpandParamsSerializer(data=request.query_params)
            params.is_valid(raise_exception=True)
            opts = params.opts()

            # A page, not the whole membership: the cover fetch and the expansion both
            # ask OpenSearch for every image at once, and OpenSearch caps a search at
            # index.max_result_window (10k). Unpaginated, a dataset past that was a 500.
            paginator = DatasetGroupsPagination()
            page = paginator.paginate_queryset(dataset.active_groups(), request, view=self)

            cover_map = batch_cover_thumbnails(page)
            members = DatasetMemberSerializer(page, many=True, context={'cover_thumbnails': cover_map}).data
            # merge in roles + optional metadata/image data (members preserve order)
            expanded = expand_groups(page, opts)
            for member, group in zip(members, page, strict=True):
                member.update(expanded[group.id])

            return paginator.get_paginated_response(members)

        # POST / DELETE — mutate membership.
        if dataset.is_frozen:
            raise serializers.ValidationError('Dataset is frozen')

        serializer = DatasetUpdateGroupsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group_ids = serializer.validated_data['group_ids']

        if request.method == 'POST':
            found = list(Group.objects.filter(id__in=group_ids, deleted_at__isnull=True))
            found_ids = {g.id for g in found}
            missing = [str(gid) for gid in group_ids if gid not in found_ids]
            if missing:
                raise serializers.ValidationError({'group_ids': f'unknown or deleted groups: {", ".join(missing)}'})
            wrong = [str(g.id) for g in found if g.type_id != dataset.type_id]
            if wrong:
                raise serializers.ValidationError(
                    {'group_ids': f'groups not of type {dataset.type_id}: {", ".join(wrong)}'}
                )
            affected_ids = [g.id for g in found]
            with transaction.atomic():
                num_updated = dataset.add_groups(affected_ids)
        else:  # DELETE
            affected_ids = list(group_ids)
            with transaction.atomic():
                num_updated = dataset.remove_groups(affected_ids)

        # OS phase (after PG commit): re-derive datasets for the groups' images.
        _sync_dataset_groups(dataset, affected_ids)

        response_serializer = DatasetUpdateGroupsResponseSerializer(data={'updated_count': num_updated})
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)

    @extend_schema(
        request=DatasetAddImagesSerializer,
        responses=DatasetUpdateGroupsResponseSerializer,
        methods=['POST'],
    )
    @action(detail=True, methods=['post'])
    def images(self, request, slug_version=None):
        """Add loose images to a single_image dataset (wraps each in its single_image group)."""
        dataset = self.get_object()
        if dataset.type_id != SINGLE_IMAGE_TYPE:
            raise serializers.ValidationError(
                f"Only '{SINGLE_IMAGE_TYPE}' datasets accept images; this dataset is of type '{dataset.type_id}'."
            )
        if dataset.is_frozen:
            raise serializers.ValidationError('Dataset is frozen')

        serializer = DatasetAddImagesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image_ids = serializer.validated_data['image_ids']

        try:
            num_updated = add_images_to_dataset(dataset, image_ids)
        except SingleImageGroupNameConflictError as exc:
            raise serializers.ValidationError({'image_ids': str(exc)}) from exc

        response_serializer = DatasetUpdateGroupsResponseSerializer(data={'updated_count': num_updated})
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)
