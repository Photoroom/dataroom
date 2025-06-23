import logging

from django.conf import settings
from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.urls import path
from opensearchpy import TransportError

from backend.api.stats.utils import get_queue_stats
from backend.dataroom.models import (
    AttributesField,
    LatentType,
    Stats,
    Tag,
)
from backend.dataroom.models.dataset import Dataset

logger = logging.getLogger(__name__)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "date_created", "image_count")
    readonly_fields = ("date_created", "date_updated")


@admin.register(AttributesField)
class AttributesFieldAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "json_schema",
        "is_required",
        "is_enabled",
        "is_mapped",
        "image_count",
    )
    list_filter = ("is_required", "is_enabled", "is_mapped")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return (
                "name",
                "field_type",
                "string_format",
                "array_type",
                "date_created",
                "date_updated",
                "is_mapped",
                "image_count",
            )
        return ()

    def has_delete_permission(self, request, obj=None):
        return False  # deleting is not allowed

    def has_add_permission(self, request):
        if self.model.objects.count() >= settings.MAX_ATTRIBUTES_FIELDS:
            return False
        return super().has_add_permission(request)

    def changelist_view(self, request, extra_context=None):
        if self.model.objects.count() >= settings.MAX_ATTRIBUTES_FIELDS:
            messages.warning(request, "You have reached the maximum number of attributes fields.")
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ('slug_version', 'name', 'image_count', 'is_frozen')
    search_fields = ('slug_version', 'name')
    list_filter = ('is_frozen', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('slug_version', 'version', 'image_count')
    raw_id_fields = ('author',)


@admin.register(LatentType)
class LatentTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_mask",
        "is_enabled",
        "is_mapped",
        "image_count",
    )
    list_filter = ("is_mask", "is_mapped", "is_enabled")
    search_fields = ("name",)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return "name", "date_created", "date_updated", "is_mapped", "image_count"
        return ()

    def has_delete_permission(self, request, obj=None):
        return False  # deleting is not allowed

    def has_add_permission(self, request):
        if self.model.objects.count() >= settings.MAX_LATENT_TYPES:
            return False
        return super().has_add_permission(request)

    def changelist_view(self, request, extra_context=None):
        if self.model.objects.count() >= settings.MAX_LATENT_TYPES:
            messages.warning(request, "You have reached the maximum number of latent types.")
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Stats)
class StatsAdmin(admin.ModelAdmin):
    list_display = ("stats_type", "group_name", "value", "date_updated")
    list_filter = ("stats_type",)
    readonly_fields = ("date_created", "date_updated")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path("tasks/", self.admin_site.admin_view(self.tasks_view), name="admin_tasks"),
            path("opensearch/", self.admin_site.admin_view(self.os_view), name="admin_opensearch"),
        ]
        return my_urls + urls

    def tasks_view(self, request):
        ctx = dict(
            self.admin_site.each_context(request),
        )

        total_stats = Stats.objects.get_total_images()
        total_images = total_stats['current']
        last_update = total_stats['date_updated']
        ctx.update(
            {
                'title': 'Tasks',
                'total_images': total_images,
                'last_update': last_update,
                'queue': {
                    key: {
                        'current': val['current'],
                        'percent': val['current'] / total_images * 100 if total_images else 0,
                        'date_updated': val['date_updated'],
                        'prev': val['prev'],
                        'prev_date_updated': val['prev_date_updated'],
                        'change_per_second': val['change_per_second'],
                        'time_left': val['time_left'],
                    }
                    for key, val in get_queue_stats().items()
                },
            }
        )
        return TemplateResponse(request, "admin/custom/tasks.html", ctx)

    def os_view(self, request):
        from backend.dataroom.models.os_image import OSImage
        from backend.dataroom.opensearch import OS

        ctx = dict(
            self.admin_site.each_context(request),
        )

        cluster_health = OS.client.cluster.health(timeout=25)
        node_stats = OS.client.nodes.stats(timeout=25)
        knn_stats = OS.client.transport.perform_request('GET', '/_opendistro/_knn/stats')
        images_stats = OS.client.indices.stats(index=OSImage.INDEX, timeout=25)
        images_mapping = OS.client.indices.get_mapping(index=OSImage.INDEX)
        images_settings = OS.client.indices.get_settings(index=OSImage.INDEX)

        # snapshots
        try:
            snapshot_stats = OS.client.transport.perform_request(
                'GET',
                f'/_plugins/_sm/policies/{settings.OPENSEARCH_SNAPSHOT_NAME}/_explain',
            )
            if snapshot_stats and 'policies' in snapshot_stats and len(snapshot_stats['policies']):
                snapshot_stats = snapshot_stats['policies'][0]
        except TransportError:
            snapshot_stats = None

        ctx.update(
            {
                'title': 'OpenSearch',
                'cluster_health': cluster_health,
                'node_stats': node_stats,
                'knn_stats': knn_stats,
                'snapshot_stats': snapshot_stats,
                'images_stats': images_stats['indices'][OSImage.INDEX],
                'images_shards': images_stats['_shards'],
                'images_mapping': images_mapping[OSImage.INDEX]['mappings'],
                'images_settings': images_settings[OSImage.INDEX]['settings']['index'],
            }
        )

        return TemplateResponse(request, "admin/custom/opensearch.html", ctx)
