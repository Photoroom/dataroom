import json
import uuid

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import NotFound, ValidationError

from backend.api import exceptions
from backend.api.exceptions import GENERIC_DETAIL, api_exception_handler, json_server_error
from backend.config.urls import handler500

ERROR_ID = '0123456789ab'


@pytest.fixture(autouse=True)
def seed_group_types():
    # overrides conftest's, no db needed here
    yield


@pytest.fixture(autouse=True)
def _fixed_error_id(monkeypatch):
    monkeypatch.setattr(exceptions.uuid, 'uuid4', lambda: uuid.UUID(ERROR_ID + '0' * 20))


@pytest.fixture
def request_():
    return RequestFactory().get('/api/images/')


def _context(request):
    return {'request': request, 'view': None}


def test_an_unhandled_exception_becomes_a_json_500(request_):
    response = api_exception_handler(RuntimeError('opensearch is on fire'), _context(request_))
    assert response.status_code == 500
    assert response.data == {'detail': GENERIC_DETAIL, 'error_id': ERROR_ID}


def test_an_unhandled_exception_rolls_the_transaction_back(request_, monkeypatch):
    # checks that rollback on an unhandled exception still works as before
    rolled_back = []
    monkeypatch.setattr(exceptions, 'set_rollback', lambda: rolled_back.append(True))
    api_exception_handler(RuntimeError('boom'), _context(request_))
    assert rolled_back


def test_the_message_never_leaks_internals(request_):
    response = api_exception_handler(RuntimeError('relation "dataroom_image" does not exist'), _context(request_))
    assert response.data == {'detail': GENERIC_DETAIL, 'error_id': ERROR_ID}


@override_settings(DEBUG=True)
def test_debug_keeps_the_exception_for_the_developer(request_):
    response = api_exception_handler(RuntimeError('boom'), _context(request_))
    assert response.data == {'detail': 'RuntimeError: boom', 'error_id': ERROR_ID}


def test_every_500_is_traceable_to_its_log_line(request_, caplog):
    api_exception_handler(RuntimeError('boom'), _context(request_))
    assert ERROR_ID in caplog.text
    assert 'GET /api/images/' in caplog.text
    assert 'RuntimeError: boom' in caplog.text


@pytest.mark.parametrize(
    ('exc', 'expected_status', 'expected_body'),
    [
        (NotFound(), 404, {'detail': 'Not found.'}),
        (Http404(), 404, {'detail': 'Not found.'}),
        (ValidationError({'slug': ['This field is required.']}), 400, {'slug': ['This field is required.']}),
    ],
)
def test_errors_drf_already_handles_are_left_alone(exc, expected_status, expected_body, request_):
    response = api_exception_handler(exc, _context(request_))
    assert response.status_code == expected_status
    assert response.data == expected_body


def test_handler500_answers_json_under_api():
    response = handler500(RequestFactory().get('/api/images/'))
    assert response.status_code == 500
    assert response['Content-Type'] == 'application/json'
    assert json.loads(response.content) == {'detail': GENERIC_DETAIL, 'error_id': ERROR_ID}


def test_handler500_still_renders_html_for_fe_views():
    response = handler500(RequestFactory().get('/images'))
    assert response.status_code == 500
    assert 'application/json' not in response['Content-Type']


def test_json_server_error_logs_the_live_traceback(caplog):
    try:
        raise RuntimeError('from middleware')
    except RuntimeError:
        response = json_server_error(RequestFactory().get('/api/images/'))
    assert json.loads(response.content) == {'detail': GENERIC_DETAIL, 'error_id': ERROR_ID}
    assert 'from middleware' in caplog.text
