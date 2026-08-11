"""Resource namespaces - ``client.datasets.list()``, ``client.groups.create_many()``, ...

Each namespace owns its endpoints' implementations and is bound to the client
it was reached through, which supplies the HTTP transport. On ``DataRoomClient``
the methods return awaitables; ``DataRoomClientSync`` wraps each namespace so
the same methods block. The flat methods (``get_datasets``, ``create_dataset``,
...) remain as thin delegates - see ``_compat.py``.

Read methods that page (list/filter, iter) follow the server cursor up to
``limit``, so pagination is automatic.
"""

from .datasets import DatasetsResource
from .groups import GroupsResource, GroupTypesResource, RolesResource
from .images import ImagesResource
from .queries import QueriesResource
from .tags import TagsResource

# The namespace properties added to both client classes, and (via ``_compat``)
# the metadata source for the flat delegates.
_RESOURCES = {
    "datasets": DatasetsResource,
    "groups": GroupsResource,
    "images": ImagesResource,
    "roles": RolesResource,
    "group_types": GroupTypesResource,
    "queries": QueriesResource,
    "tags": TagsResource,
}


def install_resources(cls):
    """Class decorator: add a cached property per resource to a client class.

    Each access returns the same namespace instance, built by the class's
    ``_make_resource`` hook - the async client binds the resource to itself,
    the sync client wraps it so its methods block.
    """
    for attr, resource_cls in _RESOURCES.items():
        def make(resource_cls):
            def getter(self, _rc=resource_cls):
                cache = self.__dict__.setdefault("_resource_cache", {})
                if _rc not in cache:
                    cache[_rc] = self._make_resource(_rc)
                return cache[_rc]

            return property(getter)

        setattr(cls, attr, make(resource_cls))
    return cls
