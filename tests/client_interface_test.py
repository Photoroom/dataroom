"""Structural guards over the client's public surface.

The tests elsewhere check that individual calls work. These check the shape of
the interface itself, which is what breaks silently: a namespace method renamed
without updating the flat delegate map, or a method that exists on the async
client but never made it onto the sync one. Both compile, both pass every other
test, and both surface as an AttributeError in somebody else's code.

These read the classes rather than making requests, so nothing here needs the
live server. (conftest's autouse fixtures still bring up the database and the
OpenSearch index for every test in this package.)
"""

import inspect

import pytest

from dataroom_client import DataRoomClient, DataRoomClientSync

try:
    # the layout users install: dataroom_client is the package itself
    from dataroom_client._compat import _FLAT_METHODS
    from dataroom_client.resources import _RESOURCES
except ModuleNotFoundError:
    # the layout in this repo: dataroom_client/dataroom_client/, re-exported by
    # the outer __init__, so the submodules sit one level deeper
    from dataroom_client.dataroom_client._compat import _FLAT_METHODS
    from dataroom_client.dataroom_client.resources import _RESOURCES


def _public_methods(resource_cls):
    return {
        name
        for name, value in inspect.getmembers(resource_cls, inspect.isfunction)
        if not name.startswith('_') and value.__qualname__.startswith(resource_cls.__name__)
    }


@pytest.mark.parametrize('flat,target', sorted(_FLAT_METHODS.items()))
def test_flat_method_delegates_to_a_real_namespace_method(flat, target):
    """_compat.py's map is the backward-compatibility contract.

    Renaming a namespace method without updating the map leaves the flat method
    pointing at nothing, and only a caller finds out.
    """
    namespace, method = target

    assert namespace in _RESOURCES, f'{flat} points at unknown namespace {namespace!r}'
    resource_cls = _RESOURCES[namespace]
    assert callable(getattr(resource_cls, method, None)), f'{flat} points at missing {namespace}.{method}'
    assert callable(getattr(DataRoomClient, flat, None)), f'{flat} is not on DataRoomClient'


@pytest.mark.parametrize('flat,target', sorted(_FLAT_METHODS.items()))
def test_flat_method_borrows_its_namespace_signature(flat, target):
    """A delegate that drops or reorders a parameter is a silent break.

    _compat generates each delegate from the namespace method so help() and
    notebook completion keep showing the real parameters; this pins that.
    """
    namespace, method = target
    delegate = inspect.signature(getattr(DataRoomClient, flat))
    original = inspect.signature(getattr(_RESOURCES[namespace], method))

    assert list(delegate.parameters) == list(original.parameters)


@pytest.mark.parametrize('attr,resource_cls', sorted(_RESOURCES.items()))
def test_sync_client_exposes_the_same_namespace_surface(attr, resource_cls):
    """Whatever the async client can do, the sync client can do blocking.

    The sync namespaces are built by wrapping the same resource classes, so a
    method missing here means the wrapper stopped covering something.
    """
    sync = DataRoomClientSync(api_url='http://localhost:1/api/', api_key='not-used')
    namespace = getattr(sync, attr)

    for method in _public_methods(resource_cls):
        assert callable(getattr(namespace, method, None)), f'sync client is missing {attr}.{method}'


def test_every_namespace_is_reachable_from_both_clients():
    for attr in _RESOURCES:
        assert isinstance(getattr(DataRoomClient, attr, None), property), f'{attr} missing on DataRoomClient'
        assert isinstance(getattr(DataRoomClientSync, attr, None), property), f'{attr} missing on DataRoomClientSync'
