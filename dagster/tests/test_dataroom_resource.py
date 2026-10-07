"""Which Dataroom a run talks to: the resource's env config, prod by default."""

from types import SimpleNamespace

import numpy as np
import pytest
from dataroom_client.models import DataRoomError

from dataroom.classifier import dataroom
from dataroom.classifier.dataroom import DataroomResource


def test_resolves_the_configured_deployment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATAROOM_EVAL_API_URL", "https://dataroom-eval.example.com/")
    monkeypatch.setenv("DATAROOM_EVAL_API_TOKEN", "eval-token")

    client = DataroomResource(env="eval").client()

    assert client.api_url.startswith("https://dataroom-eval.example.com/api")


def test_the_default_deployment_is_prod():
    assert DataroomResource().env == "prod"


def test_an_unknown_deployment_is_refused():
    with pytest.raises(RuntimeError, match="expected one of"):
        DataroomResource(env="staging").client()


def test_an_unconfigured_deployment_says_which_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATAROOM_PROD_API_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATAROOM_PROD_API_URL"):
        DataroomResource().client()


def test_a_latent_upload_retries_a_server_error_but_not_a_client_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dataroom.time, "sleep", lambda s: None)
    calls = []

    def flaky(image_id, latents):
        calls.append(image_id)
        if len(calls) < 3:
            raise DataRoomError("boom", response=SimpleNamespace(status_code=500, text="boom"))

    client = SimpleNamespace(images=SimpleNamespace(update=flaky))
    dataroom.push_latent(client, "img", "vitb14_518_features", np.zeros((2, 2)))
    assert len(calls) == 3

    def bad_request(image_id, latents):
        raise DataRoomError("nope", response=SimpleNamespace(status_code=400, text="nope"))

    client = SimpleNamespace(images=SimpleNamespace(update=bad_request))
    with pytest.raises(DataRoomError):
        dataroom.push_latent(client, "img", "vitb14_518_features", np.zeros((2, 2)))
