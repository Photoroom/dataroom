from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from backend.api.datasets.serializers import (
    DatasetCreateSerializer,
    DatasetPreviewImageSerializer,
    DatasetPreviewImagesSerializer,
    DatasetSerializer,
    DatasetUpdateImagesResponseSerializer,
    DatasetUpdateImagesSerializer,
)
from backend.dataroom.models.dataset import Dataset


class DatasetViewSet(ModelViewSet):
    ordering = ['slug', '-version']
    lookup_field = 'slug_version'
    lookup_value_regex = r'[^/.]+\/[0-9]+'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['slug']

    def get_queryset(self):
        return Dataset.objects.all().select_related('author')

    def get_serializer_class(self):
        if self.action == 'create':
            return DatasetCreateSerializer
        return DatasetSerializer

    @extend_schema(methods=["POST"])
    @action(detail=True, methods=['post'])
    def freeze(self, request, slug_version=None):
        dataset = self.get_object()
        dataset.freeze()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(methods=["POST"])
    @action(detail=True, methods=['post'])
    def unfreeze(self, request, slug_version=None):
        dataset = self.get_object()
        dataset.unfreeze()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=DatasetPreviewImagesSerializer, methods=["GET"])
    @extend_schema(
        request=DatasetUpdateImagesSerializer,
        responses=DatasetUpdateImagesResponseSerializer,
        methods=["POST"],
    )
    @extend_schema(
        request=DatasetUpdateImagesSerializer,
        responses=DatasetUpdateImagesResponseSerializer,
        methods=["DELETE"],
    )
    @action(detail=True, methods=['get', 'post', 'delete'])
    def images(self, request, slug_version=None):
        dataset = self.get_object()

        if request.method == 'GET':
            preview_fields = ['id', 'image', 'thumbnail']
            preview_images = [
                DatasetPreviewImageSerializer(image.to_json(fields=preview_fields)).data
                for image in dataset.get_preview_images(fields=preview_fields)
            ]
            response_serializer = DatasetPreviewImagesSerializer(
                data={
                    'image_count': dataset.image_count,
                    'preview_images': preview_images,
                }
            )
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data)

        elif request.method in ['POST', 'DELETE']:
            # Add images to dataset
            if dataset.is_frozen:
                raise serializers.ValidationError('Dataset is frozen')

            serializer = DatasetUpdateImagesSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            if request.method == 'POST':
                num_updated = dataset.add_images(serializer.validated_data['image_ids'])
            elif request.method == 'DELETE':
                num_updated = dataset.remove_images(serializer.validated_data['image_ids'])

            response_serializer = DatasetUpdateImagesResponseSerializer(
                data={
                    'updated_count': num_updated,
                }
            )
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data)
