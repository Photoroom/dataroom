from django import forms
from django.core.validators import EMPTY_VALUES
from django_filters import Filter, filters


class EmptyStringFilter(filters.BooleanFilter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        exclude = self.exclude ^ (value is False)
        method = qs.exclude if exclude else qs.filter

        return method(**{self.field_name: ""})


class WhitespacePreservingCharField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs['strip'] = False  # don't strip whitespace
        super().__init__(*args, **kwargs)


class WhitespacePreservingCharFilter(Filter):
    field_class = WhitespacePreservingCharField
