from django import template

register = template.Library()


@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return None


@register.filter
def times(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, ZeroDivisionError):
        return None


@register.filter
def floor(value):
    try:
        return int(float(value))
    except (ValueError, ZeroDivisionError):
        return None


@register.filter
def get_key(d, key):
    return d.get(key)
