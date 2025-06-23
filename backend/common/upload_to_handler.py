from django.conf import settings
from django.utils.deconstruct import deconstructible


@deconstructible
class UploadToHandler:
    def __init__(self, prefix, instance_attribute):
        self.prefix = prefix
        self.instance_attribute = instance_attribute

    def __call__(self, instance, filename):
        attr = getattr(instance, self.instance_attribute)
        ext = str(filename.replace('/', '').split('.')[-1:][0])[:4]
        filename = f"{self.prefix}/{attr}.{ext}"
        if len(filename) > settings.FILENAME_MAX_LENGTH:
            raise ValueError(f"File name too long for UploadToHandler: {filename}")
        return filename
