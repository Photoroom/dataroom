from django.core.validators import MinLengthValidator
from django.db import models

from backend.common.base_model import BaseModel
from backend.common.validators import AlphanumericValidator


class Tag(BaseModel):
    name = models.CharField(
        max_length=300,
        null=False,
        blank=False,
        unique=True,
        validators=[
            MinLengthValidator(1),
            AlphanumericValidator(),
        ],
    )
    description = models.TextField(blank=True, default='')
    image_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
