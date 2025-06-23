from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models

from backend.common.base_model import BaseModel
from backend.common.validators import AlphanumericValidator


class LatentType(BaseModel):
    name = models.CharField(
        max_length=settings.LATENT_TYPE_MAX_LENGTH,
        unique=True,
        validators=[
            MinLengthValidator(settings.LATENT_TYPE_MIN_LENGTH),
            AlphanumericValidator(),
        ],
    )
    is_mask = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    is_mapped = models.BooleanField(
        default=False,
        editable=False,
        help_text="Is this field present in OpenSearch mapping?",
    )
    image_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    @classmethod
    def from_os_latent(cls, os_latent):
        """
        Convert OSLatent to LatentType
        """
        return cls(
            name=os_latent.latent_type,
        )
