import datetime

from django.conf import settings
from django.db import models

from backend.common.base_model import BaseModel
from backend.dataroom.choices import DuplicateState, StatsType
from backend.dataroom.models.tag import Tag


class StatsManager(models.Manager):
    def _get_stats_dict(self, stats=None):
        return {
            'current': stats.value if stats else 0,
            'date_updated': stats.date_updated if stats else None,
            'prev': stats.prev_value if stats else 0,
            'prev_date_updated': stats.prev_date_updated if stats else None,
            'change_per_second': stats.change_per_second if stats else 0,
            'time_left': stats.time_left if stats else None,
        }

    def get_total_images(self):
        stats = self.filter(stats_type=StatsType.TOTAL_IMAGES).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_image_sources(self):
        stats = [
            (s['group_name'], s['value'])
            for s in self.filter(stats_type=StatsType.IMAGE_SOURCES).values('group_name', 'value')
        ]
        return sorted(stats, key=lambda x: x[1], reverse=True)

    def get_image_aspect_ratio_fractions(self):
        stats = [
            (s['group_name'], s['value'])
            for s in self.filter(stats_type=StatsType.IMAGE_ASPECT_RATIO_FRACTIONS).values('group_name', 'value')
        ]
        return sorted(stats, key=lambda x: x[1], reverse=True)

    def get_images_missing_thumbnail(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MISSING_THUMBNAIL).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_missing_coca_embedding(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MISSING_COCA_EMBEDDING).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_missing_tags(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MISSING_TAGS).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_missing_duplicate_state(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MISSING_DUPLICATE_STATE).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_marked_as_duplicates(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MARKED_AS_DUPLICATES).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_marked_for_deletion(self):
        stats = self.filter(stats_type=StatsType.IMAGES_MARKED_FOR_DELETION).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def get_images_with_disabled_latents(self):
        stats = self.filter(stats_type=StatsType.IMAGES_WITH_DISABLED_LATENTS).first()
        if stats:
            return self._get_stats_dict(stats)
        return self._get_stats_dict()

    def update_all_stats(self):
        self.update_count_stats()
        self.update_queue_stats()

    def update_count_stats(self):
        self.update_stats_totals()
        self.update_stats_image_sources()
        self.update_stats_image_aspect_ratio_fractions()
        self.update_stats_image_tags()
        self.update_stats_images_missing_tags()
        self.update_stats_attributes()
        self.update_stats_latents()
        self.update_stats_datasets()

    def update_queue_stats(self):
        self.update_stats_images_missing_thumbnail()
        self.update_stats_images_missing_coca_embedding()
        self.update_stats_images_missing_duplicate_state()
        self.update_stats_images_marked_as_duplicates()
        self.update_stats_images_marked_for_deletion()
        self.update_stats_images_with_disabled_latents()

    def _update_stats(self, stats_type, value, group_name=None):
        prev_value = 0
        prev_date = None
        current = self.filter(stats_type=stats_type, group_name=group_name).first()
        if current:
            prev_value = current.value
            prev_date = current.date_updated

        self.update_or_create(
            stats_type=stats_type,
            group_name=group_name,
            defaults={
                'value': value,
                'prev_value': prev_value,
                'prev_date_updated': prev_date,
            },
        )

    def update_stats_totals(self):
        from backend.dataroom.models.os_image import OSImage

        # totals
        self._update_stats(
            stats_type=StatsType.TOTAL_IMAGES,
            value=OSImage.objects.search(fields=['id'], sort='_doc').count(),
        )

    def update_stats_image_sources(self):
        from backend.dataroom.models.os_image import OSImage

        # image sources
        image_sources = OSImage.objects.counts_by_field('source')
        existing_sources = []
        for source, count in image_sources.items():
            existing_sources.append(source)
            self._update_stats(
                stats_type=StatsType.IMAGE_SOURCES,
                group_name=source,
                value=count,
            )
        # remove old sources
        self.filter(stats_type=StatsType.IMAGE_SOURCES).exclude(group_name__in=existing_sources).delete()

    def update_stats_image_aspect_ratio_fractions(self):
        from backend.dataroom.models.os_image import OSImage

        # image aspect ratio fractions
        image_ratio_fractions = OSImage.objects.counts_by_field('aspect_ratio_fraction')
        existing_ratios = []
        for ratio, count in image_ratio_fractions.items():
            existing_ratios.append(ratio)
            self._update_stats(
                stats_type=StatsType.IMAGE_ASPECT_RATIO_FRACTIONS,
                group_name=ratio,
                value=count,
            )
        # remove old ratios
        self.filter(stats_type=StatsType.IMAGE_ASPECT_RATIO_FRACTIONS).exclude(group_name__in=existing_ratios).delete()

    def update_stats_images_missing_thumbnail(self):
        from backend.dataroom.models.os_image import OSImage

        # images missing thumbnail
        count = OSImage.objects.search().filter("bool", must_not=[{"exists": {"field": "thumbnail"}}]).count()
        self._update_stats(
            stats_type=StatsType.IMAGES_MISSING_THUMBNAIL,
            value=count,
        )

    def update_stats_images_missing_coca_embedding(self):
        from backend.dataroom.models.os_image import OSImage

        # images missing COCA embedding
        count = OSImage.objects.search().filter('term', coca_embedding_exists=False).count()
        self._update_stats(
            stats_type=StatsType.IMAGES_MISSING_COCA_EMBEDDING,
            value=count,
        )

    def update_stats_image_tags(self):
        from backend.dataroom.models.os_image import OSImage

        # image tags
        image_tags = OSImage.objects.counts_by_field('tags', number=10000)
        existing_tags = []
        for tag_name, count in image_tags.items():
            if tag_name:
                existing_tags.append(tag_name)
                Tag.objects.update_or_create(name=tag_name, defaults={'image_count': count})
        # zero out old tags
        Tag.objects.exclude(name__in=existing_tags).update(image_count=0)
        # delete old tags
        Tag.objects.filter(image_count=0).delete()

    def update_stats_images_missing_tags(self):
        from backend.dataroom.models.os_image import OSImage

        # images missing tags
        count = OSImage.objects.search().filter("bool", must_not=[{"exists": {"field": "tags"}}]).count()
        self._update_stats(
            stats_type=StatsType.IMAGES_MISSING_TAGS,
            value=count,
        )

    def update_stats_images_missing_duplicate_state(self):
        from backend.dataroom.models.os_image import OSImage

        # images missing duplicate_state
        exclude_sources = settings.DUPLICATE_FINDER_EXCLUDED_SOURCES
        count = (
            OSImage.objects.search()
            .filter(
                "bool",
                must_not=[
                    {"exists": {"field": "duplicate_state"}},
                    {"terms": {"source": exclude_sources}},
                ],
                must=[
                    {"term": {"coca_embedding_exists": True}},
                    {"term": {"is_deleted": False}},
                ],
            )
            .count()
        )
        self._update_stats(
            stats_type=StatsType.IMAGES_MISSING_DUPLICATE_STATE,
            value=count,
        )

    def update_stats_images_marked_as_duplicates(self):
        from backend.dataroom.models.os_image import OSImage

        # images marked as duplicates
        count = (
            OSImage.objects.search()
            .filter("bool", must=[{"term": {"duplicate_state": DuplicateState.DUPLICATE.value}}])
            .count()
        )
        self._update_stats(
            stats_type=StatsType.IMAGES_MARKED_AS_DUPLICATES,
            value=count,
        )

    def update_stats_images_marked_for_deletion(self):
        from backend.dataroom.models.os_image import OSImage

        # images marked for deletion
        count = OSImage.all_objects.search().filter("bool", must=[{"term": {"is_deleted": True}}]).count()
        self._update_stats(
            stats_type=StatsType.IMAGES_MARKED_FOR_DELETION,
            value=count,
        )

    def update_stats_images_with_disabled_latents(self):
        from backend.dataroom.models.latents import LatentType
        from backend.dataroom.models.os_image import OSImage, OSLatent

        # images with disabled latents
        latent_types = list(LatentType.objects.filter(is_enabled=False).values_list('name', flat=True))
        if latent_types:
            count = (
                OSImage.all_objects.search()
                .filter(
                    "bool",
                    should=[
                        {"exists": {"field": OSLatent(latent_type=latent_type).os_name_file}}
                        for latent_type in latent_types
                    ],
                    minimum_should_match=1,
                    _expand__to_dot=False,
                )
                .count()
            )
        else:
            count = 0
        self._update_stats(
            stats_type=StatsType.IMAGES_WITH_DISABLED_LATENTS,
            value=count,
        )

    def update_stats_attributes(self):
        from backend.dataroom.models.attributes import AttributesField
        from backend.dataroom.models.os_image import OSAttributes, OSImage
        from backend.dataroom.opensearch import OS

        # image attributes
        response = OS.client.indices.get_mapping(index=OSImage.INDEX)
        attributes = OSAttributes.from_mapping(response[OSImage.INDEX]['mappings']['properties'])
        for attribute in attributes.attributes.values():
            count = OSImage.objects.search().filter("bool", must=[{"exists": {"field": attribute.os_name}}]).count()
            instance = AttributesField.objects.filter(name=attribute.name).first()
            if not instance:
                instance = AttributesField.from_os_attribute(attribute)
            instance.image_count = count
            instance.is_mapped = True
            instance.save(update_fields=['image_count', 'is_mapped'])

        # zero out all other attributes
        attr_names = [attr.name for attr in attributes.attributes.values()]
        AttributesField.objects.exclude(name__in=attr_names).update(image_count=0, is_mapped=False)

    def update_stats_latents(self):
        from backend.dataroom.models.latents import LatentType
        from backend.dataroom.models.os_image import OSImage, OSLatents
        from backend.dataroom.opensearch import OS

        # image latents
        response = OS.client.indices.get_mapping(index=OSImage.INDEX)
        latents = OSLatents.from_mapping(response[OSImage.INDEX]['mappings']['properties'])
        for latent in latents.latents.values():
            count = OSImage.objects.search().filter("bool", must=[{"exists": {"field": latent.os_name_file}}]).count()
            instance = LatentType.objects.filter(name=latent.latent_type).first()
            if not instance:
                instance = LatentType.from_os_latent(latent)
            instance.image_count = count
            instance.is_mapped = True
            instance.save(update_fields=['image_count', 'is_mapped'])

        # zero out all other latents
        latent_names = [latent.latent_type for latent in latents.latents.values()]
        LatentType.objects.exclude(name__in=latent_names).update(image_count=0, is_mapped=False)

    def update_stats_datasets(self):
        from backend.dataroom.models.dataset import Dataset
        from backend.dataroom.models.os_image import OSImage

        # image datasets
        for dataset in Dataset.objects.all():
            count = OSImage.objects.search().filter("terms", datasets=[dataset.slug_version]).count()
            dataset.image_count = count
            dataset.save(update_fields=['image_count'])


class Stats(BaseModel):
    stats_type = models.CharField(max_length=40, choices=StatsType.choices)
    group_name = models.CharField(max_length=200, blank=True, null=True, default=None)
    value = models.PositiveIntegerField(default=0)
    prev_value = models.PositiveIntegerField(default=0)
    prev_date_updated = models.DateTimeField(blank=True, null=True, default=None)

    objects = StatsManager()

    class Meta:
        unique_together = ['stats_type', 'group_name']
        verbose_name_plural = 'Stats'

    def __str__(self):
        return f'{self.stats_type} "{self.group_name}": {self.value}'

    @property
    def seconds_since_updated(self):
        return (self.date_updated - self.prev_date_updated).total_seconds() if self.prev_date_updated else 0

    @property
    def change_per_second(self):
        if self.seconds_since_updated:
            return (self.value - self.prev_value) / self.seconds_since_updated
        return 0

    @property
    def time_left(self):
        if self.change_per_second < 0:
            seconds_left = abs(self.value / self.change_per_second)
            return datetime.timedelta(seconds=seconds_left)
        return None
