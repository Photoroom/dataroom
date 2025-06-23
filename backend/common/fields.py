from django.conf import settings
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models

from backend.common.validators import AlphanumericValidator


class ImageIdField(models.CharField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validators.append(AlphanumericValidator())
        self.validators.append(MinLengthValidator(settings.IMAGE_ID_MIN_LENGTH))
        self.validators.append(MaxLengthValidator(settings.IMAGE_ID_MAX_LENGTH))
