import io
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import torch
from botocore.exceptions import ClientError
from dataroom_client import DataRoomFile
from PIL import Image
from torch import nn

from dataroom.classifier import config, store
from dataroom.classifier import dataroom as dataroom_module
from dataroom.classifier.ml.embedders.dino import DinoV2Backbones

SPACE = "vits14"
IMAGE_SIZE = 28  # a 2x2 patch grid keeps the 60 fake sequences small
LATENT = f"{SPACE}_{IMAGE_SIZE}_features"
BUCKET = "test-models"
BACKBONE_DIM = 8


class FakeS3:
    """put/get over a dict, raising what botocore raises on a miss."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803
        assert Bucket == BUCKET
        self.objects[Key] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        assert Bucket == BUCKET
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": SimpleNamespace(read=lambda: self.objects[Key])}


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    """The store has no local backend, so every test gets its own fake bucket."""
    fake = FakeS3()
    monkeypatch.setattr(config, "MODELS_BUCKET", BUCKET)
    monkeypatch.setattr(config, "MODELS_PREFIX", "")
    monkeypatch.setattr(store, "_client", lambda: fake)
    return fake


def fake_png(image_id: str) -> bytes:
    """A positive is white, a negative is black.

    The class lives in the pixels, not in the id, so the whole chain runs for
    real: bytes -> decode -> resize -> normalize -> backbone. Only the weights
    are fake.
    """
    shade = 255 if image_id.startswith("pos") else 0
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (shade, shade, shade)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeBackbone(nn.Module):
    """DINOv2's stand-in: normalized pixels -> a token sequence.

    Token values follow the image's brightness, so a head trained on them
    really can tell the sides apart.
    """

    dim = BACKBONE_DIM

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.embed(x)

    @torch.no_grad()
    def embed(self, x: torch.Tensor) -> torch.Tensor:
        # CLS + one per 14px patch; vits14 has no registers.
        n_tokens = (x.shape[-1] // 14) ** 2 + 1
        brightness = x.mean(dim=(1, 2, 3)).view(-1, 1, 1)
        return brightness.expand(-1, n_tokens, self.dim).clone()


def _namespace(fake: "FakeDataroom", *names: str) -> SimpleNamespace:
    """One of the client's namespaces, over the fake's own methods."""
    return SimpleNamespace(**{name: getattr(fake, name) for name in names})


class FakeDataroom:
    """A DataRoomClientSync stand-in: image docs with their latents, and the
    callbacks the jobs post.

    Tokens are stored the way Dataroom stores them, as a latent: a file per
    (image, latent type), found through ``has_latents``/``lacks_latents`` and
    fetched from the ``file_direct_url`` ``return_latents`` puts on the doc.
    """

    def __init__(self) -> None:
        sides = {"pos": "cats-positives/1", "neg": "cats-negatives/1"}
        # Every example carries the tag, so ``tag/cats`` is the set covering all 60.
        self.docs: dict[str, dict[str, Any]] = {
            f"{side}-{i}": {"datasets": [dataset], "tags": ["cats"], "latents": {}}
            for side, dataset in sides.items()
            for i in range(30)
        }
        self.training_reports: list[dict[str, Any]] = []
        self.run_reports: list[dict[str, Any]] = []
        self.scores: dict[str, float] = {}
        self.embeds_written = 0  # latents written by the embed step
        self.queries: list[str] = []  # saved-query slugs a run asked the images API for
        self.val_dataset = ""
        self.images = _namespace(self, "iter", "count", "update")
        self.classifiers = _namespace(self, "get", "report_training", "report_run", "add_scores")

    env = "dev"

    def client(self) -> "FakeDataroom":
        return self

    def hold_out(self, image_ids: list[str]) -> None:
        """Held-out images stay on their side and gain the validation dataset."""
        self.val_dataset = "cats-validation/1"
        for image_id in image_ids:
            self.docs[image_id]["datasets"].append(self.val_dataset)

    def _matching(self, filters: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        # A saved query is resolved server-side, so the fake only records which
        # slug it was asked for and matches everything.
        if filters.get("query"):
            self.queries.append(filters["query"])

        def matches(doc: dict[str, Any]) -> bool:
            sets, latents = doc["datasets"], doc["latents"]
            if filters.get("datasets") and not any(d in filters["datasets"] for d in sets):
                return False
            if any(d in filters.get("datasets__ne", []) for d in sets):
                return False
            if not all(d in sets for d in filters.get("datasets__all", [])):
                return False
            if filters.get("tags") and not any(t in filters["tags"] for t in doc.get("tags", [])):
                return False

            # ``query`` and ``sources`` are accepted and match everything: the
            # fake has no search engine, and the assets only pass them through.
            if not all(t in latents for t in filters.get("has_latents") or []):
                return False
            return not any(t in latents for t in filters.get("lacks_latents") or [])

        return [(i, d) for i, d in self.docs.items() if matches(d)]

    def iter(self, fields: list[str], return_latents: list[str] | None = None, **filters: Any) -> Iterator[dict]:
        for image_id, doc in self._matching(filters):
            latents = [
                {"latent_type": t, "file_direct_url": f"latent://{image_id}/{t}"}
                for t in return_latents or []
                if t in doc["latents"]
            ]
            yield {"id": image_id, "image_direct_url": f"image://{image_id}", "latents": latents}

    def count(self, **filters: Any) -> int:
        return len(self._matching(filters))

    def update(self, image_id: str, latents: list[dict[str, Any]] | None = None) -> None:
        for latent in latents or []:
            file = latent["file"]
            assert isinstance(file, DataRoomFile)
            assert file.filename.endswith(".npy")
            data = file.bytes_io.getvalue()
            tokens = np.load(io.BytesIO(data))
            assert tokens.dtype == np.float16
            assert tokens.ndim == 2 and tokens.shape[1] == BACKBONE_DIM
            self.docs[image_id]["latents"][latent["latent_type"]] = data
            self.embeds_written += 1

    def serve(self, url: str) -> bytes:
        """What an HTTP GET of a doc's URL returns: image bytes, or a latent's."""
        scheme, _, rest = url.partition("://")
        if scheme == "image":
            return fake_png(rest)
        image_id, _, latent_type = rest.partition("/")
        return self.docs[image_id]["latents"][latent_type]

    def get(self, slug_version: str) -> dict[str, Any]:
        return {
            "embedding_space": SPACE,
            "main_pos_dataset": "cats-positives/1",
            "main_neg_dataset": "cats-negatives/1",
            "extra_pos_datasets": [],
            "extra_neg_datasets": [],
            "val_dataset": self.val_dataset,
        }

    def report_training(self, slug_version: str, training_id: str, **payload: Any) -> None:
        self.training_reports.append(payload)

    def report_run(self, slug_version: str, run_id: str, **payload: Any) -> None:
        self.run_reports.append(payload)

    def add_scores(self, slug_version: str, scores: dict[str, float], run_id: str | None = None) -> dict[str, Any]:
        self.scores.update(scores)
        return {"written": len(scores), "missing": []}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDataroom:
    fake = FakeDataroom()
    fake.hold_out([f"pos-{i}" for i in range(6)] + [f"neg-{i}" for i in range(6)])
    backbone = FakeBackbone()
    monkeypatch.setattr(DinoV2Backbones, "backbone", property(lambda self: backbone))
    monkeypatch.setattr(dataroom_module, "download_bytes", fake.serve)
    return fake
