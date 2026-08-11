"""Compile tests for the roles image filters.

roles gained the same operator variants as tags (__ne / __all / __ne_all / __empty);
unlike tags (plain terms) roles match by prefix on the encoded `memberships` array.
These assert the full compiled OpenSearch query, no indexed data needed.
"""

from backend.api.images.filters import OSImageFilterSet
from backend.dataroom.models.os_image import OSImage

# Base clause every search carries (non-deleted images).
NOT_DELETED = {'bool': {'filter': [{'term': {'is_deleted': False}}]}}


def _compiled(data: dict) -> dict:
    filterset = OSImageFilterSet(data=data, search=OSImage.objects.search())
    assert filterset.is_valid(), filterset.errors
    return filterset.filtered_search.to_dict()['query']


def _prefixes(*roles: str) -> list[dict]:
    return [{'prefix': {'memberships': f'{r}::'}} for r in roles]


def test_roles_any_compiles_to_should_prefixes() -> None:
    assert _compiled({'roles': 'hero,thumb'}) == {
        'bool': {'filter': [NOT_DELETED, {'bool': {'should': _prefixes('hero', 'thumb'), 'minimum_should_match': 1}}]}
    }


def test_roles_all_compiles_to_must_prefixes() -> None:
    assert _compiled({'roles__all': 'hero,thumb'}) == {
        'bool': {'filter': [NOT_DELETED, {'bool': {'must': _prefixes('hero', 'thumb')}}]}
    }


def test_roles_ne_compiles_to_must_not_prefixes() -> None:
    assert _compiled({'roles__ne': 'hero'}) == {
        'bool': {'filter': [NOT_DELETED, {'bool': {'must_not': _prefixes('hero')}}]}
    }


def test_roles_ne_all_compiles_to_must_not_must() -> None:
    assert _compiled({'roles__ne_all': 'hero,thumb'}) == {
        'bool': {'filter': [NOT_DELETED, {'bool': {'must_not': [{'bool': {'must': _prefixes('hero', 'thumb')}}]}}]}
    }


def test_roles_empty_true_compiles_to_must_not_exists() -> None:
    assert _compiled({'roles__empty': 'true'}) == {
        'bool': {'filter': [NOT_DELETED, {'bool': {'must_not': [{'exists': {'field': 'memberships'}}]}}]}
    }


def test_roles_empty_false_compiles_to_exists() -> None:
    assert _compiled({'roles__empty': 'false'}) == {
        'bool': {'filter': [NOT_DELETED, {'exists': {'field': 'memberships'}}]}
    }
