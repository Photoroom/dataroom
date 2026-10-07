"""JSON error responses for the API."""

import logging
import sys
import uuid

from django.conf import settings
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)

GENERIC_DETAIL = 'Internal server error.'


def _payload(exc: BaseException | None, request) -> dict:
    error_id = uuid.uuid4().hex[:12]
    logger.error(
        'Unhandled API exception [%s] %s %s',
        error_id,
        getattr(request, 'method', '?'),
        getattr(request, 'path', '?'),
        exc_info=exc,
    )
    detail = GENERIC_DETAIL
    if settings.DEBUG and exc is not None:
        detail = f'{type(exc).__name__}: {exc}'
    return {'detail': detail, 'error_id': error_id}


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    set_rollback()
    return Response(_payload(exc, context.get('request')), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def json_server_error(request):
    # Django calls this mid-exception, so the traceback is still on sys.exc_info().
    return JsonResponse(_payload(sys.exc_info()[1], request), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
