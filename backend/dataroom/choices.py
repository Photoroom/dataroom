from enum import Enum

from django.db import models


class AttributesFieldType(models.TextChoices):
    STRING = "string", "String"
    NUMBER = "number", "Number"
    INTEGER = "integer", "Integer"
    # OBJECT = "object", "Object"  # nesting not allowed for now
    ARRAY = "array", "Array"
    BOOLEAN = "boolean", "Boolean"
    NULL = "null", "Null"


class AttributesFilterComparator(models.TextChoices):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    MATCH = "match"
    MATCH_PHRASE = "match_phrase"
    PREFIX = "prefix"
    NOT_MATCH = "not_match"
    NOT_MATCH_PHRASE = "not_match_phrase"
    NOT_PREFIX = "not_prefix"

    @classmethod
    def get_for_attr_name(cls, attr_name: str):
        for comp in cls:
            if attr_name.endswith(f'__{comp.value}'):
                return comp
        return cls.EQ

    @property
    def negated_value(self):
        return {
            AttributesFilterComparator.NOT_MATCH: AttributesFilterComparator.MATCH,
            AttributesFilterComparator.NOT_MATCH_PHRASE: AttributesFilterComparator.MATCH_PHRASE,
            AttributesFilterComparator.NOT_PREFIX: AttributesFilterComparator.PREFIX,
        }.get(self, self)


class OSFieldType(models.TextChoices):
    DATE = "date", "date"
    TEXT = "text", "text"
    DOUBLE = "double", "double"
    LONG = "long", "long"
    BOOLEAN = "boolean", "boolean"

    def is_valid_for_comparator(self, comparator: AttributesFilterComparator):
        if self in [OSFieldType.DOUBLE, OSFieldType.LONG, OSFieldType.DATE]:
            # numeric types
            return comparator in [
                AttributesFilterComparator.EQ,
                AttributesFilterComparator.NE,
                AttributesFilterComparator.LT,
                AttributesFilterComparator.LTE,
                AttributesFilterComparator.GT,
                AttributesFilterComparator.GTE,
            ]
        elif self in [OSFieldType.BOOLEAN]:
            # boolean type
            return comparator in [
                AttributesFilterComparator.EQ,
                AttributesFilterComparator.NE,
            ]
        elif self in [OSFieldType.TEXT]:
            # text type
            return comparator in [
                AttributesFilterComparator.EQ,
                AttributesFilterComparator.NE,
                AttributesFilterComparator.MATCH,
                AttributesFilterComparator.MATCH_PHRASE,
                AttributesFilterComparator.PREFIX,
                AttributesFilterComparator.NOT_MATCH,
                AttributesFilterComparator.NOT_MATCH_PHRASE,
                AttributesFilterComparator.NOT_PREFIX,
            ]
        raise NotImplementedError(f'Comparator {comparator} not implemented for type {self}')


class AttributesFieldStringFormat(models.TextChoices):
    DATE_TIME = "date-time", "Date-time"
    TIME = "time", "Time"
    DATE = "date", "Date"
    DURATION = "duration", "Duration"
    EMAIL = "email", "Email"
    HOSTNAME = "hostname", "Hostname"
    IPV4 = "ipv4", "IPv4"
    IPV6 = "ipv6", "IPv6"
    UUID = "uuid", "UUID"
    URI = "uri", "URI"


class StatsType(models.TextChoices):
    TOTAL_IMAGES = "total_images", "Total images"
    TOTAL_DATASETS = "total_datasets", "Total datasets"
    IMAGE_SOURCES = "image_sources", "Image sources"
    IMAGE_ASPECT_RATIO_FRACTIONS = "image_aspect_ratio_fractions", "Image aspect ratio fractions"
    IMAGES_MISSING_THUMBNAIL = "images_missing_thumbnail", "Images missing thumbnail"
    IMAGES_MISSING_COCA_EMBEDDING = "images_missing_coca_embedding", "Images missing COCA embedding"
    IMAGES_MISSING_TAGS = "images_missing_tags", "Images missing tags"
    IMAGES_MISSING_DUPLICATE_STATE = "images_missing_duplicate_state", "Images missing duplicate state"
    IMAGES_MARKED_AS_DUPLICATES = "images_marked_as_duplicates", "Images marked as duplicates"
    IMAGES_MARKED_FOR_DELETION = "images_marked_for_deletion", "Images marked for deletion"
    IMAGES_WITH_DISABLED_LATENTS = "images_with_disabled_latents", "Images with disabled latents"


class DuplicateState(Enum):
    UNPROCESSED = None
    ORIGINAL = 1
    DUPLICATE = 2

    @classmethod
    def values(cls):
        return [state.value for state in cls]
