import copy

import django_filters
import rest_framework.exceptions
from django_filters import Filter
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import DjangoFilterBackend
from django_filters.utils import translate_validation
from drf_spectacular.plumbing import build_array_type, build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from opensearchpy import Q, Search

from backend.api.filters import WhitespacePreservingCharField
from backend.dataroom.choices import AttributesFilterComparator, DuplicateState
from backend.dataroom.models import AttributesFieldNotFoundError, AttributesSchema
from backend.dataroom.models.dataset import Dataset
from backend.dataroom.models.os_image import OSAttribute, OSAttributes, OSLatents
from backend.dataroom.models.tag import Tag


class InvalidFilterError(Exception):
    pass


class OSFilterMixin:
    def filter(self, search, value):
        if value in EMPTY_VALUES:
            return search
        return search.filter("term", **{self.field_name: value})

    def __init__(self, *args, is_list=False, **kwargs):
        self.is_list = is_list
        super().__init__(*args, **kwargs)


class OSNumberFilter(OSFilterMixin, django_filters.NumberFilter):
    pass


class OSNumberRangeFilter(OSFilterMixin, django_filters.NumberFilter):
    def filter(self, search, value):
        if value in EMPTY_VALUES:
            return search
        return search.filter("range", **{self.field_name: {self.lookup_expr: value}})


class OSCharFilter(OSFilterMixin, django_filters.CharFilter):
    pass


class OSBooleanFilter(OSFilterMixin, django_filters.BooleanFilter):
    pass


class OSWhitespacePreservingCharFilter(OSFilterMixin, Filter):
    field_class = WhitespacePreservingCharField


class OSEmptyStringFilter(django_filters.BooleanFilter):
    def filter(self, search, value):
        if value in EMPTY_VALUES:
            return search
        if value is True:
            return search.filter("term", **{self.field_name: ""})
        return search.exclude("term", **{self.field_name: ""})


class OSDateRangeFilter(OSFilterMixin, django_filters.IsoDateTimeFilter):
    def filter(self, search, value):
        if value in EMPTY_VALUES:
            return search
        return search.filter("range", **{self.field_name: {self.lookup_expr: value}})


class OSImageFilterSet(django_filters.FilterSet):
    source = OSCharFilter(field_name='source', help_text='Deprecated! Please use sources instead.')
    sources = OSCharFilter(
        method='filter_by_sources', is_list=True, help_text='Comma-separated list of sources to filter by.'
    )
    sources__ne = OSCharFilter(
        method='filter_by_sources__ne', is_list=True, help_text='Comma-separated list of sources to exclude.'
    )
    source__empty = OSEmptyStringFilter(field_name='source', help_text='Filter images with no source.')
    short_edge = OSNumberFilter(field_name='short_edge')
    short_edge__gt = OSNumberRangeFilter(field_name='short_edge', lookup_expr='gt')
    short_edge__gte = OSNumberRangeFilter(field_name='short_edge', lookup_expr='gte')
    short_edge__lt = OSNumberRangeFilter(field_name='short_edge', lookup_expr='lt')
    short_edge__lte = OSNumberRangeFilter(field_name='short_edge', lookup_expr='lte')
    pixel_count = OSNumberFilter(field_name='pixel_count')
    pixel_count__gt = OSNumberRangeFilter(field_name='pixel_count', lookup_expr='gt')
    pixel_count__gte = OSNumberRangeFilter(field_name='pixel_count', lookup_expr='gte')
    pixel_count__lt = OSNumberRangeFilter(field_name='pixel_count', lookup_expr='lt')
    pixel_count__lte = OSNumberRangeFilter(field_name='pixel_count', lookup_expr='lte')
    aspect_ratio = OSNumberFilter(field_name='aspect_ratio')
    aspect_ratio__gt = OSNumberRangeFilter(field_name='aspect_ratio', lookup_expr='gt')
    aspect_ratio__gte = OSNumberRangeFilter(field_name='aspect_ratio', lookup_expr='gte')
    aspect_ratio__lt = OSNumberRangeFilter(field_name='aspect_ratio', lookup_expr='lt')
    aspect_ratio__lte = OSNumberRangeFilter(field_name='aspect_ratio', lookup_expr='lte')
    aspect_ratio_fraction = OSCharFilter(field_name='aspect_ratio_fraction')
    aspect_ratio_fraction__empty = OSEmptyStringFilter(
        field_name='aspect_ratio_fraction', help_text='Filter images with no aspect ratio fraction.'
    )
    attributes = OSWhitespacePreservingCharFilter(
        method='filter_by_attributes', is_list=True, help_text='Comma-separated list of attr:value pairs to filter by.'
    )
    has_attributes = OSCharFilter(
        method='filter_by_has_attributes',
        is_list=True,
        help_text='Filter images that have all of these comma-separated list of attributes.',
    )
    lacks_attributes = OSCharFilter(
        method='filter_by_lacks_attributes',
        is_list=True,
        help_text='Filter images without any of these comma-separated list of attributes.',
    )
    has_latents = OSCharFilter(
        method='filter_by_has_latents',
        is_list=True,
        help_text='Filter images that have all of these comma-separated list of latents.',
    )
    lacks_latents = OSCharFilter(
        method='filter_by_lacks_latents',
        is_list=True,
        help_text='Filter images without any of these comma-separated list of latents.',
    )
    has_masks = OSCharFilter(
        method='filter_by_has_masks',
        is_list=True,
        help_text='Filter images that have all of these comma-separated list of latentmasks.',
    )
    lacks_masks = OSCharFilter(method='filter_by_lacks_masks', is_list=True)
    tags = OSCharFilter(
        method='filter_by_tags',
        is_list=True,
        help_text='Filter images that have any of these comma-separated list of tags.',
    )
    tags__ne = OSCharFilter(
        method='filter_by_tags__ne',
        is_list=True,
        help_text='Filter images that do not have any of these comma-separated list of tags.',
    )
    tags__all = OSCharFilter(
        method='filter_by_tags__all',
        is_list=True,
        help_text='Filter images that have all of these comma-separated list of tags.',
    )
    tags__ne_all = OSCharFilter(
        method='filter_by_tags__ne_all',
        is_list=True,
        help_text='Filter images that do not have all of these comma-separated list of tags.',
    )
    tags__empty = OSBooleanFilter(method='filter_by_tags_empty', help_text='Filter images with no tags.')
    coca_embedding__empty = OSBooleanFilter(
        method='filter_by_coca_embedding_empty', help_text='Filter images with no coca embedding.'
    )
    duplicate_state = OSCharFilter(method='filter_by_duplicate_state')
    date_created__gt = OSDateRangeFilter(field_name='date_created', lookup_expr='gt')
    date_created__gte = OSDateRangeFilter(field_name='date_created', lookup_expr='gte')
    date_created__lt = OSDateRangeFilter(field_name='date_created', lookup_expr='lt')
    date_created__lte = OSDateRangeFilter(field_name='date_created', lookup_expr='lte')
    date_updated__gt = OSDateRangeFilter(field_name='date_updated', lookup_expr='gt')
    date_updated__gte = OSDateRangeFilter(field_name='date_updated', lookup_expr='gte')
    date_updated__lt = OSDateRangeFilter(field_name='date_updated', lookup_expr='lt')
    date_updated__lte = OSDateRangeFilter(field_name='date_updated', lookup_expr='lte')
    datasets = OSCharFilter(
        method='filter_by_datasets',
        is_list=True,
        help_text='Filter images that have any of these comma-separated list of datasets.',
    )
    datasets__ne = OSCharFilter(
        method='filter_by_datasets__ne',
        is_list=True,
        help_text='Filter images that do not have any of these comma-separated list of datasets.',
    )
    datasets__all = OSCharFilter(
        method='filter_by_datasets__all',
        is_list=True,
        help_text='Filter images that have all of these comma-separated list of datasets.',
    )
    datasets__ne_all = OSCharFilter(
        method='filter_by_datasets__ne_all',
        is_list=True,
        help_text='Filter images that do not have all of these comma-separated list of datasets.',
    )
    datasets__empty = OSBooleanFilter(method='filter_by_datasets_empty', help_text='Filter images with no datasets.')

    def __init__(self, data=None, search=None, *, request=None, prefix=None):
        self.is_bound = data is not None
        self.data = data or {}
        self.search = search
        self.request = request
        self.form_prefix = prefix

        self.filters = copy.deepcopy(self.base_filters)

        # propagate the filterset to the filters
        for filter_ in self.filters.values():
            filter_.parent = self

    @property
    def filtered_search(self):
        if not hasattr(self, "_filtered_search"):
            filtered_search = self.search
            if self.is_bound:
                # ensure form validation before filtering
                filtered_search = self.filter_search(filtered_search)
            self._filtered_search = filtered_search
        return self._filtered_search

    def filter_search(self, search: Search):
        """
        Filter the OpenSearch Search object with the underlying form's `cleaned_data`. You must
        call `is_valid()` or `errors` before calling this method.

        This method should be overridden if additional filtering needs to be
        applied to the search before it is cached.
        """
        for name, value in self.form.cleaned_data.items():
            search = self.filters[name].filter(search, value)
            assert isinstance(
                search,
                Search,
            ), f"Expected '{type(self).__name__}.{name}' to return a Search, but got a {type(search).__name__} instead."
        return search

    def filter_by_sources(self, search, name, value):
        sources = value.split(',')
        return search.filter("terms", source=sources)

    def filter_by_sources__ne(self, search, name, value):
        sources = value.split(',')
        return search.filter("bool", must_not=[{"terms": {"source": sources}}])

    def filter_by_attributes(self, search, name, value):
        try:
            attribute_pairs = value.split(',')
            filters = []
            for pair in attribute_pairs:
                attr_name, attr_val = pair.split(':')
                comp = AttributesFilterComparator.get_for_attr_name(attr_name)
                if '__' in attr_name:
                    attr_name, _ = attr_name.rsplit('__', 1)
                try:
                    os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
                except AttributesFieldNotFoundError as e:
                    # the field is not in the schema
                    raise e
                if not os_type.is_valid_for_comparator(comp):
                    raise InvalidFilterError(
                        f"Invalid comparator '{comp}' for attribute '{attr_name}' of type '{os_type}'",
                    )
                else:
                    try:
                        attr = OSAttribute(name=attr_name, value=attr_val, os_type=os_type)
                    except ValueError as e:
                        raise InvalidFilterError(
                            f"Invalid filter value '{attr_val}' for attribute '{attr_name}'"
                        ) from e
                    filters.append(
                        {
                            'attr': attr,
                            'comparator': comp,
                        }
                    )
        except ValueError as e:
            raise InvalidFilterError("Invalid filter value for attributes") from e
        else:
            for fil in filters:
                attr = fil['attr']
                comparator = fil['comparator']
                if comparator == AttributesFilterComparator.EQ:
                    search = search.filter(
                        "term",
                        **{attr.os_name_keyword: attr.value},
                        _expand__to_dot=False,
                    )
                elif comparator == AttributesFilterComparator.NE:
                    search = search.filter(
                        "bool",
                        must_not=[{"term": {attr.os_name_keyword: attr.value}}],
                        _expand__to_dot=False,
                    )
                elif comparator in [
                    AttributesFilterComparator.MATCH,
                    AttributesFilterComparator.MATCH_PHRASE,
                ]:
                    search = search.filter(
                        comparator.value,
                        **{attr.os_name: attr.value},
                        _expand__to_dot=False,
                    )
                elif comparator in [
                    AttributesFilterComparator.PREFIX,
                ]:
                    search = search.filter(
                        comparator.value,
                        **{attr.os_name_keyword: attr.value},
                        _expand__to_dot=False,
                    )
                elif comparator in [
                    AttributesFilterComparator.NOT_MATCH,
                    AttributesFilterComparator.NOT_MATCH_PHRASE,
                ]:
                    search = search.filter(
                        'bool',
                        must_not=[
                            Q(comparator.negated_value, **{attr.os_name: attr.value}),
                        ],
                        _expand__to_dot=False,
                    )
                elif comparator in [
                    AttributesFilterComparator.NOT_PREFIX,
                ]:
                    search = search.filter(
                        'bool',
                        must_not=[
                            Q(comparator.negated_value, **{attr.os_name_keyword: attr.value}),
                        ],
                        _expand__to_dot=False,
                    )
                elif comparator in [
                    AttributesFilterComparator.LT,
                    AttributesFilterComparator.LTE,
                    AttributesFilterComparator.GT,
                    AttributesFilterComparator.GTE,
                ]:
                    search = search.filter(
                        "range",
                        **{attr.os_name: {comparator.value: attr.value}},
                        _expand__to_dot=False,
                    )
                else:
                    raise NotImplementedError(f"Comparator {comparator} not implemented")
            return search

    def filter_by_has_attributes(self, search, name, value):
        attrs = OSAttributes.from_json({key: None for key in value.split(',')})
        for attr in attrs.attributes.values():
            search = search.filter("exists", field=attr.os_name, _expand__to_dot=False)
        return search

    def filter_by_lacks_attributes(self, search, name, value):
        attrs = OSAttributes.from_json({key: None for key in value.split(',')})
        for attr in attrs.attributes.values():
            search = search.filter("bool", must_not=[{"exists": {"field": attr.os_name}}], _expand__to_dot=False)
        return search

    def filter_by_has_latents(self, search, name, value):
        latents = OSLatents.from_json([{'latent_type': val} for val in value.split(',')])
        search = search.filter(
            "bool",
            must=[{"exists": {"field": latent.os_name_file}} for latent in latents.latents.values()],
            _expand__to_dot=False,
        )
        return search

    def filter_by_lacks_latents(self, search, name, value):
        latents = OSLatents.from_json([{'latent_type': val} for val in value.split(',')])
        search = search.filter(
            "bool",
            must_not=[{"exists": {"field": latent.os_name_file}} for latent in latents.latents.values()],
            _expand__to_dot=False,
        )
        return search

    def filter_by_has_masks(self, search, name, value):
        latents = OSLatents.from_json([{'latent_type': val} for val in value.split(',')])
        search = search.filter(
            "bool",
            must=[{"exists": {"field": latent.os_name_file}} for latent in latents.latents.values()],
            _expand__to_dot=False,
        )
        return search

    def filter_by_lacks_masks(self, search, name, value):
        latents = OSLatents.from_json([{'latent_type': val} for val in value.split(',')])
        search = search.filter(
            "bool",
            must_not=[{"exists": {"field": latent.os_name_file}} for latent in latents.latents.values()],
            _expand__to_dot=False,
        )
        return search

    def _validate_tags(self, value):
        tag_names = value.split(',')
        tags = Tag.objects.filter(name__in=tag_names)
        missing = set(tag_names) - set([tag.name for tag in tags])
        if len(missing):
            ms = ",".join([f"'{m}'" for m in missing])
            raise rest_framework.exceptions.ValidationError(f'One or more tags do not exist: {ms}')
        return tags

    def filter_by_tags(self, search, name, value):
        tags = self._validate_tags(value)
        return search.filter("terms", tags=[tag.name for tag in tags])

    def filter_by_tags__ne(self, search, name, value):
        tags = self._validate_tags(value)
        return search.filter("bool", must_not=[{"terms": {"tags": [tag.name for tag in tags]}}])

    def filter_by_tags__all(self, search, name, value):
        tags = self._validate_tags(value)
        return search.filter("bool", must=[{"term": {"tags": tag.name}} for tag in tags])

    def filter_by_tags__ne_all(self, search, name, value):
        tags = self._validate_tags(value)
        return search.filter("bool", must_not=[{"bool": {"must": [{"term": {"tags": tag.name}} for tag in tags]}}])

    def filter_by_tags_empty(self, search, name, value):
        if value:
            return search.filter("bool", must_not=[{"exists": {"field": "tags"}}])
        return search.filter("exists", field="tags")

    def filter_by_coca_embedding_empty(self, search, name, value):
        return search.filter('term', coca_embedding_exists=not value)

    def filter_by_duplicate_state(self, search, name, value):
        if value == 'None':
            value = None
        else:
            try:
                value = int(value)
            except (TypeError, ValueError) as e:
                raise rest_framework.exceptions.ValidationError(f"Invalid value for duplicate_state: {value}") from e
        if value not in DuplicateState.values():
            raise rest_framework.exceptions.ValidationError(f"Invalid value for duplicate_state: {value}")
        value = DuplicateState(value)

        if value == DuplicateState.UNPROCESSED:
            return search.filter("bool", must_not=[{"exists": {"field": "duplicate_state"}}])
        else:
            return search.filter("term", duplicate_state=value.value)

    def _validate_datasets(self, value):
        dataset_slug_versions = value.split(',')
        datasets = Dataset.objects.filter_by_slug_versions(slug_versions=dataset_slug_versions)
        missing = set(dataset_slug_versions) - set([ds.slug_version for ds in datasets])
        if len(missing):
            ms = ",".join([f"'{m}'" for m in missing])
            raise rest_framework.exceptions.ValidationError(f'One or more datasets do not exist: {ms}')
        return datasets

    def filter_by_datasets(self, search, name, value):
        datasets = self._validate_datasets(value)
        return search.filter("terms", datasets=[ds.slug_version for ds in datasets])

    def filter_by_datasets__ne(self, search, name, value):
        datasets = self._validate_datasets(value)
        return search.filter("bool", must_not=[{"terms": {"datasets": [ds.slug_version for ds in datasets]}}])

    def filter_by_datasets__all(self, search, name, value):
        datasets = self._validate_datasets(value)
        return search.filter("bool", must=[{"term": {"datasets": ds.slug_version}} for ds in datasets])

    def filter_by_datasets__ne_all(self, search, name, value):
        datasets = self._validate_datasets(value)
        return search.filter(
            "bool", must_not=[{"bool": {"must": [{"term": {"datasets": ds.slug_version}} for ds in datasets]}}]
        )

    def filter_by_datasets_empty(self, search, name, value):
        if value:
            return search.filter("bool", must_not=[{"exists": {"field": "datasets"}}])
        return search.filter("exists", field="datasets")


class OSFilterBackend(DjangoFilterBackend):
    filterset_class = OSImageFilterSet
    raise_exception = True

    def get_filterset_kwargs(self, request, search, view):
        return {
            "data": request.query_params,
            "search": search,
            "request": request,
        }

    def get_filterset(self, request, search, view):
        kwargs = self.get_filterset_kwargs(request, search, view)
        return self.filterset_class(**kwargs)

    def filter_search(self, request, search, view):
        filterset = self.get_filterset(request, search, view)

        if not filterset.is_valid() and self.raise_exception:
            raise translate_validation(filterset.errors)
        return filterset.filtered_search


def os_image_filter_params():
    """
    Generate a list of OpenApiParameter from OSImageFilterSet filters.
    """
    filter_class = OSImageFilterSet
    parameters = []

    # Map of filter types to OpenAPI types
    type_mapping = {
        OSCharFilter: OpenApiTypes.STR,
        OSNumberFilter: OpenApiTypes.NUMBER,
        OSNumberRangeFilter: OpenApiTypes.NUMBER,
        OSBooleanFilter: OpenApiTypes.BOOL,
        OSWhitespacePreservingCharFilter: OpenApiTypes.STR,
        OSEmptyStringFilter: OpenApiTypes.BOOL,
        OSDateRangeFilter: OpenApiTypes.DATETIME,
    }

    for field_name, filter_field in filter_class.base_filters.items():
        # Get the schema type based on the filter class
        schema = None
        for filter_type, openapi_type in type_mapping.items():
            if isinstance(filter_field, filter_type):
                schema = build_basic_type(openapi_type)
                break

        if schema is None:
            # Default to string if no matching type found
            schema = build_basic_type(OpenApiTypes.STR)

        # Handle array types based on is_list field attribute
        if hasattr(filter_field, 'is_list') and filter_field.is_list:
            schema = build_array_type(schema)

        # Get description from field if available
        description = filter_field.extra.get('help_text', '')
        if not description and hasattr(filter_field, 'label'):
            description = filter_field.label

        # Create OpenApiParameter
        required = filter_field.extra.get('required', False)
        parameter = OpenApiParameter(
            name=field_name,
            type=schema,
            location=OpenApiParameter.QUERY,
            description=description,
            required=required,
        )

        parameters.append(parameter)

    return parameters
