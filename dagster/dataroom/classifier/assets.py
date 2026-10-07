"""The Dataroom classifier pipelines, as Dagster assets.

One graph per Dataroom deployment (dev, eval, prod), built by ``build_env``:
asset keys are ``dataroom/<env>/<name>``, the group ``dataroom_<env>``, the
jobs ``dataroom_<env>_train_classifier`` and ``_apply_classifier``. Dataroom
launches the jobs over Dagster's GraphQL API with
the partition key as the ``dagster/partition`` run tag; the assets call back
over its REST API.

    labels               external, partitioned by classifier ``<slug>/<version>``.
                         Dataroom reports an observation whenever a version's
                         labelled sets change: the positive, negative and
                         held-out datasets and the backbone. Its data version
                         is the sorted slug_versions, so the head goes stale
                         when the list changes and not otherwise.
    trained_classifier   partitioned by classifier. Reads the labels
                         observation, trains the query head on the examples'
                         pixels, saves it to the model store, reports onto the
                         training record. Data version = model id.
    target_embeddings    partitioned by classifier × set. Stores the backbone's
                         token latent for the set's images that lack it.
    classified_images    partitioned by classifier × set. Scores the set from
                         the stored latents with the classifier's head. Depends
                         on target_embeddings (same key) and trained_classifier
                         (through the classifier dimension), so a retrain marks
                         every set it was applied to stale.
    image_embeddings     partitioned by set × backbone. Feature extraction on
                         its own: run the backbone over a set, with no
                         classifier and no model involved. Writes the same
                         latent target_embeddings does, so whichever runs first
                         does the work and the other finds it done.
A set is one Dataroom image selection, named the way Dataroom names it:
``dataset/<slug>/<v>``, ``tag/<name>``, ``source/<name>`` or
``query/<slug>``. A two-dimensional key is the dimension values joined by
``|`` in alphabetical order of dimension name, so a scores partition reads
``cats/2|dataset/shop/3``.

Training reads pixels, not stored features: the flip augmentation only
exists in image space, and the example sets are small. Apply is the other
way round, the target is a corpus, so it scores from the features
``target_embeddings`` stores: the backbone's full token sequence, as the
Dataroom latent ``<backbone>_<image_size>_features`` (fp16 .npy). Backbone
and size together are the feature type; a head trained at one size may be
applied at another.

Nothing here reads a classifier's definition from Dataroom's API: *which*
datasets a version trains on is what Dataroom pinned on the labels
observation, and the same facts travel to a remote compute backend in its
payload. Their members are still read live, so a dataset nobody froze can
change while a run works -- the owned ones cannot, because training locks the
version, but a borrowed extra can.
"""

import importlib
import os
import tempfile
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from itertools import islice
from logging import Logger
from pathlib import Path
from typing import Any, Protocol, cast

import dagster as dg
import numpy as np
import torch
from dataroom_client import DataRoomClientSync
from torch.utils.data import DataLoader

from dataroom.classifier import config as settings
from dataroom.classifier import store
from dataroom.classifier.dataroom import (
    IO_WORKERS,
    DataroomResource,
    download_many,
    download_to,
    fetch_latents,
    latent_type,
    push_latents,
)
from dataroom.classifier.ml.embedders import DEFAULT_BACKBONE, DEFAULT_IMAGE_SIZE
from dataroom.classifier.ml.embedders.dino import DinoV2Backbones
from dataroom.classifier.ml.heads import Config, QueryHead
from dataroom.classifier.ml.train_utils import (
    BinaryDataset,
    TrainArgs,
    decode_bytes,
    embed_tokens,
    evaluate,
    prepare_image,
    train_head,
)

ENVS = ("dev", "eval", "prod")

# Bump when what an asset produces changes meaning. Dagster then marks every
# materialized partition stale, which Dataroom reads back as "trained with
# older code, retrain?". Nothing retrains on its own.
TRAIN_CODE_VERSION = "query-head-1"
EMBED_CODE_VERSION = "dinov2-tokens-1"

PARTITION_TAG = "dagster/partition"
DATA_VERSION_TAG = "dagster/data_version"
SET_KINDS = ("dataset", "tag", "source", "query")

SCORE_BATCH = 500  # matches the scores endpoint's per-call limit
HEAD_BATCH = 64  # 64 x [1374, 768] fp32 is ~270 MB
EMBED_BATCH_SIZE = 64
PAGE_SIZE = 500

# The pod logs through Dagster, a remote step through logging.
Log = dg.DagsterLogManager | Logger


class ComputeBackend(Protocol):
    """Where the GPU steps run. A backend is a module named by CLASSIFIER_COMPUTE."""

    def run_step(
        self, step: str, payload: dict[str, Any], dataroom: DataroomResource, run_id: str, log: Log
    ) -> dict[str, Any]: ...


def _compute() -> ComputeBackend:
    name = settings.COMPUTE
    if name == "local":
        name = "dataroom.classifier.local"
    elif "." not in name:
        name = f"dataroom.private.{name}"
    return cast(ComputeBackend, importlib.import_module(name))


# --- sets: one Dataroom image selection, as a partition key ------------------


def set_key(kind: str, value: str) -> str:
    """The partition key of one Dataroom image selection. Dataroom builds the
    same string, so the two sides agree on which partition a run is.

    Every kind is named by something Dataroom already treats as a name: a
    dataset's slug/version, a tag, a source, a saved query's slug. All of them
    are short, stable and free of the "|" that joins a two-dimensional key, so
    the key carries the whole selection and no part of it travels in the run
    config.
    """
    if kind not in SET_KINDS:
        raise ValueError(f"unknown set kind {kind!r}; expected one of {SET_KINDS}")
    if not value:
        raise ValueError(f"a {kind} set needs a value")
    if "|" in value:
        raise ValueError(f"a set name cannot contain '|', which joins the dimensions of a key: {value!r}")
    return f"{kind}/{value}"


def set_filter(key: str) -> dict[str, Any]:
    """The images filter behind a set key."""
    kind, _, value = key.partition("/")
    if kind == "dataset":
        return {"datasets": [value]}
    if kind == "tag":
        return {"tags": [value]}
    if kind == "source":
        return {"sources": [value]}
    if kind == "query":
        # A saved query, by its slug; the images API resolves it (?query=<slug>).
        return {"query": value}
    raise ValueError(f"unknown set kind in {key!r}; expected one of {SET_KINDS}")


# --- labels: what a classifier version trains on ------------------------------


@dataclass
class Examples:
    """What a classifier version trains on, as Dataroom pinned it on the labels
    observation: the datasets per side, the one dataset naming the images held
    out of training, the backbone, and the observation's data version."""

    pos: list[str]
    neg: list[str]
    val: str
    backbone: str
    version: str = ""

    def train_params(self, datasets: list[str]) -> dict[str, Any]:
        """Filter for one side's TRAINING images: on that side, minus the
        held-out ones. Excluding by exact slug/version is what keeps this
        classifier's held-out set from touching anyone else's."""
        params: dict[str, Any] = {"datasets": datasets}
        if self.val:
            params["datasets__ne"] = [self.val]
        return params

    def val_params(self, datasets: list[str]) -> dict[str, Any]:
        """Filter for one side's HELD-OUT images: on that side, and in the
        held-out set. Which side a held-out image is on is not recorded twice
        — it comes from the side dataset it is still a member of."""
        return {"datasets": datasets, "datasets__all": [self.val]}


def read_labels(instance: dg.DagsterInstance, labels_key: dg.AssetKey, classifier: str) -> Examples:
    """The latest labels observation Dataroom reported for a classifier version.

    An observation, not a materialization: Dagster reads an external asset's
    data version from observations, and that data version is what makes the
    head stale when the datasets change.
    """
    record = instance.get_latest_data_version_record(labels_key, is_source=True, partition_key=classifier)
    if record is None:
        raise ValueError(
            f"no labels observation for {classifier!r}: Dataroom reports a version's labelled sets on "
            f"{labels_key.to_user_string()} before launching a run for it"
        )
    observation = record.event_log_entry.dagster_event.event_specific_data.asset_observation
    metadata = {key: value.value for key, value in observation.metadata.items()}
    pos = [d for d in metadata.get("pos_datasets") or [] if d]
    neg = [d for d in metadata.get("neg_datasets") or [] if d]
    if not pos or not neg:
        raise ValueError(f"classifier {classifier!r} has no labelled datasets on one side")
    return Examples(
        pos=pos,
        neg=neg,
        val=metadata.get("val_dataset") or "",
        backbone=metadata.get("embedding_space") or DEFAULT_BACKBONE,
        version=observation.tags.get(DATA_VERSION_TAG, ""),
    )


# --- partitions ---------------------------------------------------------------


@dataclass(frozen=True)
class EnvPartitions:
    classifiers: dg.DynamicPartitionsDefinition
    sets: dg.DynamicPartitionsDefinition
    targets: dg.MultiPartitionsDefinition  # classifier x set
    features: dg.MultiPartitionsDefinition  # set x backbone


def env_partitions(env: str) -> EnvPartitions:
    """A classifier version, a set, and the two pairs the assets are keyed by.

    Features depend on the set and the backbone, which is what
    ``image_embeddings`` is keyed by. The scores depend on the classifier and
    the set. There is no third key joining all three: Dagster caps a
    multi-partition at two dimensions, and a mapping from (classifier, set) to
    (set, backbone) would have to look up the classifier's backbone, which a
    partition mapping cannot do -- they are static functions of the key. So
    ``target_embeddings`` covers an apply target keyed the way the scores are,
    which is what gives the scores a same-key edge to the features they were
    computed from, and ``image_embeddings`` covers a set on its own.
    """
    classifiers = dg.DynamicPartitionsDefinition(name=f"dataroom_{env}_classifiers")
    sets = dg.DynamicPartitionsDefinition(name=f"dataroom_{env}_sets")
    backbones = dg.StaticPartitionsDefinition([backbone.value for backbone in DinoV2Backbones])
    return EnvPartitions(
        classifiers=classifiers,
        sets=sets,
        targets=dg.MultiPartitionsDefinition({"classifier": classifiers, "set": sets}),
        features=dg.MultiPartitionsDefinition({"set": sets, "backbone": backbones}),
    )


def run_partition(context: dg.AssetExecutionContext, partitions: dg.PartitionsDefinition) -> dict[str, str]:
    """The run's partition, per dimension, registered.

    Read from the run tag rather than ``context.partition_key``: Dataroom
    launches with keys it may not have registered yet, and Dagster only
    parses a two-dimensional key into its dimensions once both parts exist.
    Registering here makes the key exist for everything that follows; adding
    a key twice is a no-op. Single-dimension keys come back under ``"key"``.
    """
    raw = context.run.tags.get(PARTITION_TAG) or str(context.partition_key)
    if not isinstance(partitions, dg.MultiPartitionsDefinition):
        context.instance.add_dynamic_partitions(partitions.name, [raw])
        return {"key": raw}
    dimensions = sorted(partitions.partitions_defs, key=lambda dimension: dimension.name)
    values = raw.split("|")
    if len(values) != len(dimensions):
        names = "|".join(dimension.name for dimension in dimensions)
        raise ValueError(f"partition {raw!r} should be {len(dimensions)} values joined by '|' ({names})")
    keys = {dimension.name: value for dimension, value in zip(dimensions, values, strict=True)}
    for dimension in dimensions:
        if isinstance(dimension.partitions_def, dg.DynamicPartitionsDefinition):
            context.instance.add_dynamic_partitions(dimension.partitions_def.name, [keys[dimension.name]])
    return keys


# --- compute ------------------------------------------------------------------


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def embed_missing(
    client: DataRoomClientSync, params: dict[str, Any], backbone: str, image_size: int, log: Log
) -> int:
    """Embed the images matching ``params`` that have no features of this
    type (backbone, size) yet, and store them for each.

    The tokens are computed exactly as training computes them — same decoder,
    same resize, same ``embed_tokens`` — so a head trained on pixels scores
    stored tokens it has effectively seen before.
    """
    spec = DinoV2Backbones(backbone)
    device = _device()
    embedder = spec.backbone.to(device)
    latent = latent_type(backbone, image_size)
    docs = client.images.iter(
        fields=["id", "image_direct_url"], limit=None, page_size=PAGE_SIZE, lacks_latents=[latent], **params
    )

    embedded = 0
    # One batch uploads while the next one downloads and embeds.
    with ThreadPoolExecutor(max_workers=1) as uploads:
        pending = None
        for batch in _batched(docs, EMBED_BATCH_SIZE):
            images = download_many([doc["image_direct_url"] for doc in batch])
            pixels = torch.stack([prepare_image(decode_bytes(data), image_size) for data in images])
            tokens = embed_tokens(embedder, pixels, device).cpu().numpy()
            if pending:
                pending.result()
                log.info(f"embedded and stored {embedded} token sequences...")
            pending = uploads.submit(push_latents, client, latent, {doc["id"]: t for doc, t in zip(batch, tokens, strict=True)})
            embedded += len(batch)
        if pending:
            pending.result()
            log.info(f"embedded and stored {embedded} token sequences...")
    return embedded


def _batched(items: Iterable[dict], size: int) -> Iterator[list[dict]]:
    """Chunk an iterable into lists of at most `size` (itertools.batched needs 3.12)."""
    it = iter(items)
    while chunk := list(islice(it, size)):
        yield chunk


def _iter_latents(
    client: DataRoomClientSync, params: dict[str, Any], backbone: str, image_size: int
) -> Iterator[tuple[str, str]]:
    """Stream (image_id, latent URL) for every image matching a filter that
    has features of this type. Reads only — ``target_embeddings`` is what puts
    them there."""
    latent = latent_type(backbone, image_size)
    docs = client.images.iter(
        fields=["id", "latents"],
        return_latents=[latent],
        has_latents=[latent],
        limit=None,
        page_size=PAGE_SIZE,
        **params,
    )
    for doc in docs:
        for entry in doc.get("latents") or []:
            if entry["latent_type"] == latent:
                yield doc["id"], entry["file_direct_url"]


def _example_samples(
    client: DataRoomClientSync, params: dict[str, Any], label: int, cache_dir: Path, what: str
) -> list[tuple[Path, int]]:
    """The images matching a filter, on local disk, paired with ``label``.

    Training reads pixels rather than stored features: the flip augmentation
    that keeps a few hundred curated examples from overfitting only exists in
    image space, and a token sequence cannot be flipped.
    """
    docs = list(client.images.iter(fields=["id", "image_direct_url"], limit=None, page_size=PAGE_SIZE, **params))
    if not docs:
        raise ValueError(f"no usable {what} matching {params}")
    paths = [cache_dir / doc["id"] for doc in docs]
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as pool:
        list(pool.map(download_to, [doc["image_direct_url"] for doc in docs], paths))
    return [(path, label) for path in paths]


def _embed_target(
    context: dg.AssetExecutionContext,
    dataroom: DataroomResource,
    params: dict[str, Any],
    backbone: str,
    image_size: int,
    missing: int,
) -> int:
    """Embed what a set is missing, wherever CLASSIFIER_COMPUTE runs the backbone."""
    if not missing:
        return 0
    payload = {"params": params, "backbone": backbone, "image_size": image_size}
    return int(_compute().run_step("embed", payload, dataroom, context.run_id, context.log)["embedded"])


class DataroomTrainConfig(dg.Config):
    """Head architecture and training magnitudes; defaults match ``Config`` and
    ``TrainArgs``, which are the source of truth.

    The classifier is the run's partition key. ``training_id`` is the Dataroom
    record the outcome is reported onto; a run launched by hand from the UI
    has none and reports nothing.
    """

    training_id: str = ""
    # architecture -> heads.Config
    dim: int = 64
    n_blocks: int = 0
    n_heads: int = 2
    n_queries: int = 4
    dropout: float = 0.1
    image_size: int = int(os.environ.get("CLASSIFIER_IMAGE_SIZE", DEFAULT_IMAGE_SIZE))
    # training -> train_utils.TrainArgs
    batch_size: int = 32
    lr: float = 1e-4
    weight_decay: float = 1e-2
    label_smoothing: float = 0.05
    iterations: int = int(os.environ.get("CLASSIFIER_TRAIN_ITERATIONS", 800))
    val_every: int = 100
    seed: int = 0

    def head_config(self) -> Config:
        """The head's architecture. ``image_size`` rides along as the size the
        head was trained at; apply may choose another."""
        return Config(**{f: getattr(self, f) for f in Config.__dataclass_fields__})

    def train_args(self) -> TrainArgs:
        return TrainArgs(**{f: getattr(self, f) for f in TrainArgs.__dataclass_fields__})


class DataroomApplyConfig(dg.Config):
    """What ``target_embeddings`` and ``classified_images`` need beyond their
    partition key (classifier x set): which model to score with, and which
    Dataroom record to report onto. What to score is the key itself."""

    model_id: str
    # The Dataroom apply-run record progress is reported onto; empty = a manual run.
    apply_run_id: str = ""
    # Need not be the size the model trained at.
    image_size: int = int(os.environ.get("CLASSIFIER_IMAGE_SIZE", DEFAULT_IMAGE_SIZE))


class DataroomEmbedConfig(dg.Config):
    """What ``image_embeddings`` needs beyond its partition key (set x
    backbone). Feature extraction needs no classifier and no model, so this is
    only the size to resize to, which is part of the feature type."""

    image_size: int = int(os.environ.get("CLASSIFIER_IMAGE_SIZE", DEFAULT_IMAGE_SIZE))


def _check_model_matches(model_id: str, backbone: str, env: str) -> dict:
    """Refuse a model the current code and classifier can no longer honour.

    Checked before embedding rather than at scoring time: each of these costs
    one record read here, or a whole target embedded the wrong way there.
    The size is deliberately not checked: features at another size are a
    different feature type with their own latent, and applying a head to
    them is allowed.
    """
    record = store.get_record(model_id, env)
    if "config" not in record.get("params", {}):
        raise ValueError(
            f"model {model_id} predates the query head: its record has no params.config, "
            f"so there is no architecture to rebuild. Retrain the classifier."
        )
    if record.get("backbone") != backbone:
        # Same-width backbones (vitb14 vs vitb14_reg) would be accepted silently.
        raise ValueError(
            f"model {model_id} was trained on backbone {record.get('backbone')!r} but the "
            f"classifier now says {backbone!r}; scoring would feed the head foreign tokens"
        )
    return record


def _report_training_failure(client: DataRoomClientSync, slug_version: str, training_id: str, exc: Exception) -> None:
    if training_id:
        client.classifiers.report_training(slug_version, training_id, status="failed", error=str(exc)[:2000])


def _report_apply_failure(client: DataRoomClientSync, slug_version: str, apply_run_id: str, exc: Exception) -> None:
    if apply_run_id:
        client.classifiers.report_run(slug_version, apply_run_id, status="failed", error=str(exc)[:2000])


def _score_examples(
    client: DataRoomClientSync,
    slug_version: str,
    head: QueryHead,
    backbone: torch.nn.Module,
    datasets: list[BinaryDataset],
    device: torch.device,
    log: Log,
) -> int:
    """Score the examples training just loaded and store the scores on their
    image docs, so the annotation view shows what the new model thinks of
    every example. Held-out scores are the ones to trust; the rest the model
    trained on.

    Runs the live backbone over the pixels still cached in the datasets — a
    few hundred images, seconds — and writes no features.
    """
    scores: dict[str, float] = {}
    for dataset in datasets:
        dataset.train = False  # score the image, not a random flip of it
        batch_scores, _ = evaluate(head, backbone, DataLoader(dataset, batch_size=32), device)
        scores.update({path.name: round(float(s), 6) for (path, _), s in zip(dataset.samples, batch_scores, strict=True)})
    client.classifiers.add_scores(slug_version, scores)
    log.info(f"scored {len(scores)} example images with the new model")
    return len(scores)


def train_classifier(
    client: DataRoomClientSync,
    env: str,
    slug_version: str,
    examples: Examples,
    config: DataroomTrainConfig,
    log: Log,
) -> dict[str, Any]:
    """Train a head from the classifier's examples, save it to the model store,
    mark the training record "trained" and score the examples with it.
    Returns the asset's metadata.

    Run by whichever compute backend CLASSIFIER_COMPUTE names. It does not
    report failures to Dataroom: the asset does.
    """
    if not examples.val:
        raise ValueError("classifier has no validation dataset; AP cannot be measured without one")
    spec = DinoV2Backbones(examples.backbone)
    head_config, args = config.head_config(), config.train_args()
    backbone = spec.backbone
    device = _device()

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        train_samples = _example_samples(
            client, examples.train_params(examples.pos), 1, cache, "positives"
        ) + _example_samples(client, examples.train_params(examples.neg), 0, cache, "negatives")
        val_samples = _example_samples(
            client, examples.val_params(examples.pos), 1, cache, "held-out positives"
        ) + _example_samples(client, examples.val_params(examples.neg), 0, cache, "held-out negatives")
        log.info(f"train {len(train_samples)} examples, validate on {len(val_samples)} ({device})")

        train_dataset = BinaryDataset(train_samples, config.image_size, train=True, patch_size=spec.patch_size)
        val_dataset = BinaryDataset(val_samples, config.image_size, train=False, patch_size=spec.patch_size)
        head = QueryHead(backbone.dim, head_config)
        # A loader worker hands batches over through /dev/shm, which a run pod
        # has 64 MB of (Kubernetes' default) -- one batch of 32 images at 518px
        # is 26 MB, and the worker prefetches. On CPU the backbone dwarfs the
        # loader anyway, so the worker only buys a crash there; a GPU node has
        # the shared memory and the speed to want it.
        workers = 1 if device.type == "cuda" else 0
        result = train_head(
            head, backbone, train_dataset, val_dataset, args, device=device, num_workers=workers, log=log.info
        )

    record = store.save_model(
        backbone=examples.backbone,
        dim=backbone.dim,
        # Apply rebuilds the head as QueryHead(record["dim"], Config(**params["config"])).
        params={"config": asdict(head_config), "train": asdict(args)},
        metrics=result.metrics,
        state_dict=result.state_dict,
        env=env,
    )
    if config.training_id:
        client.classifiers.report_training(
            slug_version,
            config.training_id,
            status="trained",
            model_id=record["id"],
            metrics=result.metrics,
            code_version=TRAIN_CODE_VERSION,
            labels_version=examples.version,
        )
    # Scoring runs after the report so it cannot fail the training.
    try:
        scored = _score_examples(client, slug_version, head, backbone, [train_dataset, val_dataset], device, log)
    except Exception as exc:
        log.warning(f"scoring the examples failed: {exc}")
        scored = 0
    return {
        "model_id": record["id"],
        "backbone": examples.backbone,
        "n_train": len(train_samples),
        "n_val": len(val_samples),
        "best_iteration": result.best_iteration,
        "val_dataset": examples.val,
        "examples_scored": scored,
        **{k: v for k, v in result.metrics.items() if v is not None},
    }


# --- the graph, once per Dataroom deployment ---------------------------------


def build_env(env: str) -> tuple[list[dg.AssetsDefinition | dg.AssetSpec], list[dg.JobDefinition]]:
    """The classifier assets and jobs of one Dataroom deployment.

    Everything is keyed by ``env``: asset keys, group, partition definitions,
    job names and the ``dataroom_<env>`` resource, so a run's environment is in
    its asset key and nowhere in its config.
    """
    if env not in ENVS:
        raise ValueError(f"env={env!r} — expected one of {list(ENVS)}")
    prefix = ["dataroom", env]
    group = f"dataroom_{env}"
    resource_key = f"dataroom_{env}"
    partitions = env_partitions(env)
    labels_key = dg.AssetKey([*prefix, "labels"])

    labels = dg.AssetSpec(
        key=labels_key,
        partitions_def=partitions.classifiers,
        group_name=group,
        description=(
            "A classifier version's labelled sets, as Dataroom reports them: the positive, negative and"
            " held-out datasets and the backbone. Observed, never materialized here; the data version is"
            " the sorted dataset slug_versions"
        ),
        metadata={
            "reported_by": "Dataroom, POST /report_asset_observation/ on every change to a version's labelled sets",
            "metadata_keys": dg.MetadataValue.json(["pos_datasets", "neg_datasets", "val_dataset", "embedding_space"]),
        },
    )

    def resource(context: dg.AssetExecutionContext) -> DataroomResource:
        return getattr(context.resources, resource_key)

    @dg.asset(
        key=[*prefix, "trained_classifier"],
        partitions_def=partitions.classifiers,
        group_name=group,
        deps=[labels],
        code_version=TRAIN_CODE_VERSION,
        required_resource_keys={resource_key},
        description=(
            "The query head trained from a classifier version's labelled images, saved to the model store;"
            " outcome reported onto the Dataroom training record. Data version = model id"
        ),
    )
    def trained_classifier(context: dg.AssetExecutionContext, config: DataroomTrainConfig) -> dg.MaterializeResult:
        slug_version = run_partition(context, partitions.classifiers)["key"]
        dataroom = resource(context)
        client = dataroom.client()
        try:
            examples = read_labels(context.instance, labels_key, slug_version)
            payload = {"slug_version": slug_version, "examples": asdict(examples), "config": config.model_dump()}
            metadata = _compute().run_step("train", payload, dataroom, context.run_id, context.log)
        except Exception as exc:
            _report_training_failure(client, slug_version, config.training_id, exc)
            raise
        return dg.MaterializeResult(
            data_version=dg.DataVersion(metadata["model_id"]),
            metadata={
                **metadata,
                "code_version": TRAIN_CODE_VERSION,
                "labels_version": examples.version,
                "pos_datasets": dg.MetadataValue.json(examples.pos),
                "neg_datasets": dg.MetadataValue.json(examples.neg),
            },
        )

    @dg.asset(
        key=[*prefix, "target_embeddings"],
        partitions_def=partitions.targets,
        group_name=group,
        code_version=EMBED_CODE_VERSION,
        required_resource_keys={resource_key},
        description=(
            "Stored features covering a set, in the classifier's backbone: computes and stores the"
            " (backbone, image_size) latent for the set's images that lack it"
        ),
    )
    def target_embeddings(context: dg.AssetExecutionContext, config: DataroomApplyConfig) -> dg.MaterializeResult:
        """Also sizes the target and flips the Dataroom run to running before
        the embedding starts: ``processed``/``total`` needs its denominator
        before the slow part. Every check that can fail the run cheaply (set,
        backbone, size, model) happens here, before any image is embedded."""
        keys = run_partition(context, partitions.targets)
        slug_version, set_name = keys["classifier"], keys["set"]
        dataroom = resource(context)
        client = dataroom.client()
        try:
            examples = read_labels(context.instance, labels_key, slug_version)
            backbone = examples.backbone
            params = set_filter(set_name)
            DinoV2Backbones(backbone).num_tokens(config.image_size)  # validates both
            _check_model_matches(config.model_id, backbone, env)
            latent = latent_type(backbone, config.image_size)
            total = client.images.count(**params)
            missing = client.images.count(**params, lacks_latents=[latent])
            if config.apply_run_id:
                client.classifiers.report_run(slug_version, config.apply_run_id, status="running", total=total)
            context.log.info(f"{set_name}: {total} images, {missing} without {backbone!r} features at {config.image_size}px")
            embedded = _embed_target(context, dataroom, params, backbone, config.image_size, missing)
        except Exception as exc:
            _report_apply_failure(client, slug_version, config.apply_run_id, exc)
            raise
        context.log.info(f"embedded {embedded} images")
        return dg.MaterializeResult(
            # Coverage, not content: the same set embedded again with nothing
            # new to add is the same data.
            data_version=dg.DataVersion(f"{latent}:{total}"),
            metadata={
                "set": set_name,
                "latent": latent,
                "target_images": total,
                "already_embedded": total - missing,
                "embedded_now": embedded,
                "backbone": backbone,
                "image_size": config.image_size,
            },
        )

    @dg.asset(
        key=[*prefix, "classified_images"],
        partitions_def=partitions.targets,
        group_name=group,
        deps=[
            target_embeddings,
            dg.AssetDep(trained_classifier, partition_mapping=dg.MultiToSingleDimensionPartitionMapping("classifier")),
        ],
        required_resource_keys={resource_key},
        description="A classifier version's scores on a set's image docs, from the stored features",
    )
    def classified_images(context: dg.AssetExecutionContext, config: DataroomApplyConfig) -> dg.MaterializeResult:
        """Score the set from its stored token latents and write the scores back.

        Two batch sizes: latents are fetched and scores pushed ``SCORE_BATCH`` at
        a time (the scores endpoint's cap), and the head runs over ``HEAD_BATCH``
        sequences at once, since a full score batch of tokens does not fit
        comfortably in memory.
        """
        keys = run_partition(context, partitions.targets)
        slug_version, set_name = keys["classifier"], keys["set"]
        client = resource(context).client()
        try:
            examples = read_labels(context.instance, labels_key, slug_version)
            backbone = examples.backbone
            params = set_filter(set_name)
            total = client.images.count(**params)
            record = _check_model_matches(config.model_id, backbone, env)
            head_config = Config(**record["params"]["config"])
            spec = DinoV2Backbones(backbone)
            # QueryHead accepts any token count, so a wrong-shaped latent would score silently.
            expected_tokens = spec.num_tokens(config.image_size)
            if head_config.image_size != config.image_size:
                context.log.info(
                    f"model {config.model_id} was trained at {head_config.image_size}px; scoring at "
                    f"{config.image_size}px, {expected_tokens} tokens per image"
                )
            device = _device()
            head = QueryHead(record["dim"], head_config)
            head.load_state_dict(store.load_head(record["id"], env))
            head.to(device).eval()
            processed = 0
            ids: list[str] = []
            urls: list[str] = []

            def score(sequences: list[np.ndarray]) -> np.ndarray:
                shapes = {sequence.shape for sequence in sequences}
                if shapes != {(expected_tokens, record["dim"])}:
                    raise ValueError(
                        f"{backbone!r} features at {config.image_size}px should be [{expected_tokens}, {record['dim']}] "
                        f"but the stored ones are {sorted(shapes)}; the latent "
                        f"{latent_type(backbone, config.image_size)!r} holds something else"
                    )
                scores = []
                with torch.no_grad():
                    for start in range(0, len(sequences), HEAD_BATCH):
                        batch = torch.from_numpy(np.stack(sequences[start : start + HEAD_BATCH])).to(device).float()
                        scores.append(torch.sigmoid(head(batch).squeeze(-1)).cpu())
                return torch.cat(scores).numpy()

            def flush() -> None:
                nonlocal processed
                if not ids:
                    return
                scores = score(fetch_latents(urls))
                client.classifiers.add_scores(
                    slug_version,
                    {image_id: round(float(s), 6) for image_id, s in zip(ids, scores, strict=True)},
                    run_id=config.apply_run_id or None,
                )
                processed += len(ids)
                context.log.info(f"processed {processed}/{total}")
                ids.clear()
                urls.clear()

            for image_id, url in _iter_latents(client, params, backbone, config.image_size):
                ids.append(image_id)
                urls.append(url)
                if len(ids) >= SCORE_BATCH:
                    flush()
            flush()

            if config.apply_run_id:
                client.classifiers.report_run(slug_version, config.apply_run_id, status="completed", processed=processed)
        except Exception as exc:
            _report_apply_failure(client, slug_version, config.apply_run_id, exc)
            raise
        return dg.MaterializeResult(
            data_version=dg.DataVersion(f"{config.model_id}:{latent_type(backbone, config.image_size)}:{processed}"),
            metadata={
                "set": set_name,
                "scored": processed,
                "total": total,
                "model_id": config.model_id,
                "image_size": config.image_size,
                "trained_at": head_config.image_size,
            },
        )

    @dg.asset(
        key=[*prefix, "image_embeddings"],
        partitions_def=partitions.features,
        group_name=group,
        code_version=EMBED_CODE_VERSION,
        required_resource_keys={resource_key},
        description=(
            "The features of one set in one backbone, computed without a classifier."
            " Same latent as target_embeddings, so whichever runs first does the work"
        ),
    )
    def image_embeddings(context: dg.AssetExecutionContext, config: DataroomEmbedConfig) -> dg.MaterializeResult:
        """Run the backbone over a set and store what it produces.

        Feature extraction on its own: no classifier, no model, no scores. It
        is how a set gets its features before any classifier exists, how a
        backbone nobody has trained on yet gets tried, and how the cost of a
        big set is paid once, deliberately, rather than inside the first apply
        run that happens to need it.
        """
        keys = run_partition(context, partitions.features)
        set_name, backbone = keys["set"], keys["backbone"]
        dataroom = resource(context)
        client = dataroom.client()
        params = set_filter(set_name)
        DinoV2Backbones(backbone).num_tokens(config.image_size)  # validates both
        latent = latent_type(backbone, config.image_size)
        total = client.images.count(**params)
        missing = client.images.count(**params, lacks_latents=[latent])
        context.log.info(
            f"{set_name}: {total} images, {missing} without {backbone!r} features at {config.image_size}px"
        )
        embedded = _embed_target(context, dataroom, params, backbone, config.image_size, missing)
        return dg.MaterializeResult(
            data_version=dg.DataVersion(f"{latent}:{total}"),
            metadata={
                "set": set_name,
                "latent": latent,
                "target_images": total,
                "already_embedded": total - missing,
                "embedded_now": embedded,
                "backbone": backbone,
                "image_size": config.image_size,
            },
        )

    jobs = [
        dg.define_asset_job(
            f"dataroom_{env}_train_classifier",
            selection=dg.AssetSelection.assets(trained_classifier),
            description=f"Train one classifier version of the {env} Dataroom; partition = slug/version",
        ),
        dg.define_asset_job(
            f"dataroom_{env}_embed_set",
            selection=dg.AssetSelection.assets(image_embeddings),
            description=f"Extract features for one set of the {env} Dataroom in one backbone; partition = backbone|set",
        ),
        dg.define_asset_job(
            f"dataroom_{env}_apply_classifier",
            selection=dg.AssetSelection.assets(target_embeddings, classified_images),
            description=f"Score one set of the {env} Dataroom with one classifier version; partition = classifier|set",
        ),
    ]
    return [labels, trained_classifier, target_embeddings, classified_images, image_embeddings], jobs
