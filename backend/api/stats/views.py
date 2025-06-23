from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from backend.api.stats.serializers import (
    AttributeFieldSerializer,
    LatentTypeSerializer,
    QueueSerializer,
    TotalsSerializer,
)
from backend.api.stats.utils import get_queue_stats
from backend.dataroom.models import AttributesField, LatentType
from backend.dataroom.models.stats import Stats


class StatsViewSet(viewsets.ViewSet):
    def list(self, request):
        data = {
            'totals': request.build_absolute_uri(reverse('api:stats-totals')),
            'queue': request.build_absolute_uri(reverse('api:stats-queue')),
            'image_sources': request.build_absolute_uri(reverse('api:stats-image_sources')),
            'image_aspect_ratio_fractions': request.build_absolute_uri(
                reverse('api:stats-image_aspect_ratio_fractions'),
            ),
            'attributes': request.build_absolute_uri(reverse('api:stats-attributes')),
            'latent_types': request.build_absolute_uri(reverse('api:stats-latent_types')),
        }
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(responses={200: TotalsSerializer})
    @action(detail=False, url_name='totals')
    def totals(self, request):
        serializer = TotalsSerializer(
            {
                'images': Stats.objects.get_total_images(),
            }
        )
        return Response(serializer.data)

    @extend_schema(responses={200: QueueSerializer})
    @action(detail=False, url_name='queue')
    def queue(self, request):
        serializer = QueueSerializer(get_queue_stats())
        return Response(serializer.data)

    @extend_schema(responses={200: {"type": "object", "additionalProperties": {"type": "integer"}}})
    @action(detail=False, url_name='image_sources')
    def image_sources(self, request):
        return Response({source: count for source, count in Stats.objects.get_image_sources()})

    @extend_schema(responses={200: {"type": "object", "additionalProperties": {"type": "integer"}}})
    @action(detail=False, url_name='image_aspect_ratio_fractions')
    def image_aspect_ratio_fractions(self, request):
        return Response({ratio: count for ratio, count in Stats.objects.get_image_aspect_ratio_fractions()})

    @extend_schema(responses={200: AttributeFieldSerializer(many=True)})
    @action(detail=False, url_name='attributes')
    def attributes(self, request):
        serializer = AttributeFieldSerializer(AttributesField.objects.all().order_by('-image_count'), many=True)
        return Response(serializer.data)

    @extend_schema(responses={200: LatentTypeSerializer(many=True)})
    @action(detail=False, url_name='latent_types')
    def latent_types(self, request):
        serializer = LatentTypeSerializer(LatentType.objects.all().order_by('-image_count'), many=True)
        return Response(serializer.data)
