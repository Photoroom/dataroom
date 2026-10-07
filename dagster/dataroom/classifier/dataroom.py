"""Dataroom for the *_from_dataroom jobs: the published dataroom-client, plus
the things it does not do — fetching bytes from the URLs on a doc, and
turning a token sequence into the latent Dataroom stores it as.

One Dagster serves several Dataroom deployments; which one a run talks to is
the dataroom resource's env config. See DataroomResource.

Storage URLs in image docs may point at hosts only the docker host can resolve
(localhost:9000 for minio). DATAROOM_REWRITE_HOSTS ("from=to,from=to") rewrites
them. In a real deployment the URLs are public S3 and the list is empty.
"""

import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

import dagster as dg
import httpx
import numpy as np
from dataroom_client import DataRoomClientSync, DataRoomFile
from dataroom_client.models import DataRoomError

IO_WORKERS = 8
PUSH_RETRIES = 4


def _rewrites() -> dict[str, str]:
    pairs = os.environ.get("DATAROOM_REWRITE_HOSTS", "")
    return dict(pair.split("=", 1) for pair in pairs.split(",") if "=" in pair)


@cache
def _http() -> httpx.Client:
    """One pooled client for bytes. ``httpx.get`` builds and discards a
    client per call, so every file paid for a fresh TLS handshake."""
    return httpx.Client(timeout=60, follow_redirects=True)


def download_bytes(url: str) -> bytes:
    """The one function that reads a doc's URL; everything below goes through it."""
    for src, dst in _rewrites().items():
        url = url.replace(src, dst)
    # S3 closes idle pooled connections, and the next GET on one fails with
    # RemoteProtocolError. Retry those and 5xx, let a 4xx fail at once.
    for attempt in range(PUSH_RETRIES):
        try:
            response = _http().get(url)
            response.raise_for_status()
            return response.content
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status < 500 or attempt == PUSH_RETRIES - 1:
                raise
            time.sleep(2**attempt)


def download_many(urls: list[str]) -> list[bytes]:
    """``download_bytes`` over a list, concurrently and in order."""
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as pool:
        return list(pool.map(download_bytes, urls))


def download_to(url: str, path: Path) -> Path:
    """The file's own bytes on disk, unmodified. Writing what we received
    rather than a re-encoded PIL save keeps materializing lossless and cheap."""
    path.write_bytes(download_bytes(url))
    return path


def latent_type(backbone: str, image_size: int) -> str:
    """The Dataroom latent holding one feature type for an image.

    A feature type is a backbone AND the size the image was resized to: the
    same backbone at twice the size emits four times the patches, each
    covering a quarter of the image, and a head trained at one size may be
    applied at another on purpose. Naming both keeps the two from ever being
    mistaken for each other.

    Latents are Dataroom's per-image files: ``has_latents``/``lacks_latents``
    filter on them and ``return_latents`` puts their URL on the doc. The
    embedding fields cannot hold a sequence, so this is where features live.
    """
    return f"{backbone}_{image_size}_features"


def push_latent(client: DataRoomClientSync, image_id: str, latent: str, tokens: np.ndarray) -> None:
    """Store one image's token sequence as an fp16 ``.npy`` latent.

    Half precision is the storage recipe the bench validated: no measurable
    AP cost against fp32, at half the bytes. One PUT per image — latents are
    multipart uploads, which the bulk endpoint does not take.
    """
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(tokens, dtype=np.float16))
    payload = buffer.getvalue()
    # Under IO_WORKERS concurrent uploads Dataroom answers the odd 500; the
    # PUT is idempotent, so retry those and let a 4xx fail at once.
    for attempt in range(PUSH_RETRIES):
        file = DataRoomFile.from_bytesio(io.BytesIO(payload), extension=".npy")
        try:
            client.images.update(image_id, latents=[{"latent_type": latent, "file": file}])
            return
        except (DataRoomError, httpx.TransportError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status < 500 or attempt == PUSH_RETRIES - 1:
                raise
            time.sleep(2**attempt)


def push_latents(client: DataRoomClientSync, latent: str, tokens: dict[str, np.ndarray]) -> None:
    """``push_latent`` for a batch, concurrently: the client runs on one
    background event loop, so calls from several threads are safe."""
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as pool:
        list(pool.map(lambda item: push_latent(client, item[0], latent, item[1]), tokens.items()))


def fetch_latents(urls: list[str]) -> list[np.ndarray]:
    """The token sequences behind latent URLs, in order, as stored (fp16)."""
    return [np.load(io.BytesIO(data)) for data in download_many(urls)]


_ENVS = ("dev", "eval", "prod")


class DataroomResource(dg.ConfigurableResource):
    """One client per Dataroom deployment. Which deployment is the resource's
    ``env`` config — "prod" unless the run configures otherwise
    (``resources: {dataroom: {config: {env: dev}}}``) — and the resource
    resolves that name to DATAROOM_<ENV>_API_URL / DATAROOM_<ENV>_API_TOKEN.
    ``env`` also keys the model store's paths, so one deployment's models stay
    out of another's.
    """

    env: str = "prod"

    def credentials(self) -> tuple[str, str]:
        """(base url, token) of this deployment, for a process that has to
        reach it without this resource: a remote compute step."""
        if self.env not in _ENVS:
            raise RuntimeError(f"env={self.env!r} — expected one of {list(_ENVS)}")
        prefix = f"DATAROOM_{self.env.upper()}_"
        base_url = os.environ.get(f"{prefix}API_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError(f"{prefix}API_URL is not configured")
        return base_url, os.environ.get(f"{prefix}API_TOKEN", "")

    def client(self) -> DataRoomClientSync:
        return dataroom_client(*self.credentials())


def dataroom_client(base_url: str, token: str) -> DataRoomClientSync:
    return DataRoomClientSync(api_url=f"{base_url.rstrip('/')}/api/", api_key=token, timeout=120)
