import contextlib
import json
import logging
import random
import string
from urllib.parse import urlparse, urlunparse

from ddtrace import tracer
from django.conf import settings
from django.db.models import Count
from django.http import Http404
from drf_spectacular.utils import extend_schema
from httpx import HTTPError
from opensearchpy import RequestError
from rest_framework import exceptions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.pagination import _positive_int
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from backend.api.cache import cache_response
from backend.api.groups.serializers import GroupSerializer, batch_cover_thumbnails
from backend.api.images.filters import InvalidFilterError, OSFilterBackend, os_image_filter_params
from backend.api.images.serializers import (
    CountSerializer,
    ImageAttributesSerializer,
    ImageIdSerializer,
    ImageIdWithAttributesSerializer,
    ImageLatentCreateSerializer,
    ImageLatentTypeSerializer,
    ListOSImageParamsSerializer,
    NumberSerializer,
    OSImageAggregateSerializer,
    OSImageBucketSerializer,
    OSImageBulkUpdateSerializer,
    OSImageCatalogParamsSerializer,
    OSImageCreateSerializer,
    OSImageFacetsParamsSerializer,
    OSImageSegmentationSerializer,
    OSImageSerializer,
    OSImageUpdateSerializer,
    PaginatedOSImageSerializer,
    RandomOSImageParamsSerializer,
    RelatedOSImageListSerializer,
    RetrieveOSImageParamsSerializer,
    SimilarOSImageListSerializer,
    SimilarOSImageParamsSerializer,
    SimilarToOSImageParamsSerializer,
    SimilarToTextSerializer,
    SimilarToVectorSerializer,
)
from backend.dataroom.exceptions import LatentTypeValidationError, MissingEmbeddingError, SaveConflictError
from backend.dataroom.models.attributes import AttributesFieldNotFoundError, AttributesSchema
from backend.dataroom.models.group import Membership
from backend.dataroom.models.os_image import OSAttribute, OSAttributes, OSFieldType, OSImage, OSLatent, OSLatents
from backend.dataroom.opensearch import OS, OSBulkIndex
from backend.dataroom.utils.coca_text_encoder import encode_text as encode_text_local
from backend.dataroom.utils.fetch_embedding import fetch_coca_embedding_for_text
from backend.dataroom.utils.ramsam import get_ramsam_segmentation
from backend.dataroom.utils.vectors import normalize_similarity, normalize_vector

logger = logging.getLogger(__name__)

BULK_ADD_ATTRIBUTES_LIMIT = 100

BULK_IMAGES_LIMIT = 50


class ImageViewSet(ViewSet):
    search_after_param = 'cursor'
    partitions_count_param = 'partitions_count'
    partition_param = 'partition'

    def _check_api_writes_disabled(self):
        if settings.API_DISABLE_IMAGE_WRITES:
            raise exceptions.PermissionDenied('Writes are temporarily disabled')

    def _get_partition_params(self):
        partitions_count = self.request.query_params.get(self.partitions_count_param)
        partition = self.request.query_params.get(self.partition_param)

        if (partitions_count is not None and partition is None) or (partitions_count is None and partition is not None):
            raise exceptions.ValidationError(
                f'Both "{self.partitions_count_param}" and "{self.partition_param}" parameters must be provided'
            )

        if partitions_count and partition:
            try:
                partitions_count = _positive_int(partitions_count, strict=True, cutoff=None)
            except ValueError as e:
                raise exceptions.ValidationError(f'Invalid "{self.partitions_count_param}" parameter') from e
            try:
                partition = _positive_int(partition, strict=False, cutoff=None)
            except ValueError as e:
                raise exceptions.ValidationError(f'Invalid "{self.partition_param}" parameter') from e

            num_shards = OSImage.get_num_shards()
            if partitions_count < 2 or partitions_count > num_shards:
                raise exceptions.ValidationError(
                    f'"{self.partitions_count_param}" should be between 2 and {num_shards}'
                )
            if partition >= partitions_count:
                raise exceptions.ValidationError(
                    f'"{self.partition_param}" should be between 0 and {partitions_count - 1}'
                )

        else:
            partitions_count = None
            partition = None

        return partitions_count, partition

    def _get_next_url(self, result):
        if not result.hits:
            return None
        last_hit = result.hits[-1]
        search_after = last_hit.meta.sort[0]
        parsed_url = urlparse(self.request.build_absolute_uri())
        params = self.request.query_params.copy()
        params[self.search_after_param] = str(search_after)
        return urlunparse(parsed_url._replace(query=params.urlencode()))

    def _get_object(self, image_id, fields=None):
        try:
            return OSImage.objects.get(image_id, fields=fields)
        except OSImage.DoesNotExist as e:
            raise Http404(f'OSImage with id "{image_id}" does not exist') from e

    def get_object(self, fields=None):
        return self._get_object(self.kwargs['pk'], fields=fields)

    def get_search(self, fields=None, search_after=None, sort=None):
        return OSImage.objects.search(fields=fields, search_after=search_after, sort=sort)

    def filter_search(self, search, exclude_field=None):
        backend = OSFilterBackend()
        try:
            search = backend.filter_search(self.request, search, self, exclude_field=exclude_field)
        except InvalidFilterError as e:
            raise exceptions.ValidationError(str(e)) from e
        except AttributesFieldNotFoundError as e:
            raise exceptions.ValidationError(str(e)) from e
        except LatentTypeValidationError as e:
            raise exceptions.ValidationError(e.message) from e
        return search

    def limit_page_size(self, search, page_size):
        return search.extra(size=page_size)

    def partition_search(self, search):
        """
        Partitioning is done on the OpenSearch shards which are selected based on the partition and partitions_count.
        """
        partitions_count, partition = self._get_partition_params()
        if partitions_count is not None and partition is not None:
            all_shards = list(range(OSImage.get_num_shards()))  # shard IDs are always sequential
            selected_shards = [str(s) for s in all_shards[partition::partitions_count]]
            return search.params(preference=f'_shards:{",".join(selected_shards)}')
        return search

    @tracer.wrap()
    @extend_schema(parameters=[RetrieveOSImageParamsSerializer], responses=OSImageSerializer)
    def retrieve(self, request, *args, **kwargs):
        params_serializer = RetrieveOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()

        obj = self.get_object(fields=fields)

        return Response(obj.to_json(fields=fields, return_latents=return_latents))

    @cache_response
    @tracer.wrap()
    @extend_schema(
        parameters=[
            ListOSImageParamsSerializer,
            *os_image_filter_params(),
        ],
        responses=PaginatedOSImageSerializer,
    )
    def list(self, request, *args, **kwargs):
        params_serializer = ListOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()
        search_after = params_serializer.get_search_after()

        search = self.partition_search(
            self.limit_page_size(
                self.filter_search(
                    self.get_search(fields=fields, search_after=search_after),
                ),
                page_size=params_serializer.get_page_size(),
            ),
        )
        result = search.execute()
        next_url = self._get_next_url(result)
        images = OSImage.list_from_hits(result.hits)

        return Response(
            {
                'next': next_url,
                'results': [image.to_json(fields=fields, return_latents=return_latents) for image in images],
            }
        )

    @tracer.wrap()
    @extend_schema(
        parameters=[
            RandomOSImageParamsSerializer,
            *os_image_filter_params(),
        ],
        responses=PaginatedOSImageSerializer,
    )
    @action(detail=False, methods=['get'])
    def random(self, request):
        params_serializer = RandomOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()

        # get params
        prefix_length = params_serializer.get_prefix_length()
        num_prefixes = params_serializer.get_num_prefixes()

        # generate random prefixes
        hex_chars = string.hexdigits.lower()[:16]
        random_prefixes = ['sha256:' + ''.join(random.choices(hex_chars, k=prefix_length)) for _ in range(num_prefixes)]

        # add to search
        search = self.filter_search(self.get_search(fields=fields, sort='_doc'))

        filters = []
        for prefix in random_prefixes:
            filters.append({"prefix": {"image_hash": prefix}})
        search = search.filter("bool", should=filters, minimum_should_match=1)

        search = self.limit_page_size(search, page_size=params_serializer.get_page_size())

        result = search.execute()

        images = OSImage.list_from_hits(result.hits)
        return Response(
            {
                'next': None,
                'results': [image.to_json(fields=fields, return_latents=return_latents) for image in images],
            }
        )

    @tracer.wrap()
    @extend_schema(parameters=[*os_image_filter_params()], responses=CountSerializer)
    @action(detail=False, methods=['get'])
    def count(self, request):
        s = self.partition_search(self.filter_search(self.get_search(sort='_doc')))
        count = s.count()
        return Response({'count': count})

    @tracer.wrap()
    @extend_schema(parameters=[*os_image_filter_params()])
    @action(detail=False, methods=['post'])
    def aggregate(self, request):
        serializer = OSImageAggregateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        search = self.partition_search(self.filter_search(self.get_search(sort='_doc')))
        search.aggs.metric(
            name='agg',
            agg_type=serializer.validated_data['type'],
            field=serializer.validated_data['field'],
        )
        try:
            result = search.execute()
        except RequestError as e:
            if 'not supported for aggregation' in str(e):
                return Response(
                    {'field': ['This field type is not supported for this aggregation']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise
        return Response(result.aggregations.agg.to_dict())

    @tracer.wrap()
    @extend_schema(parameters=[*os_image_filter_params()])
    @action(detail=False, methods=['post'])
    def bucket(self, request):
        serializer = OSImageBucketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        search = self.partition_search(self.filter_search(self.get_search(sort='_doc')))
        search.aggs.bucket(
            name='agg',
            agg_type='terms',
            field=serializer.validated_data['field'],
            size=serializer.validated_data['size'],
        )
        result = search.execute()
        return Response(result.aggregations.agg.to_dict())

    # Map logical field names → OpenSearch field names for terms aggregations
    # Accepts both frontend keys (tag, dataset) and backend keys (tags, datasets)
    TERMS_FIELDS = {
        'source': 'source',
        'tag': 'tags',
        'tags': 'tags',
        'dataset': 'datasets',
        'datasets': 'datasets',
        'duplicate_state': 'duplicate_state',
        'aspect_ratio_fraction': 'aspect_ratio_fraction',
        'latent': None,  # latent types are separate OS fields; not supported via terms
    }
    NUMERIC_FACET_FIELDS = {'width', 'height', 'short_edge', 'pixel_count', 'aspect_ratio'}
    # Terms-agg size for facets. Matches the catalog safety cap so filter-aware counts cover
    # every value the catalog can expose: a terms agg only does extra work up to the ACTUAL
    # cardinality, so a high ceiling costs nothing at typical scale, and at size >= cardinality
    # the per-shard top-N truncation (and its doc_count_error) disappears entirely.
    FACET_TERMS_SIZE = 50000

    @tracer.wrap()
    @extend_schema(parameters=[*os_image_filter_params()])
    @action(detail=False, methods=['get'])
    def facets(self, request):
        """Return aggregation facets for one or more fields. Applies all current filters,
        optionally excluding one field (for self-exclusion in faceted search)."""
        params_ser = OSImageFacetsParamsSerializer(data=request.query_params)
        params_ser.is_valid(raise_exception=True)

        requested = [f.strip() for f in params_ser.validated_data['fields'].split(',') if f.strip()]
        exclude_field = params_ser.validated_data.get('exclude_field')

        search = self.filter_search(self.get_search(sort='_doc'), exclude_field=exclude_field)
        search = search.extra(size=0)

        for field in requested:
            agg_name = field.replace(':', '_')  # safe aggregation key (attr:foo → attr_foo)
            if field in self.TERMS_FIELDS:
                os_field = self.TERMS_FIELDS[field]
                if os_field is not None:
                    search.aggs.bucket(name=agg_name, agg_type='terms', field=os_field, size=self.FACET_TERMS_SIZE)
            elif field in self.NUMERIC_FACET_FIELDS:
                search.aggs.bucket(name=f'{agg_name}_stats', agg_type='stats', field=field)
            elif field.startswith('attr:'):
                attr_name = field[5:]
                os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
                attr = OSAttribute(name=attr_name, value=None, os_type=os_type, is_indexed=True)
                if os_type in (OSFieldType.DOUBLE, OSFieldType.LONG):
                    # Numeric attributes: use stats aggregation (same as NUMERIC_FACET_FIELDS)
                    search.aggs.bucket(name=f'{agg_name}_stats', agg_type='stats', field=attr.os_name)
                else:
                    search.aggs.bucket(
                        name=agg_name, agg_type='terms', field=attr.os_name_keyword, size=self.FACET_TERMS_SIZE
                    )

        try:
            result = search.execute()
        except RequestError as e:
            if 'not supported for aggregation' in str(e):
                return Response(
                    {'error': 'One or more fields are not supported for aggregation'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        # Collect all fields that used stats aggregation (builtins + numeric attrs)
        # so we can compute histograms and build the right response shape for them.
        numeric_agg_fields = {}  # field -> os_field_name for histogram
        for field in requested:
            if field in self.NUMERIC_FACET_FIELDS:
                numeric_agg_fields[field] = field
            elif field.startswith('attr:'):
                attr_name = field[5:]
                os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
                if os_type in (OSFieldType.DOUBLE, OSFieldType.LONG):
                    attr = OSAttribute(name=attr_name, value=None, os_type=os_type, is_indexed=True)
                    numeric_agg_fields[field] = attr.os_name

        # For numeric fields, compute histogram interval from stats and run a second query
        hist_data = {}  # field -> list of buckets
        if numeric_agg_fields:
            hist_search = self.filter_search(self.get_search(sort='_doc'), exclude_field=exclude_field)
            hist_search = hist_search.extra(size=0)
            hist_agg_names = []
            for field, os_field in numeric_agg_fields.items():
                agg_name = field.replace(':', '_')
                stats_agg = result.aggregations[f'{agg_name}_stats']
                if stats_agg.count and stats_agg.max is not None and stats_agg.min is not None:
                    data_range = stats_agg.max - stats_agg.min
                    if data_range == 0:
                        interval = 1
                    else:
                        interval = data_range / 100
                        if interval >= 10:
                            interval = round(interval / 10) * 10 or 10
                        elif interval >= 1:
                            interval = round(interval)
                        # For small ranges (e.g. 0-1), keep fractional intervals
                        # rounded to 2 significant digits
                        elif interval >= 0.01:
                            interval = round(interval, 2)
                        else:
                            interval = float(f'{interval:.2g}')
                    hist_name = f'{agg_name}_hist'
                    hist_search.aggs.bucket(
                        name=hist_name,
                        agg_type='histogram',
                        field=os_field,
                        interval=interval,
                    )
                    hist_agg_names.append((field, hist_name))
            if hist_agg_names:
                hist_result = hist_search.execute()
                for field, hist_name in hist_agg_names:
                    hist_data[field] = hist_result.aggregations[hist_name].to_dict().get('buckets', [])

        response = {}
        for field in requested:
            agg_name = field.replace(':', '_')
            if field in numeric_agg_fields:
                stats_agg = result.aggregations[f'{agg_name}_stats']
                response[field] = {
                    'stats': stats_agg.to_dict(),
                    'histogram': hist_data.get(field, []),
                }
            else:
                agg = result.aggregations.get(agg_name)
                if agg:
                    response[field] = {'buckets': agg.to_dict().get('buckets', [])}
                else:
                    response[field] = {'buckets': []}

        return Response(response)

    # Discrete fields whose distinct-value set can grow unbounded. The frontend loads
    # these once via `field_catalog`, caches them client-side, and filters locally —
    # instead of only ever seeing the top-N most frequent values (as `facets` returns).
    CATALOG_FIELDS = {'source', 'tag', 'tags', 'dataset', 'datasets'}
    # Composite-agg page size. Every page re-runs the aggregation over the whole index, so
    # total cost scales with ceil(cardinality / page_size) full passes — at prod's tag
    # cardinality (tens of thousands), 1000/page meant dozens of passes and ~80s responses.
    # Matching the catalog cap makes a single pass cover everything the catalog can return
    # (pagination only remains as the mechanism to detect hitting the cap); the ceiling is
    # OpenSearch's search.max_buckets (65,535), and `facets` already requests 50k buckets.
    _CATALOG_PAGE_SIZE = FACET_TERMS_SIZE
    # Safety backstop so a pathological cardinality can't build an unbounded response.
    # At the expected scale (hundreds to low thousands) this is never reached. Kept equal
    # to FACET_TERMS_SIZE so filter-aware facet counts cover the whole catalog.
    _CATALOG_MAX_BUCKETS = FACET_TERMS_SIZE

    def _catalog_os_field(self, field):
        """Resolve a requested catalog field to its OpenSearch keyword field, or None if unsupported."""
        if field in self.CATALOG_FIELDS:
            return self.TERMS_FIELDS[field]
        if field.startswith('attr:'):
            attr_name = field[5:]
            os_type = AttributesSchema.get_os_type_for_field_name(attr_name)
            if os_type in (OSFieldType.DOUBLE, OSFieldType.LONG):
                return None  # numeric attributes are ranges, not term catalogs
            attr = OSAttribute(name=attr_name, value=None, os_type=os_type, is_indexed=True)
            return attr.os_name_keyword
        return None

    def _collect_catalog_values(self, os_field):
        """Collect every distinct value of ``os_field`` with its global doc count.

        Delegates to ``counts_by_field_exhaustive`` (a paged composite aggregation), so the
        result is complete and exact at any cardinality — unlike a plain ``terms`` agg with
        a capped ``size``, which shard-truncates. Returns ``(values, truncated)``.
        """
        counts, truncated = OSImage.objects.counts_by_field_exhaustive(
            os_field, page_size=self._CATALOG_PAGE_SIZE, max_buckets=self._CATALOG_MAX_BUCKETS
        )
        return [{'key': key, 'doc_count': count} for key, count in counts.items()], truncated

    @cache_response
    @tracer.wrap()
    @extend_schema(parameters=[OSImageCatalogParamsSerializer])
    @action(detail=False, methods=['get'])
    def field_catalog(self, request):
        """Return the complete, unfiltered value catalog for one or more discrete fields.

        Unlike ``facets``, this ignores the active user filters: it returns the full universe
        of values (with global counts) plus the total distinct count, so the frontend can cache
        it for a long time and filter locally. Response shape per field::

            {"source": {"values": [{"key": "...", "doc_count": N}, ...], "total": M, "truncated": false}}
        """
        params_ser = OSImageCatalogParamsSerializer(data=request.query_params)
        params_ser.is_valid(raise_exception=True)
        requested = [f.strip() for f in params_ser.validated_data['fields'].split(',') if f.strip()]

        # The manager search keeps the standard visibility filters (e.g. not-deleted), but no
        # user filter chips and no partitioning apply — the catalog is the global value universe.
        response = {}
        for field in requested:
            os_field = self._catalog_os_field(field)
            if os_field is None:
                return Response(
                    {'fields': [f'Field "{field}" does not support a value catalog.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                values, truncated = self._collect_catalog_values(os_field)
            except RequestError as e:
                if 'not supported for aggregation' in str(e):
                    return Response(
                        {'fields': [f'Field "{field}" is not supported for aggregation.']},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                raise
            if truncated:
                logger.warning(
                    'field_catalog truncated for field "%s" at %d values (cap=%d)',
                    field,
                    len(values),
                    self._CATALOG_MAX_BUCKETS,
                )
            response[field] = {'values': values, 'total': len(values), 'truncated': truncated}

        return Response(response)

    @tracer.wrap()
    @extend_schema(request=OSImageCreateSerializer)
    def create(self, request, *args, **kwargs):
        self._check_api_writes_disabled()

        if 'multipart/form-data' in request.content_type and request.data.get('json_0', None):
            return self._handle_bulk_create(request, *args, **kwargs)

        return self._handle_single_create(request, *args, **kwargs)

    @tracer.wrap()
    def _handle_bulk_create(self, request, *args, **kwargs):
        serializers = []
        image_ids = []
        image_hashes = []
        for key, value in request.data.items():
            if key.startswith('json_'):
                index = key[5:]

                # parse json
                try:
                    data = json.loads(value)
                except (ParseError, TypeError):
                    return Response({'error': f'Invalid JSON for {key}'}, status=status.HTTP_400_BAD_REQUEST)

                # add the image
                image_file = request.FILES.get(f'image_{index}', None)
                if image_file:
                    data['image'] = image_file

                # validate serializer
                serializer = OSImageCreateSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                serializers.append(serializer)

                # add other data
                serializer.validated_data['original_url'] = data.get('image_url', None)
                if not serializer.validated_data.get('image_hash', None):
                    serializer.validated_data['image_hash'] = OSImage.get_image_hash(serializer.validated_data['image'])
                serializer.validated_data['author'] = self.request.user.email

                # validate all images in batch are unique
                if serializer.validated_data['id'] in image_ids:
                    return Response(
                        {'error': f"Image with ID '{serializer.validated_data['id']}' appears multiple times in bulk"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if serializer.validated_data['image_hash'] in image_hashes:
                    return Response(
                        {
                            'error': f"Image hash with ID '{serializer.validated_data['id']}' appears multiple times "
                            f"in bulk",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                image_ids.append(serializer.validated_data['id'])
                image_hashes.append(serializer.validated_data['image_hash'])

        # check if any images with the given IDs already exist
        existing = OSImage.all_objects.get_multiple(
            [s.validated_data['id'] for s in serializers],
            fields=['id'],
            number=BULK_IMAGES_LIMIT,
        )
        if existing:
            existing_str = ', '.join([f"'{e.id}'" for e in existing])
            return Response(
                {
                    'error': f'Images with IDs {existing_str} already exist',
                },
                status=status.HTTP_409_CONFLICT,
            )

        # check if any images with the same hash already exist
        existing = OSImage.all_objects.get_multiple_by_hash(
            [s.validated_data['image_hash'] for s in serializers],
            fields=['id'],
            number=BULK_IMAGES_LIMIT,
        )
        if existing:
            existing_str = ', '.join([f"'{e.id}'" for e in existing])
            return Response(
                {
                    'error': f'Image hashes with IDs {existing_str} already exist',
                },
                status=status.HTTP_409_CONFLICT,
            )

        # save images in bulk
        # TODO: log updates
        with OSBulkIndex() as os_bulk:
            for serializer in serializers:
                # save image
                serializer.create(serializer.validated_data, bulk_index=os_bulk)

        return Response({'created': [s.validated_data['id'] for s in serializers]}, status=status.HTTP_200_OK)

    @tracer.wrap()
    def _handle_single_create(self, request, *args, **kwargs):
        instance = None
        image_url = None

        if 'multipart/form-data' in request.content_type:
            # multipart/form-data request with image file
            image = request.FILES.get('image', None)
            if not image:
                return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)

            # parse the json inside the request
            data = request.data.get('json', '{}')
            try:
                data = json.loads(data)
            except (ParseError, TypeError):
                return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)

            # add the image to the data
            data['image'] = image

        else:
            # regular JSON request
            data = request.data

            # check if image from this URL already exists
            image_url = data.get('image_url', None)
            if image_url:
                with contextlib.suppress(OSImage.DoesNotExist):
                    instance = OSImage.all_objects.get_by_original_url(original_url=image_url)

        if not instance:
            # new image, create it
            serializer = OSImageCreateSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            image_file = serializer.validated_data['image']

            # check if same ID already exists
            try:
                same_id_image = OSImage.all_objects.get(serializer.validated_data['id'])
            except OSImage.DoesNotExist:
                pass
            else:
                deleted_msg = ' as a deleted image' if same_id_image.is_deleted else ''
                return Response(
                    {
                        'error': f'The provided ID already exists in the database{deleted_msg}. '
                        'Make sure all your IDs are unique and can trace back to the original image.',
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # check if same hash already exists
            image_hash = serializer.validated_data.get('image_hash', None)
            if not image_hash:
                image_hash = OSImage.get_image_hash(image_file)
            try:
                same_hash_image = OSImage.all_objects.get_by_hash(image_hash)
            except OSImage.DoesNotExist:
                pass
            else:
                if same_hash_image.is_same_image(image_file):
                    deleted_msg = ' as a deleted image' if same_hash_image.is_deleted else ''
                    return Response(
                        {
                            'error': f'Image with the same hash already exists in the database{deleted_msg}. '
                            'Make sure all your images are unique.',
                            'image_id': same_hash_image.id,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            # save image
            try:
                serializer.save(
                    author=self.request.user.email,
                    image_hash=image_hash,
                    original_url=image_url,
                )
            except SaveConflictError as e:
                return Response(
                    {'error': e.description},
                    status=status.HTTP_409_CONFLICT,
                )

            instance = serializer.instance

        # response
        return Response(instance.to_json(), status=status.HTTP_201_CREATED)

    @tracer.wrap()
    @extend_schema(request=OSImageUpdateSerializer)
    def update(self, request, *args, **kwargs):
        self._check_api_writes_disabled()

        if 'multipart/form-data' in request.content_type:
            return self._update_image_with_latents(request=request)
        return self._update_image(data=request.data)

    @tracer.wrap()
    def _update_image_with_latents(self, request):
        """
        Update an image with multiple latents in a single request.

        Example request:

            files = [
                ('json_0', '{"source": "test", "attributes": {}, "tags": []}'),
                ('latent_json_0', '{"latent_type": "test1"}'),
                ('latent_0', <file>),
                ('latent_json_1', '{"latent_type: "test2"}'),
                ('latent_1', <file>),
            ]
        """
        # parse the request data
        data = {}
        for key, value in request.data.items():
            if key == 'json':
                # image data
                try:
                    image_data = json.loads(value)
                except (ParseError, TypeError):
                    return Response({'error': 'Invalid JSON for image'}, status=status.HTTP_400_BAD_REQUEST)
                data.update(image_data)

            elif key.startswith('latent_json_'):
                # latent data
                index = key[12:]

                # parse latent json
                try:
                    latent_data = json.loads(value)
                except (ParseError, TypeError):
                    return Response({'error': f'Invalid JSON for latent {key}'}, status=status.HTTP_400_BAD_REQUEST)

                # add the latent
                latent_file = request.FILES.get(f'latent_{index}', None)
                if 'latents' not in data:
                    data['latents'] = []
                final_latent_data = {
                    'latent_type': latent_data.get('latent_type'),
                    'file': latent_file,
                }
                data['latents'].append(final_latent_data)

        return self._update_image(data=data)

    @tracer.wrap()
    def _update_image(self, data):
        # validate serializer
        serializer = OSImageUpdateSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        # validate all latents are unique
        latent_types = []
        for latent in serializer.validated_data.get('latents', []):
            if latent['latent_type'] in latent_types:
                return Response(
                    {'error': f"Latent type '{latent['latent_type']}' appears multiple times in update"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            latent_types.append(latent['latent_type'])

        # save image
        image = self.get_object()
        updated_fields = list(serializer.validated_data.keys())
        # TODO: log update
        # old_date_updated = image.date_updated

        for field, value in serializer.validated_data.items():
            if field == 'attributes':
                value = OSAttributes.from_json(value)
                setattr(image, field, value)
            elif field == 'latents':
                try:
                    value = OSLatents.from_json(value)
                except LatentTypeValidationError as e:
                    return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
                setattr(image, field, value)
            elif field == 'coca_embedding':
                image.coca_embedding_exists = value is not None
                image.coca_embedding_vector = value
                image.coca_embedding_author = self.request.user.email
            else:
                setattr(image, field, value)

        if updated_fields:
            try:
                image.save(fields=updated_fields, latent_types=latent_types)
            except SaveConflictError as e:
                return Response({'error': e.description}, status=status.HTTP_409_CONFLICT)
            except LatentTypeValidationError as e:
                return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(image.to_json(include_fields=updated_fields), status=status.HTTP_200_OK)

    @action(detail=False, methods=['put'])
    def bulk_update(self, request, *args, **kwargs):
        self._check_api_writes_disabled()

        if not isinstance(request.data, list):
            return Response({'error': "Expected a list of images to update"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.data:
            return Response({'error': "Empty list provided"}, status=status.HTTP_400_BAD_REQUEST)

        # validate each image update
        valid_serializers = []
        for item in request.data:
            serializer = OSImageBulkUpdateSerializer(data=item)
            serializer.is_valid(raise_exception=True)
            valid_serializers.append(serializer)

        # validate bulk size
        if len(valid_serializers) > BULK_IMAGES_LIMIT:
            return Response(
                {'error': f"Number of items in bulk exceeds maximum limit of {BULK_IMAGES_LIMIT} items."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # get all images with one query
        image_ids = [serializer.validated_data['id'] for serializer in valid_serializers]
        images_by_id = {
            image.id: image
            for image in OSImage.all_objects.get_multiple(image_ids, fields=['id'], number=BULK_IMAGES_LIMIT)
        }
        if len(image_ids) != len(images_by_id):
            missing = set(image_ids) - set(images_by_id.keys())
            missing = [f'"{m}"' for m in missing]
            return Response(
                {
                    'error': f'Images with IDs {", ".join(list(missing))} were not found',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # update images in bulk
        # TODO: log updates
        try:
            with OSBulkIndex() as os_bulk:
                for serializer in valid_serializers:
                    image = images_by_id[serializer.validated_data['id']]
                    updated_fields = []

                    for field, value in serializer.validated_data.items():
                        if field == 'id':
                            continue
                        elif field == 'source':
                            image.source = value
                            updated_fields.append('source')
                        elif field == 'attributes':
                            image.attributes = OSAttributes.from_json(value)
                            updated_fields.append('attributes')
                        elif field == 'latents':
                            raise NotImplementedError('Bulk update images with latents is not supported')
                        elif field == 'tags' and value is not None:
                            image.tags = value
                            updated_fields.append('tags')
                        elif field == 'coca_embedding':
                            image.coca_embedding_exists = value is not None
                            image.coca_embedding_vector = value
                            image.coca_embedding_author = self.request.user.email
                            updated_fields.append('coca_embedding')

                    image.save(fields=updated_fields, bulk_index=os_bulk)
        except SaveConflictError as e:
            return Response(
                {'error': e.description},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({'updated': image_ids}, status=status.HTTP_200_OK)

    @tracer.wrap()
    def destroy(self, request, *args, **kwargs):
        self._check_api_writes_disabled()

        image = self.get_object()
        image.delete()

        # TODO: log deletion

        return Response(status=status.HTTP_204_NO_CONTENT)

    @tracer.wrap()
    @action(detail=True, methods=['put'])
    def add_attributes(self, request, pk=None):
        self._check_api_writes_disabled()

        image = self.get_object()

        image_attributes_serializer = ImageAttributesSerializer(data=self.request.data)
        image_attributes_serializer.is_valid(raise_exception=True)

        # old_attributes = dict(image.attributes.to_json())
        # old_date_updated = image.date_updated

        image.attributes.update(image_attributes_serializer.validated_data['attributes'])
        try:
            image.save(fields=['attributes'])
        except SaveConflictError as e:
            return Response(
                {'error': e.description},
                status=status.HTTP_409_CONFLICT,
            )

        # TODO: log update

        return Response(image.to_json(), status=status.HTTP_200_OK)

    @tracer.wrap()
    @action(detail=False, methods=['post'])
    def add_attributes_bulk(self, request):
        self._check_api_writes_disabled()

        if len(self.request.data) == 0:
            return Response({'error': "Empty list provided"}, status=status.HTTP_400_BAD_REQUEST)
        if len(self.request.data) > BULK_ADD_ATTRIBUTES_LIMIT:
            return Response(
                {'error': f"Batch size exceeds maximum limit of {BULK_ADD_ATTRIBUTES_LIMIT} items."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializers_list = ImageIdWithAttributesSerializer(data=self.request.data, many=True)
        serializers_list.is_valid(raise_exception=True)

        image_ids = [image['image_id'] for image in serializers_list.validated_data]

        added_count = 0
        merged_count = 0
        search = (
            OSImage.objects.search(
                fields=['id', 'attributes'],
            )
            .filter('terms', id=image_ids)
            .extra(size=BULK_ADD_ATTRIBUTES_LIMIT)
        )
        result = search.execute()
        images = {image.id: image for image in OSImage.list_from_hits(result.hits)}

        try:
            with OSBulkIndex() as os_bulk:
                for image_serializer in serializers_list.validated_data:
                    image = images[image_serializer['image_id']]
                    # old_attributes = dict(image.attributes.to_json())
                    # old_date_updated = image.date_updated
                    if image.attributes:
                        merged_count += 1
                    else:
                        added_count += 1
                    image.attributes.update(image_serializer['attributes'])
                    image.save(fields=['attributes'], bulk_index=os_bulk)
                    # TODO: log update
        except SaveConflictError as e:
            return Response(
                {'error': e.description},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({'added': added_count, 'merged': merged_count}, status=status.HTTP_200_OK)

    @tracer.wrap()
    @action(detail=True, methods=['post'])
    def set_latent(self, request, pk=None):
        self._check_api_writes_disabled()

        # multipart/form-data request with file
        latent_file = request.FILES.get('file', None)
        if not latent_file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # parse the json inside the request
        data = request.data.get('json', '{}')
        try:
            data = json.loads(data)
        except (ParseError, TypeError):
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)

        # add the file to the data
        data['file'] = latent_file

        # create the serializer
        latent_serializer = ImageLatentCreateSerializer(data=data)
        latent_serializer.is_valid(raise_exception=True)

        # save the latent
        try:
            latent = OSLatent.from_json(latent_serializer.validated_data)
        except LatentTypeValidationError as e:
            return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

        image = self.get_object(fields=['latents', 'date_updated'])
        if latent.latent_type in image.latents:
            pass
            # old_date_updated = image.date_updated
            # TODO: log update
        else:
            pass  # TODO: log create

        try:
            image.add_latent(latent)
        except SaveConflictError as e:
            return Response(
                {'error': e.description},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(image.to_json(fields=['id', 'latents', 'date_updated']), status=status.HTTP_200_OK)

    @tracer.wrap()
    @action(detail=True, methods=['post'])
    def delete_latent(self, request, pk=None):
        self._check_api_writes_disabled()

        image = self.get_object(fields=['latents', 'date_updated'])

        serializer = ImageLatentTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latent_type = serializer.validated_data['latent_type']

        if latent_type not in image.latents:
            return Response({'error': 'Latent not found'}, status=status.HTTP_404_NOT_FOUND)

        # old_date_updated = image.date_updated
        try:
            image.remove_latent(latent_type)
        except SaveConflictError as e:
            return Response(
                {'error': e.description},
                status=status.HTTP_409_CONFLICT,
            )

        # TODO: log delete

        return Response(image.to_json(fields=['id', 'latents', 'date_updated']), status=status.HTTP_200_OK)

    @tracer.wrap()
    @action(detail=True, methods=['post'])
    def similarity(self, request, pk=None):
        image = self.get_object(fields=['coca_embedding'])

        image_id_serializer = ImageIdSerializer(data=self.request.data)
        image_id_serializer.is_valid(raise_exception=True)

        other_image_id = image_id_serializer.validated_data['image_id']
        try:
            other_image = OSImage.objects.get(other_image_id)
        except OSImage.DoesNotExist:
            return Response(
                {'error': f'Image with ID "{other_image_id}" not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            similarity = image.get_similarity(other_image)
        except MissingEmbeddingError as e:
            return Response(
                {'error': f'Image "{e.image_id}" does not have an embedding'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'image_id_1': image.id,
                'image_id_2': other_image.id,
                'similarity': similarity,
            }
        )

    def _get_number_from_params(self, request, default_value=10, max_value=100):
        number = request.query_params.get('number', default_value)
        try:
            number = int(number)
        except (ValueError, TypeError):
            number = default_value
        else:
            number = min(max(number, 1), max_value)
        return number

    @tracer.wrap()
    @extend_schema(
        parameters=[
            SimilarOSImageParamsSerializer,
            *os_image_filter_params(),
        ],
        responses=SimilarOSImageListSerializer,
    )
    @action(detail=True, methods=['get'])
    def similar(self, request, pk=None):
        os_image = self.get_object(fields=['coca_embedding'])

        if not os_image.coca_embedding_exists:
            return Response(
                {'error': f'Image "{os_image.id}" does not have an embedding'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vector = os_image.coca_embedding_vector

        # filters
        params_serializer = SimilarOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        number = params_serializer.get_number()
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()
        search = self.limit_page_size(
            self.filter_search(self.get_search(fields=fields, sort='_score')),
            page_size=number,
        )
        body = search.to_dict()

        # add similarity search
        if 'must' not in body['query']['bool']:
            body['query']['bool']['must'] = []
        body['query']['bool']['must'].append(
            {
                "knn": {
                    "coca_embedding_vector": {
                        "vector": vector,
                        "k": number,
                    },
                },
            }
        )
        if 'must_not' not in body['query']['bool']:
            body['query']['bool']['must_not'] = []
        body["query"]["bool"]["must_not"].append({"match": {"id": os_image.id}})

        response = OS.client.search(index=search._index, body=body, **search._params)
        images = OSImage.list_from_hits(response['hits']['hits'])
        return Response(
            [
                image.to_json(
                    fields=fields,
                    return_latents=return_latents,
                    extra_data={"similarity": normalize_similarity(image.meta.score)},
                )
                for image in images
            ]
        )

    @tracer.wrap()
    @extend_schema(
        parameters=[SimilarToOSImageParamsSerializer],
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'image': {'type': 'string', 'format': 'binary'},
                    'json': {'type': 'string', 'description': 'JSON string containing parameters like "number"'},
                },
                'required': ['image'],
            }
        },
        responses=SimilarOSImageListSerializer,
    )
    @action(detail=False, methods=['post'])
    def similar_to_file(self, request):
        # multipart/form-data request with file
        image_file = request.FILES.get('image', None)
        if not image_file:
            return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)

        # parse the json inside the request
        data = request.data.get('json', '{}')
        try:
            data = json.loads(data)
        except (ParseError, TypeError):
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)

        num_serializer = NumberSerializer(data=data)
        num_serializer.is_valid(raise_exception=True)
        number = num_serializer.validated_data['number']

        params_serializer = SimilarToOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()

        search = self.limit_page_size(
            self.filter_search(self.get_search(fields=fields, sort='_score')),
            page_size=number,
        )
        body = search.to_dict()

        similar_images = OSImage.objects.find_similar_to_file(
            image_file=image_file,
            number=number,
            fields=fields,
            body=body,
        )

        return Response(
            [
                similar.to_json(
                    fields=fields,
                    return_latents=return_latents,
                    extra_data={"similarity": normalize_similarity(similar.meta.score)},
                )
                for similar in similar_images
            ]
        )

    @tracer.wrap()
    @extend_schema(
        parameters=[
            SimilarToOSImageParamsSerializer,
            *os_image_filter_params(),
        ],
        request=SimilarToVectorSerializer,
        responses=SimilarOSImageListSerializer,
    )
    @action(detail=False, methods=['post'])
    def similar_to_vector(self, request):
        serializer = SimilarToVectorSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        vector = serializer.validated_data['vector']
        number = serializer.validated_data['number']

        # filters
        params_serializer = SimilarToOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()
        search = self.limit_page_size(
            self.filter_search(self.get_search(fields=fields, sort='_score')),
            page_size=number,
        )
        body = search.to_dict()

        similar_images = OSImage.objects.find_similar(
            vector=vector,
            number=number,
            fields=fields,
            body=body,
        )

        return Response(
            [
                image.to_json(
                    fields=fields,
                    return_latents=return_latents,
                    extra_data={"similarity": normalize_similarity(image.meta.score)},
                )
                for image in similar_images
            ]
        )

    @tracer.wrap()
    @extend_schema(
        parameters=[
            SimilarToOSImageParamsSerializer,
            *os_image_filter_params(),
        ],
        request=SimilarToTextSerializer,
        responses=SimilarOSImageListSerializer,
    )
    @action(detail=False, methods=['post'])
    def similar_to_text(self, request):
        serializer = SimilarToTextSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data['text']
        number = serializer.validated_data['number']

        error_response = Response({'error': 'Unable to fetch embedding for text'}, status=status.HTTP_400_BAD_REQUEST)

        vector = None
        try:
            vector = encode_text_local(text)
        except Exception:
            logger.warning("Local text encoder failed, falling back to API", exc_info=True)

        if not vector:
            try:
                vector = fetch_coca_embedding_for_text(text)
            except HTTPError as e:
                logger.error(e)
                return error_response

        if not vector:
            return error_response

        vector = normalize_vector(vector)

        # filters
        params_serializer = SimilarToOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()
        search = self.limit_page_size(
            self.filter_search(self.get_search(fields=fields, sort='_score')),
            page_size=number,
        )
        body = search.to_dict()

        similar_images = OSImage.objects.find_similar(
            vector=vector,
            number=number,
            fields=fields,
            body=body,
        )

        return Response(
            [
                image.to_json(
                    fields=fields,
                    return_latents=return_latents,
                    extra_data={"similarity": normalize_similarity(image.meta.score)},
                )
                for image in similar_images
            ]
        )

    @extend_schema(responses=OSImageSegmentationSerializer)
    @action(detail=True, methods=['get'])
    def segmentation(self, request, pk=None):
        image = self.get_object(fields=['latents', 'width', 'height'])

        captions_latent_type = "latent_ramsam_caption_numpy"
        segments_latent_type = "segmentation_mask_ramsam"

        if captions_latent_type not in image.latents:
            return Response(
                {'error': f'Latent type "{captions_latent_type}" not found'}, status=status.HTTP_404_NOT_FOUND
            )
        captions_latent = image.latents.latents[captions_latent_type]

        if segments_latent_type not in image.latents:
            return Response(
                {'error': f'Latent type "{segments_latent_type}" not found'}, status=status.HTTP_404_NOT_FOUND
            )
        segments_latent = image.latents.latents[segments_latent_type]

        captions, segments = get_ramsam_segmentation(
            image_width=image.width,
            image_height=image.height,
            captions_file=captions_latent.file_object,
            segments_file=segments_latent.file_object,
        )

        return Response(
            {
                "captions": captions,
                "segments": segments,
            }
        )

    @action(detail=True, methods=['get'])
    def groups(self, request, pk=None):
        """List all (non-deleted) groups this image is a member of, hydrated.

        Response: [{group: {...}, role, metadata}]
        """
        memberships = list(
            Membership.objects.filter(image_id=pk, deleted_at__isnull=True, group__deleted_at__isnull=True)
            .select_related('group', 'group__author', 'group__type')
            .order_by('date_created')
        )
        # Bulk-fetch image_count for every group in the response in one query
        # so GroupSerializer.get_image_count doesn't fire one COUNT per group.
        group_ids = {m.group_id for m in memberships}
        counts = dict(
            Membership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True)
            .values('group_id')
            .annotate(c=Count('image_id', distinct=True))
            .values_list('group_id', 'c')
        )
        for m in memberships:
            m.group.image_count = counts.get(m.group_id, 0)

        # Batch the cover thumbnails for every group in one OS query (else the
        # serializer fetches one cover per group).
        cover_thumbnails = batch_cover_thumbnails([m.group for m in memberships])

        return Response(
            [
                {
                    'group': GroupSerializer(m.group, context={'cover_thumbnails': cover_thumbnails}).data,
                    'role': m.role,
                    'metadata': m.metadata,
                }
                for m in memberships
            ]
        )

    @extend_schema(parameters=[RetrieveOSImageParamsSerializer], responses=RelatedOSImageListSerializer)
    @action(detail=True, methods=['get'])
    def related(self, request, pk=None):
        # fields
        params_serializer = RetrieveOSImageParamsSerializer(data=self.request.query_params)
        params_serializer.is_valid(raise_exception=True)
        fields = params_serializer.get_fields_list()
        return_latents = params_serializer.get_latents_list()

        # never include related_images to prevent circular dependencies
        if 'related_images' in fields:
            fields.remove('related_images')

        # get all related images
        image = self.get_object(fields=['related_images'])
        related_images = []
        if image.related_images and image.related_images.images:
            for name, rel_id in image.related_images.images.items():
                try:
                    related_image = self._get_object(rel_id, fields=fields)
                except Http404:
                    # skip missing images
                    related_image = None
                related_images.append(
                    {
                        "name": name,
                        "image_id": rel_id,
                        "image": related_image.to_json(
                            fields=fields,
                            return_latents=return_latents,
                        )
                        if related_image
                        else None,
                    }
                )

        return Response(related_images)
