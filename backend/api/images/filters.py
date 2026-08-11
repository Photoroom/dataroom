import copy
import json

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
from backend.dataroom.groups.os_fields import text_to_keyword_field
from backend.dataroom.models import AttributesSchema
from backend.dataroom.models.os_image import OSAttribute, OSAttributes, OSFieldType, OSLatents
from backend.dataroom.models.query import Query


class InvalidFilterError(Exception):
    pass


# Generic filter field sets — adding a new numeric/date field is just one word
NUMERIC_FIELDS = {'width', 'height', 'short_edge', 'pixel_count', 'aspect_ratio'}
DATE_FIELDS = {'date_created', 'date_updated'}
RANGE_OPS = {'gt', 'gte', 'lt', 'lte'}


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
    datasets__prefix = OSCharFilter(
        method='filter_by_datasets__prefix',
        is_list=True,
        help_text='Filter images in any version of these comma-separated dataset slugs (version-agnostic).',
    )
    datasets__empty = OSBooleanFilter(method='filter_by_datasets_empty', help_text='Filter images with no datasets.')
    # group membership filters (see backend/dataroom/groups/ and the design docs).
    # group_ids: comma-separated group ids. Compose with `roles` to filter exact role-in-group pairs.
    group_ids = OSCharFilter(
        method='filter_by_group_ids',
        is_list=True,
        help_text='Comma-separated list of group ids the image is a member of (any).',
    )
    roles = OSCharFilter(
        method='filter_by_roles',
        is_list=True,
        help_text='Comma-separated list of membership roles (any group).',
    )
    roles__ne = OSCharFilter(
        method='filter_by_roles__ne',
        is_list=True,
        help_text='Filter images that do not have any of these comma-separated roles.',
    )
    roles__all = OSCharFilter(
        method='filter_by_roles__all',
        is_list=True,
        help_text='Filter images that have all of these comma-separated roles.',
    )
    roles__ne_all = OSCharFilter(
        method='filter_by_roles__ne_all',
        is_list=True,
        help_text='Filter images that do not have all of these comma-separated roles.',
    )
    roles__empty = OSBooleanFilter(method='filter_by_roles_empty', help_text='Filter images with no group memberships.')
    group_type = OSCharFilter(
        method='filter_by_group_type',
        help_text='Filter to images in any group of this type (e.g. product, dataset, relationship).',
    )
    query = OSCharFilter(method='filter_by_query', help_text='Filter images by query.')

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
        # 1. Standard declared filters (sources, tags, attributes, etc.)
        for name, value in self.form.cleaned_data.items():
            search = self.filters[name].filter(search, value)
            assert isinstance(
                search,
                Search,
            ), f"Expected '{type(self).__name__}.{name}' to return a Search, but got a {type(search).__name__} instead."

        # 2. Generic numeric/date range filters — no declaration needed
        for param, value in self.data.items():
            if param in self.filters or not value:
                continue
            parts = param.rsplit('__', 1)
            field, op = (parts[0], parts[1]) if len(parts) == 2 else (param, None)

            if field in NUMERIC_FIELDS:
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    continue
                if op in RANGE_OPS:
                    search = search.filter("range", **{field: {op: numeric_value}})
                elif op == 'ne':
                    search = search.filter("bool", must_not=[{"term": {field: numeric_value}}])
                elif op is None:
                    search = search.filter("term", **{field: numeric_value})
            elif field in DATE_FIELDS and op in RANGE_OPS:
                search = search.filter("range", **{field: {op: value}})

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

                # Raises AttributesFieldNotFound if the field is not in the schema
                os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
                is_indexed = AttributesSchema.get_is_indexed_for_field_name(attr_name)
                if not is_indexed:
                    raise InvalidFilterError(
                        f"Attribute '{attr_name}' is not indexed and can therefore not be used for filtering."
                    )

                if not os_type.is_valid_for_comparator(comp):
                    raise InvalidFilterError(
                        f"Invalid comparator '{comp}' for attribute '{attr_name}' of type '{os_type}'",
                    )
                else:
                    try:
                        attr = OSAttribute(name=attr_name, value=attr_val, os_type=os_type, is_indexed=True)
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
            if attr.os_type == OSFieldType.OBJECT:
                raise InvalidFilterError(
                    f"Existance checks on object attributes are not supported. Attribute: {attr.name}"
                )

            search = search.filter("exists", field=attr.os_name, _expand__to_dot=False)
        return search

    def filter_by_lacks_attributes(self, search, name, value):
        attrs = OSAttributes.from_json({key: None for key in value.split(',')})
        for attr in attrs.attributes.values():
            if attr.os_type == OSFieldType.OBJECT:
                raise InvalidFilterError(
                    f"Existance checks on object attributes are not supported. Attribute: {attr.name}"
                )

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

    # Tags are filtered directly against OpenSearch (the source of truth for what's on an
    # image), NOT validated against the Postgres Tag table. Tag cardinality is effectively
    # unbounded (e.g. per-product tags like "product_47brand_com_11591462740"), so the Tag
    # table — synced from a capped aggregation — can never be a complete list; validating
    # against it 400s on any tag beyond the cap even though it exists in the index. Filtering
    # by an unknown tag simply matches nothing, exactly like `sources`.
    def filter_by_tags(self, search, name, value):
        tags = value.split(',')
        return search.filter("terms", tags=tags)

    def filter_by_tags__ne(self, search, name, value):
        tags = value.split(',')
        return search.filter("bool", must_not=[{"terms": {"tags": tags}}])

    def filter_by_tags__all(self, search, name, value):
        tags = value.split(',')
        return search.filter("bool", must=[{"term": {"tags": tag}} for tag in tags])

    def filter_by_tags__ne_all(self, search, name, value):
        tags = value.split(',')
        return search.filter("bool", must_not=[{"bool": {"must": [{"term": {"tags": tag}} for tag in tags]}}])

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

    def filter_by_datasets(self, search, name, value):
        datasets = value.split(',')
        return search.filter("terms", datasets=datasets)

    def filter_by_datasets__ne(self, search, name, value):
        datasets = value.split(',')
        return search.filter("bool", must_not=[{"terms": {"datasets": datasets}}])

    def filter_by_datasets__all(self, search, name, value):
        datasets = value.split(',')
        return search.filter("bool", must=[{"term": {"datasets": ds}} for ds in datasets])

    def filter_by_datasets__ne_all(self, search, name, value):
        datasets = value.split(',')
        return search.filter("bool", must_not=[{"bool": {"must": [{"term": {"datasets": ds}} for ds in datasets]}}])

    def filter_by_datasets__prefix(self, search, name, value):
        # Version-agnostic dataset match: an image's `datasets` entries are
        # `slug/version` strings, so prefix `slug/` matches every version of a
        # dataset. Pass bare slugs (e.g. `shoes`); the `/` is appended so
        # `shoes` doesn't also match `shoes-2/1`.
        prefixes = [v for v in value.split(',') if v]
        if not prefixes:
            return search
        return search.filter(
            "bool",
            should=[{"prefix": {"datasets": f'{p}/'}} for p in prefixes],
            minimum_should_match=1,
        )

    def filter_by_datasets_empty(self, search, name, value):
        if value:
            return search.filter("bool", must_not=[{"exists": {"field": "datasets"}}])
        return search.filter("exists", field="datasets")

    # ------------------------------------------------------------------
    # Group / role membership filters
    #
    # Postgres stores group ids as plain UUIDs; OS denorm joins them with the
    # group's type as ``<type>::<uuid>`` (and ``<role>::<type>::<uuid>`` in the
    # memberships array). For exact-id filters we resolve UUID -> type once
    # via Postgres before issuing the OS query.
    # ------------------------------------------------------------------
    def _encoded_gids(self, raw_value):
        """Resolve a comma-separated list of group UUIDs into ``<type>::<uuid>`` strings.

        Unknown ids are silently dropped — same shape as a no-match OS query.
        """
        from backend.dataroom.models.group import Group

        uuids = [v for v in (raw_value or '').split(',') if v]
        if not uuids:
            return []
        rows = Group.objects.filter(id__in=uuids).values_list('type_id', 'id')
        return [f'{type_id}::{gid}' for type_id, gid in rows]

    def filter_by_group_ids(self, search, name, value):
        gids = self._encoded_gids(value)
        if not gids:
            return search
        # If a roles filter is also set, filter_by_roles composes the encoded
        # role::type::uuid terms; defer there to keep the clause single.
        if self.data.get('roles'):
            return search
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once group_ids is keyword everywhere.
        return search.filter("terms", **{text_to_keyword_field("group_ids"): gids})

    def filter_by_roles(self, search, name, value):
        roles = [v for v in value.split(',') if v]
        if not roles:
            return search
        gids = self._encoded_gids(self.data.get('group_ids'))
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once memberships is keyword everywhere.
        if gids:
            # exact (role, group) pairs — terms over the encoded keyword
            terms = [f'{r}::{g}' for r in roles for g in gids]
            return search.filter("terms", **{text_to_keyword_field("memberships"): terms})
        # role-anywhere — bool should over prefix queries (low role cardinality)
        return search.filter(
            "bool",
            should=[{"prefix": {text_to_keyword_field("memberships"): f'{r}::'}} for r in roles],
            minimum_should_match=1,
        )

    # Same operators as tags, matched by prefix on the encoded memberships array.
    def filter_by_roles__ne(self, search, name, value):
        roles = [v for v in value.split(',') if v]
        if not roles:
            return search
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once memberships is keyword everywhere.
        return search.filter(
            "bool", must_not=[{"prefix": {text_to_keyword_field("memberships"): f'{r}::'}} for r in roles]
        )

    def filter_by_roles__all(self, search, name, value):
        roles = [v for v in value.split(',') if v]
        if not roles:
            return search
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once memberships is keyword everywhere.
        return search.filter("bool", must=[{"prefix": {text_to_keyword_field("memberships"): f'{r}::'}} for r in roles])

    def filter_by_roles__ne_all(self, search, name, value):
        roles = [v for v in value.split(',') if v]
        if not roles:
            return search
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once memberships is keyword everywhere.
        return search.filter(
            "bool",
            must_not=[
                {"bool": {"must": [{"prefix": {text_to_keyword_field("memberships"): f'{r}::'}} for r in roles]}}
            ],
        )

    def filter_by_roles_empty(self, search, name, value):
        if value:
            return search.filter("bool", must_not=[{"exists": {"field": "memberships"}}])
        return search.filter("exists", field="memberships")

    def filter_by_group_type(self, search, name, value):
        if not value:
            return search
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once group_ids is keyword everywhere.
        return search.filter("prefix", **{text_to_keyword_field("group_ids"): f'{value}::'})

    def filter_by_query(self, search, name, value):
        try:
            query = Query.objects.get(slug=value)
        except Query.DoesNotExist as e:
            raise rest_framework.exceptions.ValidationError(f'Query with slug "{value}" does not exist') from e
        # Compile the saved query's filters into the search.
        return compile_filters(query.query_dict, search, request=self.request)


def compile_filters(filters, search, request=None):
    """Compile a saved query's filters onto `search`. Raises if a referenced dataset is gone.

    `filters` is the same query-param dict the images endpoint accepts (what the filter UI
    produces): either flat params or a single ``filter_lanes`` JSON string, compiled through
    the same backend, so saving a query is just freezing the current image search.
    """
    filters = filters or {}
    filter_lanes_raw = filters.get('filter_lanes')
    if filter_lanes_raw:
        return OSFilterBackend().filter_search_lanes(request, search, None, filter_lanes_raw)
    filterset = OSImageFilterSet(data=filters, search=search, request=request)
    if not filterset.is_valid():
        raise translate_validation(filterset.errors)
    return filterset.filtered_search


class OSFilterBackend(DjangoFilterBackend):
    filterset_class = OSImageFilterSet
    raise_exception = True

    def get_filterset_kwargs(self, request, search, view):
        return {
            "data": request.query_params,
            "search": search,
            "request": request,
        }

    def get_filterset(self, request, search, view, exclude_field=None):
        kwargs = self.get_filterset_kwargs(request, search, view)
        if exclude_field:
            kwargs['data'] = self._exclude_params(kwargs['data'], exclude_field)
        return self.filterset_class(**kwargs)

    def filter_search(self, request, search, view, exclude_field=None):
        # Check for multi-lane filter param
        filter_lanes_raw = request.query_params.get('filter_lanes')
        if filter_lanes_raw:
            return self.filter_search_lanes(request, search, view, filter_lanes_raw)

        filterset = self.get_filterset(request, search, view, exclude_field=exclude_field)

        if not filterset.is_valid() and self.raise_exception:
            raise translate_validation(filterset.errors)
        return filterset.filtered_search

    def filter_search_lanes(self, request, search, view, filter_lanes_raw):
        """Apply multi-lane OR filtering with optional per-lane negation.

        Each lane is a set of AND'd filters. Lanes are OR'd together.
        A negated lane wraps its query in must_not.
        """
        try:
            lanes_data = json.loads(filter_lanes_raw)
        except (json.JSONDecodeError, TypeError) as e:
            raise rest_framework.exceptions.ValidationError('Invalid filter_lanes JSON') from e

        if not isinstance(lanes_data, list) or not lanes_data:
            raise rest_framework.exceptions.ValidationError('filter_lanes must be a non-empty array')

        lane_queries = []
        for lane in lanes_data:
            chips = lane.get('chips', [])
            negated = lane.get('negated', False)

            # Convert chips to flat query params that the existing filterset understands
            lane_params = self._chips_to_query_params(chips)

            # Create a fresh search and apply this lane's filters through the existing filterset
            lane_search = Search()
            lane_filterset = self.filterset_class(data=lane_params, search=lane_search, request=request)
            if not lane_filterset.is_valid() and self.raise_exception:
                raise translate_validation(lane_filterset.errors)
            filtered_lane = lane_filterset.filtered_search

            # Extract the query from the filtered search
            lane_query = filtered_lane.to_dict().get('query', {'match_all': {}})
            q = Q(lane_query)

            if negated:
                q = Q('bool', must_not=[q])

            lane_queries.append(q)

        # Combine lanes with OR (should + minimum_should_match=1)
        combined = Q('bool', should=[q for q in lane_queries], minimum_should_match=1)
        return search.filter(combined)

    @staticmethod
    def _chips_to_query_params(chips):
        """Convert a list of chip dicts {field, operator, value} to flat query params
        matching the existing OSImageFilterSet parameter format."""
        from backend.api.images.filters import DATE_FIELDS, NUMERIC_FIELDS

        params = {}
        # Group chips by field
        by_field = {}
        for chip in chips:
            field = chip.get('field', '')
            by_field.setdefault(field, []).append(chip)

        for field, field_chips in by_field.items():
            if field == 'source':
                eq = [c['value'] for c in field_chips if c.get('operator') == 'eq']
                ne = [c['value'] for c in field_chips if c.get('operator') == 'ne']
                if eq:
                    params['sources'] = ','.join(eq)
                if ne:
                    params['sources__ne'] = ','.join(ne)
            elif field == 'tag':
                eq = [c['value'] for c in field_chips if c.get('operator') == 'eq']
                ne = [c['value'] for c in field_chips if c.get('operator') == 'ne']
                if eq:
                    params['tags'] = ','.join(eq)
                if ne:
                    params['tags__ne'] = ','.join(ne)
            elif field == 'dataset':
                eq = [c['value'] for c in field_chips if c.get('operator') == 'eq']
                ne = [c['value'] for c in field_chips if c.get('operator') == 'ne']
                if eq:
                    params['datasets'] = ','.join(eq)
                if ne:
                    params['datasets__ne'] = ','.join(ne)
            elif field == 'latent':
                eq = [c['value'] for c in field_chips if c.get('operator') == 'eq']
                ne = [c['value'] for c in field_chips if c.get('operator') == 'ne']
                if eq:
                    params['has_latents'] = ','.join(eq)
                if ne:
                    params['lacks_latents'] = ','.join(ne)
            elif field == 'duplicate_state':
                params['duplicate_state'] = field_chips[0]['value']
            elif field == 'aspect_ratio_fraction':
                params['aspect_ratio_fraction'] = field_chips[0]['value']
            elif field in NUMERIC_FIELDS:
                for chip in field_chips:
                    op = chip.get('operator', 'eq')
                    if op == 'eq':
                        params[field] = chip['value']
                    else:
                        params[f'{field}__{op}'] = chip['value']
            elif field in DATE_FIELDS:
                for chip in field_chips:
                    op = chip.get('operator', 'gte')
                    params[f'{field}__{op}'] = chip['value']
            elif field.startswith('attr:'):
                attr_name = field[5:]
                for chip in field_chips:
                    op = chip.get('operator', 'eq')
                    if op == 'exists':
                        existing = params.get('has_attributes', '').split(',') if params.get('has_attributes') else []
                        existing.append(attr_name)
                        params['has_attributes'] = ','.join(filter(None, existing))
                    elif op == 'not_exists':
                        existing = (
                            params.get('lacks_attributes', '').split(',') if params.get('lacks_attributes') else []
                        )
                        existing.append(attr_name)
                        params['lacks_attributes'] = ','.join(filter(None, existing))
                    else:
                        parts = params.get('attributes', '').split(',') if params.get('attributes') else []
                        if op == 'eq':
                            parts.append(f'{attr_name}:{chip["value"]}')
                        else:
                            parts.append(f'{attr_name}__{op}:{chip["value"]}')
                        params['attributes'] = ','.join(filter(None, parts))
            elif field == 'has_attributes':
                params['has_attributes'] = ','.join(c['value'] for c in field_chips)
            elif field == 'lacks_attributes':
                params['lacks_attributes'] = ','.join(c['value'] for c in field_chips)

        return params

    @staticmethod
    def _exclude_params(params, exclude_field):
        """Remove filter params for a given logical field so faceted counts exclude the field's own filters."""
        # Map logical field names to the query param prefixes they use
        field_param_map = {
            'source': ['sources', 'sources__ne', 'source', 'source__empty'],
            'tag': ['tags', 'tags__ne', 'tags__all', 'tags__ne_all', 'tags__empty'],
            'tags': ['tags', 'tags__ne', 'tags__all', 'tags__ne_all', 'tags__empty'],
            'dataset': ['datasets', 'datasets__ne', 'datasets__all', 'datasets__ne_all', 'datasets__empty'],
            'datasets': ['datasets', 'datasets__ne', 'datasets__all', 'datasets__ne_all', 'datasets__empty'],
            'duplicate_state': ['duplicate_state'],
            'aspect_ratio_fraction': ['aspect_ratio_fraction', 'aspect_ratio_fraction__empty'],
        }
        exclude_keys = set()
        if exclude_field in field_param_map:
            exclude_keys.update(field_param_map[exclude_field])
        elif exclude_field in NUMERIC_FIELDS:
            exclude_keys.add(exclude_field)
            for op in ['gt', 'gte', 'lt', 'lte', 'ne']:
                exclude_keys.add(f'{exclude_field}__{op}')
        elif exclude_field in DATE_FIELDS:
            for op in RANGE_OPS:
                exclude_keys.add(f'{exclude_field}__{op}')
        elif exclude_field.startswith('attr:'):
            # Attribute filters are packed in the 'attributes', 'has_attributes', 'lacks_attributes' params
            # We need to filter out the specific attribute from the comma-separated values
            attr_name = exclude_field[5:]
            filtered = {}
            for key, value in params.items():
                if key == 'attributes':
                    parts = [p for p in value.split(',') if p.split(':')[0].split('__')[0] != attr_name]
                    if parts:
                        filtered[key] = ','.join(parts)
                    continue
                if key in ('has_attributes', 'lacks_attributes'):
                    parts = [p for p in value.split(',') if p != attr_name]
                    if parts:
                        filtered[key] = ','.join(parts)
                    continue
                filtered[key] = value
            return filtered
        elif exclude_field == 'latent':
            exclude_keys.update(['has_latents', 'lacks_latents'])

        if not exclude_keys:
            return params

        return {k: v for k, v in params.items() if k not in exclude_keys}


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

    # Add generic numeric/date range filter params
    for field in sorted(NUMERIC_FIELDS):
        parameters.append(
            OpenApiParameter(
                name=field,
                type=build_basic_type(OpenApiTypes.NUMBER),
                location=OpenApiParameter.QUERY,
                description=f'Exact match for {field}.',
            )
        )
        for op in ['gt', 'gte', 'lt', 'lte', 'ne']:
            parameters.append(
                OpenApiParameter(
                    name=f'{field}__{op}',
                    type=build_basic_type(OpenApiTypes.NUMBER),
                    location=OpenApiParameter.QUERY,
                    description=f'{field} {op}.',
                )
            )
    for field in sorted(DATE_FIELDS):
        for op in sorted(RANGE_OPS):
            parameters.append(
                OpenApiParameter(
                    name=f'{field}__{op}',
                    type=build_basic_type(OpenApiTypes.DATETIME),
                    location=OpenApiParameter.QUERY,
                    description=f'{field} {op}.',
                )
            )

    return parameters
