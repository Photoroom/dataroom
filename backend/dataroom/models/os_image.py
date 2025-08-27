import datetime
import hashlib
import logging
import re
import zoneinfo
from fractions import Fraction
from io import BytesIO

import numpy as np
from ddtrace import tracer
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from opensearchpy import AttrDict, NotFoundError, Search
from opensearchpy.exceptions import ConflictError
from opensearchpy.helpers.response import Hit
from PIL import Image

from backend.dataroom.choices import DuplicateState, OSFieldType
from backend.dataroom.exceptions import LatentTypeValidationError, MissingEmbeddingError, SaveConflictError
from backend.dataroom.models.attributes import AttributesFieldNotFoundError, AttributesSchema
from backend.dataroom.models.latents import LatentType
from backend.dataroom.models.tag import Tag
from backend.dataroom.opensearch import OS, OSBulkIndex
from backend.dataroom.utils.disable_storage_custom_domain import disable_storage_custom_domain
from backend.dataroom.utils.fetch_embedding import fetch_coca_embedding, fetch_coca_embedding_async
from backend.dataroom.utils.get_vector_for_image_file import get_vector_for_image_file
from backend.dataroom.utils.vectors import normalize_similarity, normalize_vector

logger = logging.getLogger('dataroom')


# Default limit is 89,478,485 pixels (approximately a 9000x9000 pixel image)
Image.MAX_IMAGE_PIXELS = 180_000_000


class OSLatent:
    def __init__(self, latent_type, file=None, file_object=None, is_mask=False):
        self.latent_type = latent_type
        self.file = file
        self._file_object = file_object
        self.is_mask = is_mask
        self.latent_type_instance = None
        self.is_removed = False

    @property
    def is_validated(self):
        return bool(self.latent_type_instance)

    @property
    def os_name_file(self):
        return f'latent_{self.latent_type}_file'

    @property
    def file_object(self):
        if not self._file_object:
            self._file_object = default_storage.open(self.file)
        return self._file_object

    @property
    def file_url(self):
        return default_storage.url(self.file) if self.file else None

    @property
    def file_direct_url(self):
        with disable_storage_custom_domain(default_storage):
            return default_storage.url(self.file) if self.file else None

    @classmethod
    @tracer.wrap()
    def from_json(cls, data):
        if data.get('file'):
            assert isinstance(data['file'], File)
        latent_type = cls(
            latent_type=data['latent_type'],
            file_object=data.get('file'),
        )
        latent_type.validate_latent_type()
        return latent_type

    def mark_as_removed(self):
        self.file = None
        self.is_removed = True

    def to_json(self):
        return {
            'latent_type': self.latent_type,
            'file_direct_url': self.file_direct_url,
            'is_mask': self.is_mask,
        }

    def validate_latent_type(self, prefetched_latent_types=None):
        # validate that the LatentType is configured and exists
        if prefetched_latent_types:
            prefetched_latent_types = {instance.name: instance for instance in prefetched_latent_types}
        if not self.is_validated:
            if prefetched_latent_types:
                latent_type_instance = prefetched_latent_types.get(self.latent_type)
            else:
                latent_type_instance = LatentType.objects.filter(name=self.latent_type).first()
            if latent_type_instance:
                self.latent_type_instance = latent_type_instance
                self.is_mask = latent_type_instance.is_mask
                return latent_type_instance
            else:
                raise LatentTypeValidationError(message=f"Latent type '{self.latent_type}' does not exist")


class OSLatents:
    def __init__(self, latents: dict[str, OSLatent] | None = None):
        if not latents:
            latents = {}
        self.latents = latents

    def __bool__(self):
        return bool(self.latents)

    def __contains__(self, item):
        return item in self.latents

    @classmethod
    def from_hit(cls, hit, latent_types_map):
        """Parse OSLatents from an OpenSearch hit"""
        latents = {}
        for key in hit:
            if key.startswith('latent_') and key.endswith('_file'):
                latent_type = key[len('latent_') : -len('_file')]
                file_key = key
                if hit[file_key] and latent_type in latent_types_map:
                    latents[latent_type] = OSLatent(
                        latent_type=latent_type,
                        file=hit[file_key],
                        is_mask=latent_types_map[latent_type].is_mask,
                    )
        return cls(latents=latents)

    @classmethod
    def from_json(cls, latents_list):
        """Parse OSLatents from a list of dictionaries"""
        latents = {}
        for data in latents_list:
            latent_type = data['latent_type']
            if latent_type in latents:
                raise LatentTypeValidationError(message=f"Duplicate latent type '{latent_type}'")
            latents[latent_type] = OSLatent.from_json(data)
        return cls(latents=latents)

    @classmethod
    def from_mapping(cls, mapping):
        """Parse an empty OSLatents object from OS mappings"""
        latents = {}
        for key in mapping:
            if key.startswith('latent_') and key.endswith('_file'):
                latent_type = key[len('latent_') : -len('_file')]
                latents[latent_type] = OSLatent(
                    latent_type=latent_type,
                )
        return cls(latents=latents)

    def to_json(self, return_latents=None):
        latents = []
        for latent_type, latent in self.latents.items():
            if return_latents and latent_type not in return_latents:
                continue
            latents.append(latent.to_json())
        return latents

    def to_doc(self):
        latents_dict = {}
        for latent in self.latents.values():
            latents_dict.update(
                {
                    latent.os_name_file: latent.file,
                }
            )
        return latents_dict

    def validate_latent_types(self):
        latent_types = self.latents.keys()
        latent_type_instances = LatentType.objects.filter(name__in=latent_types)
        for latent in self.latents.values():
            latent.validate_latent_type(prefetched_latent_types=latent_type_instances)


class OSAttribute:
    def __init__(self, name, value, os_type, is_indexed=False):
        self.name = name

        # validate the OS type
        if os_type not in OSFieldType.values:
            raise ValueError(f"Invalid OS type: {os_type}")
        self.os_type = os_type

        # validate objects are not indexed
        if os_type == OSFieldType.OBJECT and is_indexed:
            raise ValueError("Object attributes cannot be indexed")
        self.is_indexed = is_indexed

        # validate the value
        if os_type == OSFieldType.BOOLEAN and value is not None:
            value = str(value).lower()
            if value not in ['true', 'false']:
                raise ValueError(f"Invalid boolean value: {value}")
            value = value == 'true'
        elif os_type == OSFieldType.OBJECT and value is not None:
            # Validate that object values are valid JSON objects (dict)
            if not isinstance(value, dict):
                raise ValueError(f"Object attribute values must be dictionaries/objects, got {type(value)}")
        self.value = value

    def __repr__(self):
        return f'<OSAttribute {self.name}={self.value}>'

    @property
    def os_name(self):
        prefix = "attr" if self.is_indexed else "attr_noidx"
        return f'{prefix}_{self.name}_{self.os_type}'

    @property
    def os_name_keyword(self):
        """Text fields store an additional keyword field for exact matches"""
        if self.os_type == OSFieldType.TEXT:
            return self.os_name + '.keyword'
        return self.os_name


class OSAttributes:
    def __init__(self, attributes: dict[str, OSAttribute] | None = None):
        if not attributes:
            attributes = {}
        self.attributes = attributes

    def __bool__(self):
        return bool(self.attributes)

    def __contains__(self, item):
        return item in self.attributes

    @classmethod
    def from_hit(cls, hit):
        """Parse OSAttributes from an OpenSearch hit"""
        attributes = {}
        for key in hit:
            # Handle both indexed (attr_) and non-indexed (attr_noidx_) attributes
            is_indexed = None
            name = None

            if key.startswith('attr_noidx_'):
                is_indexed = False
                for os_type in OSFieldType.values:
                    if key.endswith(f'_{os_type}'):
                        name = key[len('attr_noidx_') : -len(f'_{os_type}')]
                        break
            elif key.startswith('attr_'):
                is_indexed = True
                for os_type in OSFieldType.values:
                    if key.endswith(f'_{os_type}'):
                        name = key[len('attr_') : -len(f'_{os_type}')]
                        break

            if name is not None and is_indexed is not None:
                try:
                    expected_type = AttributesSchema.get_os_type_for_field_name(name)
                except AttributesFieldNotFoundError:
                    # the field is not in the schema, so we ignore it
                    pass
                else:
                    if expected_type == os_type:
                        attributes[name] = OSAttribute(
                            name=name, value=hit[key], os_type=os_type, is_indexed=is_indexed
                        )
                    else:
                        # if the expected and indexed types don't match, we ignore the field
                        pass
        return cls(attributes=attributes)

    @classmethod
    def from_json(cls, attrs_dict):
        """Parse OSAttributes from a name-value dictionary"""
        if not attrs_dict:
            attrs_dict = {}
        attributes = {}
        for name, value in attrs_dict.items():
            try:
                os_type = AttributesSchema.get_os_type_for_field_name(name)
                is_indexed = AttributesSchema.get_is_indexed_for_field_name(name)
            except AttributesFieldNotFoundError as e:
                # the field is not in the schema
                raise e
            else:
                attributes[name] = OSAttribute(name=name, value=value, os_type=os_type, is_indexed=is_indexed)
        return cls(attributes=attributes)

    @classmethod
    def from_mapping(cls, mapping):
        """Parse an empty OSAttributes object from OS mappings"""
        attributes = {}
        for key in mapping:
            # Handle both indexed (attr_) and non-indexed (attr_noidx_) attributes
            is_indexed = None
            name = None

            if key.startswith('attr_noidx_'):
                is_indexed = False
                for os_type in OSFieldType.values:
                    if key.endswith(f'_{os_type}'):
                        name = key[len('attr_noidx_') : -len(f'_{os_type}')]
                        break
            elif key.startswith('attr_'):
                is_indexed = True
                for os_type in OSFieldType.values:
                    if key.endswith(f'_{os_type}'):
                        name = key[len('attr_') : -len(f'_{os_type}')]
                        break

            if name is not None and is_indexed is not None:
                attributes[name] = OSAttribute(name=name, value=None, os_type=os_type, is_indexed=is_indexed)
        return cls(attributes=attributes)

    def update(self, attrs_dict):
        new_attrs = self.from_json(attrs_dict)
        self.attributes.update(new_attrs.attributes)
        return self

    def to_json(self):
        return {attr.name: attr.value for attr in self.attributes.values()}

    def to_doc(self):
        attributes_dict = {}
        for attr in self.attributes.values():
            attributes_dict[attr.os_name] = attr.value
        return attributes_dict


class RelatedOSImages:
    _disallowed_chars = r'[^a-zA-Z0-9_-]'

    def __init__(self, images: dict[str, str] | None = None):
        self.images = {}
        if images:
            self.images = {str(name): str(link) for name, link in images.items()}

    def __bool__(self):
        return bool(self.images)

    def __contains__(self, item):
        return item in self.images

    def __iter__(self):
        return iter(self.images)

    def __len__(self):
        return len(self.images)

    def __getitem__(self, item):
        return self.images[item]

    def __setitem__(self, item, value):
        self.images[item] = value

    @classmethod
    def _validate_key(cls, key):
        min_length = 1
        max_length = settings.RELATED_IMAGE_TYPE_MAX_LENGTH
        if not isinstance(key, str):
            raise ValueError(f'Key in related_images must be a string, got {type(key)}')
        if re.search(cls._disallowed_chars, key):
            raise ValueError('Key in related_images can only contain alphanumeric characters, dashes, and underscores')
        if len(key) < min_length:
            raise ValueError(f'Key in related_images must be at least {min_length} characters long')
        if len(key) > max_length:
            raise ValueError(f'Key in related_images can only be {max_length} characters long')

    @classmethod
    def _validate_value(cls, value):
        min_length = 1
        max_length = settings.IMAGE_ID_MAX_LENGTH
        if not isinstance(value, str):
            raise ValueError(f'Value in related_images must be a string, got {type(value)}')
        if len(value) < min_length:
            raise ValueError(f'Value in related_images must be at least {min_length} characters long')
        if len(value) > max_length:
            raise ValueError(f'Value in related_images must be at most {max_length} characters long')
        if re.search(cls._disallowed_chars, value):
            raise ValueError(
                'Value in related_images can only contain alphanumeric characters, dashes, and underscores'
            )

    @classmethod
    def from_hit(cls, hit):
        related_images = {}
        if hit.get('related_images', None):
            for key, value in hit.get('related_images', {}).items():
                related_images[key] = value

        return cls(images=related_images)

    @classmethod
    def from_json(cls, images_dict):
        for key, value in images_dict.items():
            cls._validate_key(key)
            cls._validate_value(value)
        return cls(images=images_dict)

    def to_json(self):
        return self.images

    def to_doc(self):
        return {
            'related_images': self.images,
        }


class OSImageDatasets:
    def __init__(self, datasets: list[str] | None = None):
        if not datasets:
            datasets = []
        self.datasets = sorted(list(set(datasets)))

    def __bool__(self):
        return bool(self.datasets)

    def __contains__(self, item):
        return item in self.datasets

    def __iter__(self):
        return iter(self.datasets)

    def __len__(self):
        return len(self.datasets)

    def update(self, datasets_list):
        self.datasets = sorted(list(set(self.datasets + datasets_list)))
        return self

    def add(self, dataset):
        if dataset not in self.datasets:
            self.datasets.append(dataset)
        return self

    def remove(self, dataset):
        if dataset in self.datasets:
            self.datasets.remove(dataset)
        return self

    @classmethod
    def from_hit(cls, hit):
        datasets = hit.get('datasets', [])
        return cls(datasets=datasets)

    @classmethod
    def from_json(cls, datasets_list):
        return cls(datasets=datasets_list)

    def to_json(self):
        return sorted(self.datasets)

    def to_doc(self):
        return {
            'datasets': sorted(self.datasets),
        }


class OSImageManager:
    default_timeout = 55
    _exclude_deleted_query = {"bool": {"filter": [{"term": {"is_deleted": False}}]}}
    _search_params = {
        "timeout": f"{default_timeout}s",
    }

    def __init__(self, include_deleted=False):
        self.include_deleted = include_deleted

    def _field_includes(self, fields):
        if not fields:
            return None
        translated_fields = ['id', 'is_deleted']
        for field in fields:
            if field in OSImage.api_field_to_doc_field_mapping:
                translated_fields.extend(OSImage.api_field_to_doc_field_mapping[field])
            elif field not in OSImage.all_class_fields:
                raise ValueError(f'Invalid field "{field}"')
            else:
                translated_fields.append(field)
        return list(set(translated_fields))

    def search(self, fields=None, search_after=None, sort=None, include_source=True):
        extra = dict(self._search_params)
        s = Search(using=OS.client, index=OSImage.INDEX, extra=extra)

        # sorting
        if not sort:
            sort = 'id'
        if sort:
            s = s.sort(sort)

        # do not include _source or only some fields
        if not include_source:
            s = s.source(False)
        elif fields:
            s = s.source(includes=self._field_includes(fields))

        # pagination
        if search_after:
            s = s.extra(search_after=search_after)

        # include deleted
        if not self.include_deleted:
            s = s.filter(self._exclude_deleted_query)

        return s

    def counts_by_field(self, field_name, order="desc", number=100):
        search = self.search(sort='_doc', include_source=False).extra(size=0)
        search.aggs.bucket('count', 'terms', field=field_name, order={"_count": order}, size=number)
        result = search.execute()
        return {doc['key']: doc['doc_count'] for doc in result.aggregations.count.to_dict()['buckets']}

    def filter_counts_by_field(self, filter_type, filter_kwargs, field_name, order="desc", number=100):
        search = self.search(sort='_doc', include_source=False).extra(size=0)
        search = search.filter(filter_type, **filter_kwargs)
        search.aggs.bucket('count', 'terms', field=field_name, order={"_count": order}, size=number)
        result = search.execute()
        return {doc['key']: doc['doc_count'] for doc in result.aggregations.count.to_dict()['buckets']}

    def get_by_original_url(self, original_url):
        result = self.search().filter("term", original_url=original_url).execute()
        if len(result.hits.hits) and (self.include_deleted or not result.hits.hits[0]['_source']['is_deleted']):
            return OSImage.from_hit(result.hits[0])
        raise OSImage.DoesNotExist(f'OSImage with url "{original_url}" not found')

    def get_by_hash(self, image_hash):
        result = self.search().filter("term", image_hash=image_hash).execute()
        if len(result.hits.hits) and (self.include_deleted or not result.hits.hits[0]['_source']['is_deleted']):
            return OSImage.from_hit(result.hits[0])
        raise OSImage.DoesNotExist(f'OSImage with hash "{image_hash}" not found')

    def get_multiple_by_hash(self, image_hashes, fields=None, number=100):
        result = self.search(fields=fields).filter("terms", image_hash=image_hashes).extra(size=number).execute()
        return OSImage.list_from_hits(result.hits.hits)

    def get(self, id, fields=None):  # noqa: A002
        try:
            hit = OS.client.get(
                index=OSImage.INDEX,
                id=id,
                _source_includes=self._field_includes(fields),
                timeout=self.default_timeout,
            )
        except NotFoundError as e:
            raise OSImage.DoesNotExist(f'OSImage "{id}" not found') from e
        if self.include_deleted or not hit['_source']['is_deleted']:
            return OSImage.from_hit(hit)
        raise OSImage.DoesNotExist(f'OSImage "{id}" is deleted')

    def get_multiple(self, ids, fields=None, number=100):
        result = self.search(fields=fields).filter("terms", id=ids).extra(size=number).execute()
        return OSImage.list_from_hits(result.hits.hits)

    def all(self, number=100, fields=None):
        """Convenience method to get all images up to a count of <number>."""
        response = self.search(fields=fields).extra(size=number).execute()
        return OSImage.list_from_hits(response.hits)

    def find_similar(self, vector, number=10, exclude_id=None, fields=None, body=None):
        if body:
            if "size" not in body:
                body["size"] = number
            if "query" not in body:
                body["query"] = {"bool": {}}
            elif "bool" not in body["query"]:
                body["query"]["bool"] = {}
            if "must" not in body["query"]["bool"]:
                body["query"]["bool"]["must"] = []
        else:
            body = {"size": number, "query": {"bool": {"must": []}}}

        body["query"]["bool"]["must"].append(
            {
                "knn": {
                    "coca_embedding_vector": {
                        "vector": vector,
                        "k": number,
                    },
                },
            }
        )

        if exclude_id:
            if "must_not" not in body["query"]["bool"]:
                body["query"]["bool"]["must_not"] = []
            body["query"]["bool"]["must_not"].append({"match": {"id": exclude_id}})
        if not self.include_deleted:
            if "filter" not in body["query"]["bool"]:
                body["query"]["bool"]["filter"] = []
            body["query"]["bool"]["filter"].extend(self._exclude_deleted_query["bool"]["filter"])

        response = OS.client.search(
            index=OSImage.INDEX,
            body=body,
            _source_includes=self._field_includes(fields),
            timeout=self.default_timeout,
        )
        return OSImage.list_from_hits(response['hits']['hits'])

    def find_similar_to_file(self, image_file, number=10, exclude_id=None, fields=None, body=None):
        vector = get_vector_for_image_file(image_file)
        if not vector:
            return []
        return self.find_similar(vector=vector, number=number, exclude_id=exclude_id, fields=fields, body=body)

    def get_similarity(self, image_id, vector):
        query = {
            "size": 1,
            "query": {
                "bool": {
                    "must": {
                        "knn": {
                            "coca_embedding_vector": {
                                "vector": vector,
                                "k": 1,
                            },
                        },
                    },
                    "filter": [
                        {"term": {"id": image_id}},
                    ],
                },
            },
        }
        if not self.include_deleted:
            query["query"]["bool"]["filter"].append(self._exclude_deleted_query["bool"]["filter"][0])

        response = OS.client.search(
            index=OSImage.INDEX,
            body=query,
            _source=False,
            timeout=self.default_timeout,
        )
        if len(response['hits']['hits']):
            return normalize_similarity(response['hits']['hits'][0]['_score'])

        raise OSImage.DoesNotExist(f'OSImage "{image_id}" not found')

    def refresh(self):
        OS.client.indices.refresh(index=OSImage.INDEX, timeout=self.default_timeout)


class OSImageMeta:
    def __init__(self, score: float, sort: list):
        self.score = score
        self.sort = sort


class OSImage:
    INDEX = settings.OPENSEARCH_IMAGES_INDEX_NAME
    INDEX_SETTINGS = {
        "settings": {
            "index": {
                # Number of shards should be divisible by the number of nodes (4 today)
                # Ideally, each shard should be 20-50gb
                # Our 70mil images is about 1000 GB
                # 48 shards: ideal for 70mil - 170mil images
                "number_of_shards": 48,
                # No replicas, we don't care about redundancy
                "number_of_replicas": 0,
                # Support for k-NN search
                "knn": True,
                "knn.algo_param.ef_search": 100,
                # Increase the limit for the number of fields in the index
                "mapping": {
                    "total_fields": {
                        "limit": "2000",
                    },
                },
            },
        },
        "mappings": {
            # We disable "norms" on all keywords. They are used for scoring results, which we don't use.
            # The keyword type supports exact matches only, without any text analysis
            "properties": {
                "id": {"type": "keyword", "norms": False},  # useful when sorting by id
                "date_created": {"type": "date"},
                "date_updated": {"type": "date"},
                "is_deleted": {"type": "boolean"},
                "author": {"type": "keyword", "norms": False},
                "image": {"type": "keyword", "norms": False},
                "image_hash": {"type": "keyword", "norms": False},
                "width": {"type": "long"},
                "height": {"type": "long"},
                "short_edge": {"type": "long"},
                "pixel_count": {"type": "long"},
                "aspect_ratio": {"type": "double"},
                "aspect_ratio_fraction": {"type": "keyword", "norms": False},
                "thumbnail": {"type": "keyword", "norms": False},
                "thumbnail_error": {"type": "boolean"},
                "source": {"type": "keyword", "norms": False},
                "original_url": {"type": "keyword", "norms": False},
                "tags": {"type": "keyword", "norms": False},
                "coca_embedding_exists": {"type": "boolean"},
                "coca_embedding_vector": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "innerproduct",
                        "parameters": {
                            "encoder": {
                                "name": "sq",
                                "parameters": {
                                    "type": "fp16",
                                },
                            },
                            "ef_construction": 64,
                            "m": 16,
                        },
                    },
                },
                "coca_embedding_author": {"type": "keyword", "norms": False},
                "duplicate_state": {"type": "keyword", "norms": False},
                "related_images": {
                    "type": "object",
                    "dynamic": False,  # do not add to the mapping
                    "enabled": False,  # do not index
                },
                "datasets": {"type": "keyword", "norms": False},
            },
            "dynamic_templates": [
                # latents
                # latent_<latent_type>_file
                {
                    "latents_files": {
                        "match_pattern": "regex",
                        "match": "latents_.*_file",
                        "mapping": {"type": "keyword", "norms": False},
                    },
                },
                # Non-indexed attributes (stored but not searchable, aggregatable)
                # attr_noidx_<attribute_name>_<os_type>
                # We use the os_type in the name in order to avoid losing data if the schema type is changed
                {
                    "attr_noidx_keywords": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_keyword",
                        "mapping": {
                            "type": "keyword",
                            "index": False,  # Not searchable
                            "doc_values": True,  # Aggregatable
                            "norms": False,  # No scoring
                        },
                    },
                },
                {
                    "attr_noidx_doubles": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_double",
                        "mapping": {"type": "double", "index": False, "doc_values": True},
                    },
                },
                {
                    "attr_noidx_longs": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_long",
                        "mapping": {"type": "long", "index": False, "doc_values": True},
                    },
                },
                {
                    "attr_noidx_dates": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_date",
                        "mapping": {"type": "date", "index": False, "doc_values": True},
                    },
                },
                {
                    "attr_noidx_booleans": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_boolean",
                        "mapping": {"type": "boolean", "index": False, "doc_values": True},
                    },
                },
                {
                    "attr_noidx_objects": {
                        "match_pattern": "regex",
                        "match": "attr_noidx_.*_object",
                        "mapping": {
                            "type": "object",
                            "index": False,  # Not searchable
                            "dynamic": False,  # Prevent automatic subfield mapping
                            "enabled": False,  # Completely disable indexing of all subfields
                        },
                    },
                },
                # Indexed attributes
                # attr_<attribute_name>_<os_type>
                # We use the os_type in the name in order to avoid losing data if the schema type is changed
                {
                    # We use a text field here, so we can do full-text search
                    "attr_texts": {
                        "match_pattern": "regex",
                        "match": "attr_.*_text",
                        "mapping": {
                            "type": "text",
                            "fields": {
                                # We also store a keyword field for exact matches
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256,
                                    "norms": False,
                                },
                            },
                        },
                    },
                },
                {
                    "attr_doubles": {
                        "match_pattern": "regex",
                        "match": "attr_.*_double",
                        "mapping": {"type": "double"},
                    },
                },
                {
                    "attr_longs": {
                        "match_pattern": "regex",
                        "match": "attr_.*_long",
                        "mapping": {"type": "long"},
                    },
                },
                {
                    "attr_dates": {
                        "match_pattern": "regex",
                        "match": "attr_.*_date",
                        "mapping": {"type": "date"},
                    },
                },
                {
                    "attr_booleans": {
                        "match_pattern": "regex",
                        "match": "attr_.*_boolean",
                        "mapping": {"type": "boolean"},
                    },
                },
            ],
        },
    }
    all_class_fields = (
        "id",
        "source",
        "image",
        "date_created",
        "date_updated",
        "is_deleted",
        "author",
        "image_hash",
        "width",
        "height",
        "short_edge",
        "pixel_count",
        "aspect_ratio",
        "aspect_ratio_fraction",
        "thumbnail",
        "thumbnail_error",
        "original_url",
        "tags",
        "coca_embedding",
        "latents",
        "attributes",
        "duplicate_state",
        "related_images",
        "datasets",
    )
    required_class_fields = (  # not allowed to be None
        'id',
        'source',
        'image',
        'image_hash',
        'width',
        'height',
        'short_edge',
        'pixel_count',
        'aspect_ratio',
        'aspect_ratio_fraction',
    )
    available_api_fields = (  # fields available in the API
        "id",
        "source",
        "image",
        'image_direct_url',
        "date_created",
        "date_updated",
        "author",
        "image_hash",
        "width",
        "height",
        "short_edge",
        "pixel_count",
        "aspect_ratio",
        "aspect_ratio_fraction",
        "thumbnail",
        'thumbnail_direct_url',
        "thumbnail_error",
        "original_url",
        "tags",
        "coca_embedding",
        "latents",
        "attributes",
        "duplicate_state",
        "related_images",
        "datasets",
    )
    default_api_fields = (  # fields to return by default in the API
        "id",
        "source",
        # "image",
        'image_direct_url',
        "date_created",
        "date_updated",
        "author",
        "image_hash",
        "width",
        "height",
        "short_edge",
        "pixel_count",
        "aspect_ratio",
        "aspect_ratio_fraction",
        # "thumbnail",
        # 'thumbnail_direct_url',
        "original_url",
        "tags",
        # "coca_embedding",
        # "latents",
        "attributes",
        # "duplicate_state",
        "datasets",
    )
    api_field_to_doc_field_mapping = {  # renames for ?include_fields
        "image_direct_url": ["image"],
        "thumbnail_direct_url": ["thumbnail"],
        "coca_embedding": ["coca_embedding_exists", "coca_embedding_vector", "coca_embedding_author"],
        "latents": ["latent_*"],
        "attributes": ["attr_*"],
    }

    DoesNotExist = ObjectDoesNotExist

    objects = OSImageManager()
    all_objects = OSImageManager(include_deleted=True)

    def __init__(
        self,
        id,  # noqa: A002
        source: str | None = None,
        image: str | None = None,
        image_file: File | None = None,
        meta: OSImageMeta | None = None,
        date_created: str | None = None,
        date_updated: str | None = None,
        is_deleted: bool = False,
        author: str | None = None,
        image_hash: str | None = None,
        width: int | None = None,
        height: int | None = None,
        short_edge: int | None = None,
        pixel_count: int | None = None,
        aspect_ratio: float | None = None,
        aspect_ratio_fraction: str | None = None,
        thumbnail: str | None = None,
        thumbnail_file: File | None = None,
        thumbnail_error: bool = False,
        original_url: str | None = None,
        tags: list[str] | None = None,
        coca_embedding_exists: bool = False,
        coca_embedding_vector: list[float] | None = None,
        coca_embedding_author: str | None = None,
        latents: OSLatents = None,
        attributes: OSAttributes = None,
        duplicate_state: DuplicateState = DuplicateState.UNPROCESSED,
        related_images: RelatedOSImages = None,
        datasets: OSImageDatasets | None = None,
    ):
        self._validate_id(id)
        self.id = id
        self.source = source
        self.image = image
        self._image_file = image_file
        self.meta = meta
        self.date_created = date_created
        self.date_updated = date_updated
        if is_deleted is None:
            is_deleted = False
        self.is_deleted = is_deleted
        self.author = author
        self.image_hash = image_hash
        self.width = width
        self.height = height
        self.short_edge = short_edge
        self.pixel_count = pixel_count
        self.aspect_ratio = aspect_ratio
        self.aspect_ratio_fraction = aspect_ratio_fraction
        self.thumbnail = thumbnail
        self._thumbnail_file = thumbnail_file
        self.thumbnail_error = thumbnail_error
        self.original_url = original_url
        if not tags:
            tags = []
        self.tags = tags
        self.coca_embedding_exists = coca_embedding_exists
        self.coca_embedding_vector = coca_embedding_vector
        self.coca_embedding_author = coca_embedding_author
        if latents is None:
            latents = OSLatents()
        assert isinstance(latents, OSLatents)
        self.latents = latents
        if attributes is None:
            attributes = OSAttributes()
        assert isinstance(attributes, OSAttributes)
        self.attributes = attributes
        self.duplicate_state = duplicate_state
        if related_images is None:
            related_images = RelatedOSImages()
        self.related_images = related_images
        if datasets is None:
            datasets = OSImageDatasets()
        self.datasets = datasets

    def __str__(self):
        return self.id

    def __repr__(self):
        return f'<OSImage {self.id}>'

    @classmethod
    def get_num_shards(cls):
        return cls.INDEX_SETTINGS['settings']['index']['number_of_shards']

    @classmethod
    def _validate_id(cls, value):
        disallowed_chars = r'[^a-zA-Z0-9_-]'
        if re.search(disallowed_chars, value):
            raise ValueError('ID can only contain alphanumeric characters, dashes, and underscores')
        if len(value) < settings.IMAGE_ID_MIN_LENGTH or len(value) > settings.IMAGE_ID_MAX_LENGTH:
            raise ValueError(
                f'Ensure this field has between {settings.IMAGE_ID_MIN_LENGTH} '
                'and {settings.IMAGE_ID_MAX_LENGTH} characters.'
            )

    @classmethod
    def from_hit(cls, hit, latent_types_map=None):
        """
        Create an OSImage from an OpenSearch hit.
        """
        if isinstance(hit, Hit):
            hit_id = hit.meta.id
            hit_meta = OSImageMeta(score=hit.meta.score, sort=hit.meta.sort)
            doc = hit.to_dict()
        else:
            hit_id = hit['_id']
            hit_meta = OSImageMeta(score=hit.get('_score'), sort=hit.get('sort'))
            doc = hit['_source']
            if isinstance(doc, AttrDict):
                doc = doc.to_dict()

        if not latent_types_map:
            latent_types_map = cls.get_latent_types_map()

        return cls(
            id=hit_id,
            source=doc.get('source'),
            image=doc.get('image'),
            meta=hit_meta,
            date_created=doc.get('date_created'),
            date_updated=doc.get('date_updated'),
            is_deleted=doc.get('is_deleted'),
            author=doc.get('author'),
            image_hash=doc.get('image_hash'),
            width=doc.get('width'),
            height=doc.get('height'),
            short_edge=doc.get('short_edge'),
            pixel_count=doc.get('pixel_count'),
            aspect_ratio=doc.get('aspect_ratio'),
            aspect_ratio_fraction=doc.get('aspect_ratio_fraction'),
            thumbnail=doc.get('thumbnail'),
            thumbnail_error=doc.get('thumbnail_error'),
            original_url=doc.get('original_url'),
            tags=doc.get('tags'),
            coca_embedding_exists=doc.get('coca_embedding_exists'),
            coca_embedding_vector=doc.get('coca_embedding_vector'),
            coca_embedding_author=doc.get('coca_embedding_author'),
            latents=OSLatents.from_hit(doc, latent_types_map=latent_types_map),
            attributes=OSAttributes.from_hit(doc),
            duplicate_state=DuplicateState(doc.get('duplicate_state')),
            related_images=RelatedOSImages.from_hit(doc),
            datasets=OSImageDatasets.from_hit(doc),
        )

    @classmethod
    def get_latent_types_map(cls):
        return {latent_type.name: latent_type for latent_type in LatentType.objects.all()}

    @classmethod
    def list_from_hits(cls, hits):
        latent_types_map = cls.get_latent_types_map()
        return [
            OSImage.from_hit(
                hit,
                latent_types_map=latent_types_map,
            )
            for hit in hits
        ]

    def to_json(self, fields=None, all_fields=False, include_fields=None, return_latents=None, extra_data=None):
        """
        Convert the OSImage to a JSON-serializable dictionary to be used in the API.
        @param fields: list of fields to include in the output
        @param all_fields: include all available fields
        @param include_fields: fields to include additionally to the default fields
        @param return_latents: list of latent types to include in the output (if None, all latents are included)
        """
        result = {}
        selected_fields = fields or (self.available_api_fields if all_fields else self.default_api_fields)
        selected_fields = [f for f in selected_fields]
        if include_fields:
            selected_fields += include_fields
        for field in selected_fields:
            if field not in self.available_api_fields:
                raise ValueError(f"Invalid field: {field}")
            elif field == "coca_embedding":
                result[field] = (
                    {
                        "vector": self.coca_embedding_vector,
                        "author": self.coca_embedding_author,
                    }
                    if self.coca_embedding_exists
                    else None
                )
            elif field == "image":
                result[field] = self.image_url
            elif field == "thumbnail":
                result[field] = self.thumbnail_url
            elif field == "latents":
                result[field] = self.latents.to_json(return_latents=return_latents)
            elif field == "attributes":
                result[field] = self.attributes.to_json()
            elif field == "duplicate_state":
                result[field] = self.duplicate_state.value if self.duplicate_state is not None else None
            elif field == "related_images":
                result[field] = self.related_images.to_json()
            elif field == "datasets":
                result[field] = self.datasets.to_json()
            else:
                result[field] = getattr(self, field)
        if extra_data:
            result.update(extra_data)
        return result

    def to_doc(self, fields=None):
        """
        Convert the OSImage to an OpenSearch document.
        """
        selected_fields = []
        if fields:
            for f in fields:
                if f not in self.all_class_fields:
                    raise ValueError(f"Invalid field: {f}")
                else:
                    selected_fields.append(f)
        else:
            selected_fields = self.all_class_fields

        doc = {}
        for field in selected_fields:
            if field == "coca_embedding":
                doc["coca_embedding_exists"] = self.coca_embedding_exists
                doc["coca_embedding_vector"] = self.coca_embedding_vector
                doc["coca_embedding_author"] = self.coca_embedding_author
            elif field == "latents" or field.startswith("latent_"):
                doc.update(self.latents.to_doc())
            elif field == "attributes" or field.startswith("attr_"):
                doc.update(self.attributes.to_doc())
            elif field == "duplicate_state":
                doc[field] = self.duplicate_state.value if self.duplicate_state is not None else None
            elif field == "related_images":
                doc.update(self.related_images.to_doc())
            elif field == "datasets":
                doc.update(self.datasets.to_doc())
            else:
                doc[field] = getattr(self, field)

        return doc

    def _validate_class(self, fields=None):
        fields = [f for f in fields if f in self.required_class_fields] if fields else self.required_class_fields

        for field in fields:
            if not getattr(self, field):
                raise ValueError(f'OSImage field "{field}" is required')

        if not isinstance(self.attributes, OSAttributes):
            raise ValueError('OSImage.attributes must be an OSAttributes instance')
        if not isinstance(self.latents, OSLatents):
            raise ValueError('OSImage.latents must be an OSLatents instance')
        if self.related_images and not isinstance(self.related_images, RelatedOSImages):
            raise ValueError('OSImage.related_images must be an RelatedOSImages instance')
        if not isinstance(self.datasets, OSImageDatasets):
            raise ValueError('OSImage.datasets must be an OSImageDatasets instance')

    @tracer.wrap()
    def create(self, bulk_index: OSBulkIndex = None, refresh=settings.OPENSEARCH_DEFAULT_REFRESH):
        date_now = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC')).isoformat()

        if not self._image_file and not self.image:
            raise ValueError('No image_file or image provided')

        if not self.image:
            # we are creating a new image, save it to storage
            assert self._image_file
            storage_path = self.get_image_storage_path(image_id=self.id, filename=self._image_file.name)
            self.image = default_storage.save(storage_path, self._image_file)
            # calculate hash
            if not self.image_hash:
                self.image_hash = self.get_image_hash(self._image_file)
            # get image sizes
            sizes = self.get_image_sizes(self._image_file)
            self.width = sizes['width']
            self.height = sizes['height']
            self.short_edge = sizes['short_edge']
            self.pixel_count = sizes['pixel_count']
            self.aspect_ratio = sizes['aspect_ratio']
            self.aspect_ratio_fraction = sizes['aspect_ratio_fraction']

        # update dates
        if not self.date_created:
            self.date_created = date_now
        self.date_updated = date_now

        # final validation
        self._validate_class()

        # save to OpenSearch
        if bulk_index:
            bulk_index.index(
                index=self.INDEX,
                doc_id=self.id,
                body=self.to_doc(),
            )
        else:
            OS.client.index(
                index=self.INDEX,
                id=self.id,
                body=self.to_doc(),
                refresh=refresh,
                timeout=self.objects.default_timeout,
            )

        self._update_tag_objects()

        return self

    def _update_tag_objects(self):
        # creates entries in the tags table
        for tag_name in self.tags:
            Tag.objects.get_or_create(name=tag_name)

    @tracer.wrap()
    def save(self, fields, latent_types=None, bulk_index=None, refresh=settings.OPENSEARCH_DEFAULT_REFRESH):
        """
        Save the OSImage to OpenSearch.

        @param fields: List of fields to update
        @param latent_types: If "latents" is in fields, please also provide a list of latent types to update (all other
            latent types will not be updated)
        @param bulk_index: OSBulkIndex instance to use for bulk indexing
        @param refresh: Should we refresh the index right after saving?
        """
        # we don't allow saving without explicitly providing fields to prevent data loss
        if not fields:
            raise ValueError('No fields provided')

        if 'image' in fields:
            raise ValueError('Not allowed to update the image field')

        # update date
        fields.append('date_updated')
        self.date_updated = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC')).isoformat()

        # final validation
        self._validate_class(fields=fields)

        # save latents
        if latent_types and 'latents' not in fields:
            raise ValueError('Latent types provided without saving latents')
        if 'latents' in fields:
            if not latent_types:
                raise ValueError('Latent types must be provided when saving latents')
            self.latents.validate_latent_types()
            for latent in self.latents.latents.values():
                if not latent.is_removed and latent.latent_type in latent_types:
                    storage_path = self.get_latent_storage_path(
                        image_id=self.id,
                        latent_type=latent.latent_type,
                        filename=latent.file_object.name,
                    )
                    latent.file = default_storage.save(storage_path, latent.file_object)

        # save to OpenSearch
        doc = self.to_doc(fields=fields)
        try:
            if bulk_index:
                bulk_index.index(
                    index=self.INDEX,
                    doc_id=self.id,
                    body=doc,
                )
            else:
                OS.client.update(
                    index=self.INDEX,
                    id=self.id,
                    body={"doc": doc},
                    refresh=refresh,
                    timeout=self.objects.default_timeout,
                )
        except ConflictError as e:
            if e.error == 'version_conflict_engine_exception':
                raise SaveConflictError() from e

        if 'tags' in fields:
            self._update_tag_objects()

        return self

    @tracer.wrap()
    def add_latent(self, latent: OSLatent):
        if not isinstance(latent, OSLatent) or not latent._file_object or latent.file:
            raise ValueError('Invalid latent state')

        # save the image
        self.latents.latents[latent.latent_type] = latent
        self.save(fields=['latents'], latent_types=[latent.latent_type])

    @tracer.wrap()
    def remove_latent(self, latent_type, refresh=settings.OPENSEARCH_DEFAULT_REFRESH):
        if latent_type not in self.latents:
            raise ValueError(f'Latent type "{latent_type}" not found in image')

        latent = self.latents.latents[latent_type]
        if latent.file:
            default_storage.delete(latent.file)

        latent.mark_as_removed()
        self.save(fields=['latents'], latent_types=[latent.latent_type], refresh=refresh)

    @tracer.wrap()
    def update_thumbnail(self, pil_image=None):
        try:
            if not pil_image:
                pil_image = self.pil_image

            pil_image.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

            # save the thumbnail to a temporary memory file
            with BytesIO() as temp_thumb:
                pil_image.save(temp_thumb, pil_image.format)
                temp_thumb.seek(0)
                content_file = ContentFile(temp_thumb.read())
                storage_path = self.get_thumbnail_storage_path(image_id=self.id, filename=pil_image.filename)
                self.thumbnail = default_storage.save(storage_path, content_file)
        except Exception as e:
            logger.error(f'Error updating thumbnail for image {self.id}: {e}')
            self.thumbnail_error = True
            self.save(fields=['thumbnail_error'])
        else:
            # TODO: log update
            self.save(fields=['thumbnail'])

    @tracer.wrap()
    def update_coca_embedding(self, pil_image=None, author=None):
        if not pil_image:
            pil_image = self.pil_image

        vector = fetch_coca_embedding(pil_image=pil_image, image_name=pil_image.filename)
        if not vector:
            return

        vector = normalize_vector(vector)

        self.coca_embedding_vector = vector
        self.coca_embedding_exists = True
        self.coca_embedding_author = author

        # TODO: log update
        self.save(fields=['coca_embedding'])

    @tracer.wrap()
    async def update_coca_embedding_async(self, pil_image=None, author=None):
        if not pil_image:
            pil_image = self.pil_image

        vector = await fetch_coca_embedding_async(pil_image=pil_image, image_name=pil_image.filename)
        if not vector:
            return

        vector = normalize_vector(vector)

        self.coca_embedding_vector = vector
        self.coca_embedding_exists = True
        self.coca_embedding_author = author

        # TODO: log update
        self.save(fields=['coca_embedding'])

    @classmethod
    @tracer.wrap()
    def mark_duplicates(cls, image_id, threshold=settings.DUPLICATE_FINDER_SIMILARITY_THRESHOLD):
        current_image = OSImage.objects.get(
            image_id,
            fields=["id", "duplicate_state", "coca_embedding", "width", "height"],
        )

        if current_image.duplicate_state != DuplicateState.UNPROCESSED:
            return

        if not current_image.coca_embedding_exists:
            return

        similars = current_image.find_similar(number=settings.DUPLICATE_FINDER_NUMBER_OF_SIMILARS)
        duplicates = [current_image] + [similar for similar in similars if similar.similarity_from_score > threshold]

        sorted_duplicates = sorted(duplicates, key=lambda image: image.width * image.height, reverse=True)

        with OSBulkIndex() as bulk_index:
            for i, duplicate in enumerate(sorted_duplicates):
                duplicate.duplicate_state = DuplicateState.ORIGINAL if i == 0 else DuplicateState.DUPLICATE
                duplicate.save(bulk_index=bulk_index, fields=["duplicate_state"])

    def delete(self, refresh=True):
        # TODO: log update
        OS.client.update(
            index=self.INDEX,
            id=self.id,
            body={"doc": {"is_deleted": True}},
            refresh=refresh,
            timeout=self.objects.default_timeout,
        )

    def delete_permanently(self, refresh=True):
        # TODO: log update
        filepaths_to_delete = [self.image, self.thumbnail]
        for latent in self.latents.latents.values():
            filepaths_to_delete.append(latent.file)
        for filepath in filepaths_to_delete:
            if filepath:
                default_storage.delete(filepath)
        OS.client.delete(
            index=self.INDEX,
            id=self.id,
            refresh=refresh,
            timeout=self.objects.default_timeout,
        )

    @property
    def similarity_from_score(self):
        if self.meta.score is None:
            return None
        return normalize_similarity(self.meta.score)

    @property
    def image_file(self):
        if not self._image_file:
            self._image_file = default_storage.open(self.image)
        return self._image_file

    @property
    def pil_image(self):
        pil_image = Image.open(self.image_file)
        pil_image.filename = self.image_file.name
        return pil_image

    @property
    def thumbnail_file(self):
        if not self._thumbnail_file and self.thumbnail:
            self._thumbnail_file = default_storage.open(self.thumbnail)
        return self._thumbnail_file

    @property
    def pil_thumbnail(self):
        return Image.open(self.thumbnail_file) if self.thumbnail_file else None

    @classmethod
    def get_storage_path(cls, image_id: str, filename: str, name: str):
        extension = str(filename.replace('/', '').split('.')[-1:][0])[:4]
        return f"images/{image_id}/{name}.{extension}"

    @classmethod
    def get_image_storage_path(cls, image_id, filename):
        return cls.get_storage_path(image_id=image_id, filename=filename, name='original')

    @classmethod
    def get_thumbnail_storage_path(cls, image_id, filename):
        return cls.get_storage_path(image_id=image_id, filename=filename, name='thumbnail')

    @classmethod
    def get_latent_storage_path(cls, image_id, latent_type, filename):
        return cls.get_storage_path(image_id=image_id, filename=filename, name=f'latent_{latent_type}')

    @classmethod
    def get_aspect_ratio_fraction(cls, aspect_ratio):
        if aspect_ratio:
            fraction = Fraction(aspect_ratio).limit_denominator(max_denominator=10)
            return f'{fraction.numerator}:{fraction.denominator}'
        return ''

    @classmethod
    def get_image_sizes(cls, image_file: File):
        with Image.open(image_file) as pil_image:
            sizes = {
                'width': pil_image.width,
                'height': pil_image.height,
            }
            sizes.update(
                {
                    'short_edge': min(sizes['width'], sizes['height']),
                    'aspect_ratio': sizes['width'] / sizes['height'],
                    'pixel_count': sizes['width'] * sizes['height'],
                }
            )
            sizes.update(
                {
                    'aspect_ratio_fraction': cls.get_aspect_ratio_fraction(sizes['aspect_ratio']),
                }
            )
        return sizes

    @classmethod
    def get_image_hash(cls, image_file: File, image_hash: str | None = None, prefix='sha256'):
        if not image_hash:
            image_hash = cls.get_image_hash_without_prefix(image_file)
        return f'{prefix}:{image_hash}'

    @classmethod
    def get_image_hash_without_prefix(cls, image_file: File):
        image_file.seek(0)
        with Image.open(image_file) as image:
            image.load()
            return hashlib.sha256(image.tobytes()).hexdigest()

    @tracer.wrap()
    def is_same_image(self, other_image_file):
        other_hash = self.get_image_hash(other_image_file)
        if self.image_hash == other_hash:
            other_image = Image.open(other_image_file)
            if self.width == other_image.width and self.height == other_image.height:
                arr1 = np.array(Image.open(self.image_file))
                arr2 = np.array(other_image)
                return np.array_equal(arr1, arr2)
        return False

    @property
    def image_url(self):
        return default_storage.url(self.image) if self.image else None

    @property
    def image_direct_url(self):
        with disable_storage_custom_domain(default_storage):
            return default_storage.url(self.image) if self.image else None

    @property
    def thumbnail_url(self):
        return default_storage.url(self.thumbnail) if self.thumbnail else None

    @property
    def thumbnail_direct_url(self):
        with disable_storage_custom_domain(default_storage):
            return default_storage.url(self.thumbnail) if self.thumbnail else None

    @tracer.wrap()
    def get_similarity(self, other_image: 'OSImage'):
        """
        Dot/Inner Product (similarity) between two images.
        """
        if not isinstance(other_image, OSImage):
            raise ValueError('other_image must be a OSImage')
        if not self.coca_embedding_exists:
            raise MissingEmbeddingError(image_id=self.id)
        if not other_image.coca_embedding_exists:
            raise MissingEmbeddingError(image_id=other_image.id)

        return self.objects.get_similarity(image_id=other_image.id, vector=self.coca_embedding_vector)

    @tracer.wrap()
    def find_similar(self, number=10, fields=None):
        if not self.coca_embedding_exists:
            raise MissingEmbeddingError(image_id=self.id)
        return self.objects.find_similar(
            self.coca_embedding_vector,
            number=number,
            exclude_id=self.id,
            fields=fields,
        )
