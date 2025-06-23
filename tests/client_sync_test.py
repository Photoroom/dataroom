import inspect
from dataroom_client.dataroom_client.client import DataRoomClientSync


def get_public_async_methods(client_class):
    """Returns a set of public async method names for a class."""
    return {
        name for name, func in inspect.getmembers(client_class, inspect.iscoroutinefunction)
        if not name.startswith('_')
    }

def test_sync_client_mirrors_async_client(DataRoom):
    """
    Verify that DataRoomClientSync has a sync method for every public async
    method in DataRoomClient.
    """
    async_methods = get_public_async_methods(DataRoom)
    sync_client_instance = DataRoomClientSync(api_url=DataRoom.api_url, api_key=DataRoom.api_key)
    for method_name in async_methods:
        async_method = getattr(DataRoom, method_name)
        sync_method_wrapper = getattr(sync_client_instance, method_name)

        assert async_method is not None, (
            f"Method {method_name} is in DataRoomClient but missing from DataRoomClientSync"
        )

        # The __doc__ of the wrapped function should be the same as the original
        assert sync_method_wrapper.__doc__ == async_method.__doc__, (
            f"Docstring for '{method_name}' does not match between sync and async clients."
        ) 
