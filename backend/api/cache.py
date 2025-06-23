from functools import wraps

from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response


def cache_response(func):
    """
    Cache the response of a view according to the header Cache-Control=max-age=60
    """

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        cache_control = request.headers.get('Cache-Control', '')
        if 'max-age' in cache_control:
            cache_control = cache_control.split(',')
            cache_ttl = next((x for x in cache_control if 'max-age' in x), None)
            if cache_ttl:
                try:
                    cache_ttl = min(abs(int(cache_ttl.split('=')[1])), settings.API_CACHE_MAX_TTL)
                except (ValueError, KeyError):
                    cache_ttl = settings.API_CACHE_DEFAULT_TTL
            # try to retrieve cached response
            cache_key = request.build_absolute_uri()
            cached_response = cache.get(cache_key)

            if cached_response is not None:
                # return cached response
                return Response(
                    cached_response,
                    headers={'Cache-Control': f'cached, max-age={cache_ttl}'},
                )
            else:
                # cache the whole request
                response = func(self, request, *args, **kwargs)
                cache.set(cache_key, response.data, timeout=cache_ttl)
                response['Cache-Control'] = f'max-age={cache_ttl}'
                return response

        return func(self, request, *args, **kwargs)

    return wrapper
