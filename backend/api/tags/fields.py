from django.core.validators import RegexValidator
from rest_framework.fields import CharField


class TagNameValidator(RegexValidator):
    message = 'Tags can only contain alphanumeric characters, dashes, and underscores'
    code = 'alphanumeric_characters_only'
    regex = r'^[a-zA-Z0-9_-]+$'


class TagNameField(CharField):
    def __init__(self, **kwargs):
        kwargs['min_length'] = 1
        kwargs['max_length'] = 300
        super().__init__(**kwargs)
        self.validators.append(TagNameValidator())
