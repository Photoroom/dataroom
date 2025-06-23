import numpy as np
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.deconstruct import deconstructible


@deconstructible
class AlphanumericValidator(RegexValidator):
    message = 'Can only contain alphanumeric characters, dashes, and underscores'
    code = 'alphanumeric_characters_only'
    regex = r'^[a-zA-Z0-9_-]+$'


@deconstructible
class VectorRegexValidator(RegexValidator):
    message = 'Invalid vector format'
    code = 'invalid_vector_format'
    regex = r'^\[[\s\d,.\-\+eE]+\]$'


@deconstructible
class NormalizedVectorValidator:
    message = "Vector must be normalized"
    code = "vector_not_normalized"

    def __init__(self, tolerance=1e-3):
        self.tolerance = tolerance

    def __call__(self, value):
        if not np.abs(np.linalg.norm(value) - 1) < self.tolerance:
            raise ValidationError(self.message, code=self.code)
