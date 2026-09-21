"""The GraphQL transport itself: headers on the way out, redirects on the way back.

The rest of the classifier tests mock _graphql, so nothing else covers what it
actually puts on the wire — which is where the Cloudflare Access service token
lives.
"""

from typing import Any

import httpx
import pytest
from pytest_django.fixtures import SettingsWrapper

from backend.dataroom.classifiers.dagster import _access_headers, _graphql
from backend.dataroom.classifiers.runner import RunnerError


@pytest.fixture(autouse=True)
def dagster_configured(settings: SettingsWrapper) -> None:
    settings.DAGSTER_GRAPHQL_URL = 'http://dagster.test/graphql'
    settings.DAGSTER_CF_ACCESS_CLIENT_ID = None
    settings.DAGSTER_CF_ACCESS_CLIENT_SECRET = None


REQUEST = httpx.Request('POST', 'http://dagster.test/graphql')


def _answer(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> dict[str, Any]:
    """Capture the kwargs of the POST _graphql makes, answering with `response`."""
    sent: dict[str, Any] = {}

    def post(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        sent.update(kwargs)
        return response

    monkeypatch.setattr(httpx.Client, 'post', post)
    return sent


def test_no_access_headers_without_a_service_token() -> None:
    assert _access_headers() == {}


def test_no_access_headers_with_half_a_service_token(settings: SettingsWrapper) -> None:
    """An id without a secret authenticates nothing, and sending it alone would
    turn a missing-credential misconfiguration into a puzzling 403."""
    settings.DAGSTER_CF_ACCESS_CLIENT_ID = 'an-id'

    assert _access_headers() == {}


def test_service_token_travels_with_the_request(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DAGSTER_CF_ACCESS_CLIENT_ID = 'an-id'
    settings.DAGSTER_CF_ACCESS_CLIENT_SECRET = 'a-secret'
    sent = _answer(monkeypatch, httpx.Response(200, json={'data': {'version': '1.13.19'}}, request=REQUEST))

    assert _graphql('{version}', {}) == {'version': '1.13.19'}
    assert sent['headers'] == {
        'CF-Access-Client-Id': 'an-id',
        'CF-Access-Client-Secret': 'a-secret',
    }


def test_access_redirect_is_an_error_not_a_login_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Access answers an unauthenticated POST with 302, which raise_for_status()
    lets through — without this the login page's HTML fails much later as a
    KeyError on 'data'."""
    _answer(monkeypatch, httpx.Response(302, headers={'location': 'https://login.example/'}, request=REQUEST))

    with pytest.raises(RunnerError, match='Cloudflare Access'):
        _graphql('{version}', {})


def test_rest_endpoints_live_next_to_graphql() -> None:
    """The labels observation goes to the webserver's REST endpoint, which
    sits beside /graphql on the same host, behind the same Access token."""
    from backend.dataroom.classifiers.dagster import _rest_url

    assert _rest_url('/report_asset_observation/') == 'http://dagster.test/report_asset_observation/'


def test_rest_post_carries_the_service_token(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.dataroom.classifiers.dagster import _post_json

    settings.DAGSTER_CF_ACCESS_CLIENT_ID = 'an-id'
    settings.DAGSTER_CF_ACCESS_CLIENT_SECRET = 'a-secret'
    sent = _answer(monkeypatch, httpx.Response(200, json={}, request=REQUEST))

    assert (
        _post_json('http://dagster.test/report_asset_observation/', {'asset_key': ['dataroom', 'dev', 'labels']}) == {}
    )
    assert sent['headers']['CF-Access-Client-Id'] == 'an-id'
    assert sent['json'] == {'asset_key': ['dataroom', 'dev', 'labels']}
