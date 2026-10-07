"""The model store, over the fake bucket every test runs against."""

import pytest
import torch

from dataroom.classifier import config, store


@pytest.fixture
def bucket(isolated_store):
    return isolated_store


def test_round_trips_a_head_through_the_bucket(bucket):
    record = store.save_model("dinov2_vits14", 384, {"epochs": 1}, {"auc": 0.9}, {"weight": torch.zeros(2, 3)})

    model_id = record["id"]
    assert set(bucket.objects) == {
        f"classifiers/models/{model_id}/head.pt",
        f"classifiers/models/{model_id}/meta.json",
    }
    assert store.get_record(model_id) == record
    assert store.load_head(model_id)["weight"].shape == (2, 3)


def test_prefix_shares_a_bucket(bucket, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MODELS_PREFIX", "dataroom/")

    record = store.save_model("dinov2_vits14", 384, {}, {}, {"weight": torch.zeros(1)}, env="prod")

    assert all(key.startswith("dataroom/prod/classifiers/models/") for key in bucket.objects)
    assert store.get_record(record["id"], "prod")["id"] == record["id"]


def test_env_scopes_the_keys(bucket):
    record = store.save_model("dinov2_vits14", 384, {}, {}, {"weight": torch.zeros(1)}, env="prod")

    assert all(key.startswith("prod/classifiers/models/") for key in bucket.objects)
    assert store.get_record(record["id"], "prod")["id"] == record["id"]
    # the same id under another environment is a different object
    with pytest.raises(FileNotFoundError):
        store.get_record(record["id"], "dev")


def test_unknown_model_is_a_file_not_found(bucket):
    with pytest.raises(FileNotFoundError):
        store.get_record("nosuchmodel")


def test_without_a_bucket_nothing_is_stored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MODELS_BUCKET", "")

    with pytest.raises(RuntimeError, match="CLASSIFIER_MODELS_BUCKET"):
        store.get_record("anything")
