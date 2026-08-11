from django.db import models

from backend.common.base_model import BaseModel


class QueryManager(models.Manager):
    pass


class Query(BaseModel):
    """
    A Query is a named, dynamic collection of images defined by a set of filters
    (the OSImageFilterSet input). The filters are compiled to an OpenSearch query on
    demand wherever the query is used (``?query=<slug>``, counts, previews), so the
    collection always reflects current data. Nothing is precompiled or cached.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    # The source filters (OSImageFilterSet input). Compiled to an OpenSearch query on
    # demand via filters.compile_filters.
    query_dict = models.JSONField(default=dict)

    objects = QueryManager()

    def __str__(self):
        return self.slug

    class Meta:
        ordering = ('slug',)
        verbose_name = 'Query'
        verbose_name_plural = 'Queries'
