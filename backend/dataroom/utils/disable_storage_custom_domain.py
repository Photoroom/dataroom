from django.conf import settings


def disable_storage_custom_domain(storage):
    class DisableStorageCustomDomain:
        def __init__(self, storage):
            self.storage = storage

        def __enter__(self):
            if hasattr(self.storage, 'custom_domain'):
                self.original_custom_domain = self.storage.custom_domain
                # In local dev, use the fallback domain so URLs are browser-accessible
                # (otherwise it would use internal Docker network URL like minio:9000)
                # NOTE:
                # for non-local environment STORAGE_DIRECT_URL_DOMAIN does not exist and fallback = None works as before
                fallback = getattr(settings, 'STORAGE_DIRECT_URL_DOMAIN', None)
                self.storage.custom_domain = fallback

        def __exit__(self, *args):
            if hasattr(self.storage, 'custom_domain'):
                self.storage.custom_domain = self.original_custom_domain

    return DisableStorageCustomDomain(storage)
