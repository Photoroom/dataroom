"""The HTTP calls to Dagster: the headers they send and how they handle a redirect.

The other classifier tests mock _graphql, so only these tests cover the request itself.
"""

from typing import Any

import environ
import httpx
import pytest
from pytest_django.fixtures import SettingsWrapper

from backend.dataroom.classifiers.dagster import _graphql, _post_json, _url
from backend.dataroom.classifiers.runner import RunnerError


@pytest.fixture(autouse=True)
def dagster_configured(settings: SettingsWrapper) -> None:
    settings.DAGSTER_URL = 'http://dagster.test/'
    settings.DAGSTER_HTTP_HEADERS = {}


REQUEST = httpx.Request('POST', 'http://dagster.test/graphql')


def _answer(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> dict[str, Any]:
    """Capture the kwargs of the POST _graphql makes, answering with `response`."""
    sent: dict[str, Any] = {}

    def post(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        sent.update(kwargs)
        return response

    monkeypatch.setattr(httpx.Client, 'post', post)
    return sent


def test_headers_setting_parses_values_with_equals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens are often base64, so a value may end in '='."""
    monkeypatch.setenv('DAGSTER_HTTP_HEADERS', 'Authorization=Bearer abc==,X-Other=1')

    assert environ.Env().dict('DAGSTER_HTTP_HEADERS') == {'Authorization': 'Bearer abc==', 'X-Other': '1'}


def test_headers_travel_with_the_request(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DAGSTER_HTTP_HEADERS = {'Authorization': 'Bearer abc'}
    sent = _answer(monkeypatch, httpx.Response(200, json={'data': {'version': '1.13.19'}}, request=REQUEST))

    assert _graphql('{version}', {}) == {'version': '1.13.19'}
    assert sent['headers'] == {'Authorization': 'Bearer abc'}


def test_redirect_is_an_error_not_a_login_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """An auth proxy answers an unauthenticated POST with 302, which
    raise_for_status() lets through. Without this the login page's HTML fails
    much later as a KeyError on 'data'."""
    _answer(monkeypatch, httpx.Response(302, headers={'location': 'https://login.example/'}, request=REQUEST))

    with pytest.raises(RunnerError, match='DAGSTER_HTTP_HEADERS'):
        _graphql('{version}', {})


def test_url_joins_the_path_without_a_double_slash() -> None:
    assert _url('/report_asset_observation/') == 'http://dagster.test/report_asset_observation/'


def test_rest_post_carries_the_headers(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DAGSTER_HTTP_HEADERS = {'Authorization': 'Bearer abc'}
    sent = _answer(monkeypatch, httpx.Response(200, json={}, request=REQUEST))

    assert (
        _post_json('http://dagster.test/report_asset_observation/', {'asset_key': ['dataroom', 'dev', 'labels']}) == {}
    )
    assert sent['headers'] == {'Authorization': 'Bearer abc'}
    assert sent['json'] == {'asset_key': ['dataroom', 'dev', 'labels']}
