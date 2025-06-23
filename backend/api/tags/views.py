from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from backend.api.tags.serializers import (
    TAG_IMAGES_IMAGE_LIMIT,
    ImageIdsWithTagNamesSerializer,
    TagImagesResponseSerializer,
    TagSerializer,
)
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.models.tag import Tag
from backend.dataroom.opensearch import OSBulkIndex


class TagViewSet(ModelViewSet):
    ordering = ['-image_count', 'name']

    def get_serializer_class(self):
        return TagSerializer

    def get_queryset(self):
        return Tag.objects.all()

    @extend_schema(
        request=ImageIdsWithTagNamesSerializer,
        responses=TagImagesResponseSerializer,
    )
    @action(detail=False, methods=['PUT'])
    def tag_images(self, request):
        serializer = ImageIdsWithTagNamesSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)

        image_ids = list(set(serializer.validated_data['image_ids']))
        tag_names = serializer.validated_data['tag_names']
        result = (
            OSImage.objects.search(fields=['id', 'tags'])
            .filter(
                'terms',
                id=image_ids,
            )
            .extra(size=TAG_IMAGES_IMAGE_LIMIT)
            .execute()
        )
        existing_images = OSImage.list_from_hits(result.hits)
        if len(existing_images) != len(image_ids):
            missing = set(image_ids) - set([i.id for i in existing_images])
            missing = ', '.join([f"'{image_id}'" for image_id in missing])
            return Response(
                {'error': f'One or more images do not exist: {missing}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        num_created = 0

        for tag_name in tag_names:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            if created:
                num_created += 1

        # TODO: log updates

        with OSBulkIndex() as os_bulk:
            for image in existing_images:
                for tag_name in tag_names:
                    if tag_name not in image.tags:
                        image.tags.append(tag_name)
                image.save(fields=['tags'], bulk_index=os_bulk)

        return Response(
            {
                'tags_created': num_created,
                'images_tagged': len(existing_images),
            },
            status=status.HTTP_200_OK,
        )
