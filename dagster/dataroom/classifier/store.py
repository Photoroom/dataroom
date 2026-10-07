"""Store for trained heads, in object storage.

One model id, two objects: meta.json (backbone, params, metrics) and head.pt (the
weights), under the name of the Dataroom that trained it. Every run is its own
Job pod, so a head written to the pod's own disk would be gone before the apply
run that loads it. There is no local backend for that reason.

Callers only touch save_model/get_record/load_head.
"""

import io
import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import boto3
import torch
from botocore.exceptions import ClientError

from dataroom.classifier import config

META = "meta.json"
HEAD = "head.pt"
_MISSING = {"NoSuchKey", "NoSuchBucket", "404"}


@lru_cache(maxsize=1)
def _client() -> Any:
    return boto3.client("s3", endpoint_url=config.S3_ENDPOINT_URL or None)


def _bucket() -> str:
    if not config.MODELS_BUCKET:
        raise RuntimeError("CLASSIFIER_MODELS_BUCKET is not configured, so no model can be stored or loaded")
    return config.MODELS_BUCKET


# The store's own segment, after the shared-bucket prefix and the environment
# scope: <prefix>/<env>/classifiers/models/<model id>/<name>.
_STORE_SEGMENT = "classifiers/models/"


def _scope(env: str) -> str:
    return f"{env}/" if env else ""


def _key(env: str, model_id: str, name: str) -> str:
    return f"{config.MODELS_PREFIX}{_scope(env)}{_STORE_SEGMENT}{model_id}/{name}"


def _put(env: str, model_id: str, name: str, body: bytes) -> None:
    _client().put_object(Bucket=_bucket(), Key=_key(env, model_id, name), Body=body)


def _get(env: str, model_id: str, name: str) -> bytes:
    try:
        response = _client().get_object(Bucket=_bucket(), Key=_key(env, model_id, name))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in _MISSING:
            raise FileNotFoundError(f"no {name} for model {model_id!r} in {_bucket()}") from exc
        raise
    body: bytes = response["Body"].read()
    return body


def save_model(
    backbone: str,
    dim: int,
    params: dict[str, Any],
    metrics: dict[str, Any],
    state_dict: dict[str, Any],
    env: str = "",
) -> dict[str, Any]:
    model_id = uuid.uuid4().hex[:12]
    record = {
        "id": model_id,
        "backbone": backbone,
        "dim": dim,
        "params": params,
        "metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    # Weights first, so meta.json is the commit marker.
    _put(env, model_id, HEAD, buffer.getvalue())
    _put(env, model_id, META, json.dumps(record, indent=2).encode())
    return record


def get_record(model_id: str, env: str = "") -> dict[str, Any]:
    record: dict[str, Any] = json.loads(_get(env, model_id, META))
    return record


def list_records(env: str = "") -> list[dict[str, Any]]:
    prefix = f"{config.MODELS_PREFIX}{_scope(env)}{_STORE_SEGMENT}"
    pages = _client().get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=prefix)
    keys = [obj["Key"] for page in pages for obj in page.get("Contents", []) if obj["Key"].endswith(f"/{META}")]
    records = [get_record(key[len(prefix) :].split("/")[0], env) for key in keys]
    return sorted(records, key=lambda r: r["created_at"], reverse=True)


def load_head(model_id: str, env: str = "") -> dict[str, Any]:
    head: dict[str, Any] = torch.load(io.BytesIO(_get(env, model_id, HEAD)), weights_only=True)
    return head
