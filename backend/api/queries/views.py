from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import BooleanField
from rest_framework.filters import SearchFilter
from rest_framework.viewsets import ModelViewSet

from backend.api.permissions import DataroomAccessPermission
from backend.api.queries.serializers import (
    QueryCreateUpdateSerializer,
    QuerySerializer,
)
from backend.dataroom.models.query import Query


@extend_schema(
    parameters=[
        OpenApiParameter('mine', OpenApiTypes.BOOL, description='Only queries authored by the current user.'),
    ]
)
class QueryViewSet(ModelViewSet):
    # Same access gate as Group/Dataset writes: any authenticated dataroom user.
    permission_classes = [DataroomAccessPermission]
    ordering = ['name']
    lookup_field = 'slug'
    # Free-text search over name/slug/description (?search=). SearchFilter also documents
    # the `search` param in the OpenAPI schema for the generated client.
    filter_backends = [SearchFilter]
    search_fields = ['name', 'slug', 'description']

    def get_queryset(self):
        qs = Query.objects.all().select_related('author')
        if self.request.query_params.get('mine') in BooleanField.TRUE_VALUES:
            qs = qs.filter(author=self.request.user)
        return qs

    def _require_author(self, instance):
        # A saved query may only be edited/deleted by the user who created it. Orphaned
        # queries (author cleared via SET_NULL) stay editable by any dataroom user.
        if instance.author_id and instance.author_id != self.request.user.id:
            raise PermissionDenied('You can only edit queries you created.')

    def perform_update(self, serializer):
        self._require_author(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_author(instance)
        instance.delete()

    def get_serializer_class(self):
        # PATCH (partial_update) uses the compiler serializer too, so `filters` are
        # validated and stored. QuerySerializer only ever exposes filters read-only.
        if self.action in ('create', 'update', 'partial_update'):
            return QueryCreateUpdateSerializer
        return QuerySerializer
