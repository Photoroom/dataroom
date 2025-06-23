from django.db import models, transaction

from backend.common.base_model import BaseModel
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OSBulkIndex

DATASET_UPDATE_IMAGES_LIMIT = 1000
DATASET_PREVIEW_IMAGES_COUNT = 12


class DatasetVersionManager(models.Manager):
    def get_next_version(self, slug):
        version = 1
        latest = self.filter(slug=slug).order_by('-version').first()
        if latest:
            version = latest.version + 1
        return version

    def create(self, *args, **kwargs):
        slug = kwargs.get('slug')
        if not slug:
            raise ValueError('slug is required')

        with transaction.atomic():
            # lock the table to get latest version number, without race conditions
            self.select_for_update().filter(slug=slug)
            version = self.get_next_version(slug)
            return super().create(*args, **kwargs, version=version)

    def filter_by_slug_versions(self, slug_versions):
        return self.filter(slug_version__in=slug_versions)


class Dataset(BaseModel):
    """
    A dataset is a collection of images, with a version number.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    version = models.PositiveIntegerField()
    slug_version = models.CharField(max_length=110, unique=True)
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    image_count = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True, default='')
    is_frozen = models.BooleanField(default=False)

    objects = DatasetVersionManager()

    def __str__(self):
        return self.slug_version

    class Meta:
        ordering = ('slug', '-version')
        constraints = [models.UniqueConstraint(fields=['slug', 'version'], name='dataset_slug_version_idx')]

    def save(self, *args, **kwargs):
        if not self.version:
            self.version = Dataset.objects.get_next_version(self.slug)
        self.slug_version = self.get_slug_version()
        super().save(*args, **kwargs)

    def get_slug_version(self):
        return f'{self.slug}/{self.version}'

    def get_preview_images(self, fields=None):
        if not fields:
            fields = ['id', 'image', 'thumbnail']

        result = (
            OSImage.objects.search(
                fields=fields,
            )
            .filter("terms", datasets=[self.slug_version])
            .extra(size=DATASET_PREVIEW_IMAGES_COUNT)
            .execute()
        )
        images = OSImage.list_from_hits(result.hits)
        return images

    def freeze(self):
        self.is_frozen = True
        self.save()

    def unfreeze(self):
        self.is_frozen = False
        self.save()

    def add_images(self, image_ids) -> int:
        if self.is_frozen:
            raise ValueError('Dataset is frozen')

        num_updated = 0
        result = (
            OSImage.objects.search(fields=['id', 'datasets'])
            .filter(
                'terms',
                id=image_ids,
            )
            .extra(size=DATASET_UPDATE_IMAGES_LIMIT)
            .execute()
        )
        images = OSImage.list_from_hits(result.hits)

        with OSBulkIndex() as os_bulk:
            for image in images:
                if self.slug_version not in image.datasets:
                    image.datasets.add(self.slug_version)
                    num_updated += 1
                    image.save(fields=['datasets'], bulk_index=os_bulk)

        return num_updated

    def remove_images(self, image_ids) -> int:
        if self.is_frozen:
            raise ValueError('Dataset is frozen')

        num_updated = 0
        result = (
            OSImage.objects.search(fields=['id', 'datasets'])
            .filter(
                'terms',
                id=image_ids,
            )
            .extra(size=DATASET_UPDATE_IMAGES_LIMIT)
            .execute()
        )
        images = OSImage.list_from_hits(result.hits)

        with OSBulkIndex() as os_bulk:
            for image in images:
                if self.slug_version in image.datasets:
                    image.datasets.remove(self.slug_version)
                    num_updated += 1
                image.save(fields=['datasets'], bulk_index=os_bulk)

        return num_updated
