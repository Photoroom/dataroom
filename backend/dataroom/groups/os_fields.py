from django.conf import settings


def text_to_keyword_field(name: str) -> str:
    """Map a group denorm field name to the queryable OpenSearch field.

    ``group_ids`` and ``memberships`` are ``keyword`` on a freshly-created index, so
    exact-match (term/terms/prefix) queries target them directly. Some existing indexes
    had these dynamically mapped as ``text`` + ``.keyword``; on those environments
    ``OPENSEARCH_GROUP_FIELD_SUFFIX`` is ``.keyword`` so queries hit the keyword
    sub-field instead of the analyzed text field (which never matches the encoded
    ``type::uuid`` / ``role::type::uuid`` ids).

    Use this only for *queryable* field references. Painless scripts read
    ``ctx._source.*`` (the raw JSON, mapping-independent) and ``exists`` targets the
    parent field, so neither needs the suffix.
    """
    return f"{name}{settings.OPENSEARCH_GROUP_FIELD_SUFFIX}"
