def disable_storage_custom_domain(storage):
    class DisableStorageCustomDomain:
        def __init__(self, storage):
            self.storage = storage

        def __enter__(self):
            if hasattr(self.storage, 'custom_domain'):
                self.original_custom_domain = self.storage.custom_domain
                self.storage.custom_domain = None

        def __exit__(self, *args):
            if hasattr(self.storage, 'custom_domain'):
                self.storage.custom_domain = self.original_custom_domain

    return DisableStorageCustomDomain(storage)
