"""The classifier graph of one Dataroom deployment (dev), end to end against
the fake Dataroom: labels observation -> trained head -> target features ->
scores, and what makes which partition stale."""

import io

import dagster as dg
import numpy as np
import pytest
from conftest import IMAGE_SIZE, LATENT, SPACE
from dagster import DagsterInstance, RunConfig
from dagster._core.definitions.data_version import CachingStaleStatusResolver
from dagster._core.loader import LoadingContextForTest

from dataroom import defs
from dataroom.classifier import assets
from dataroom.classifier.assets import (
    DATA_VERSION_TAG,
    ENVS,
    TRAIN_CODE_VERSION,
    DataroomApplyConfig,
    DataroomEmbedConfig,
    DataroomTrainConfig,
    env_partitions,
    set_filter,
    set_key,
)

ENV = "dev"
CLASSIFIER = "cats/1"
POS, NEG, VAL = "cats-positives/1", "cats-negatives/1", "cats-validation/1"
ALL_CATS = "tag/cats"  # every example carries the tag: the set covering all 60
PARTS = env_partitions(ENV)
LABELS = dg.AssetKey(["dataroom", ENV, "labels"])
HEAD = dg.AssetKey(["dataroom", ENV, "trained_classifier"])
SCORES = dg.AssetKey(["dataroom", ENV, "classified_images"])


def op(name: str) -> str:
    """An asset's op name: its key joined by __, which is what run config addresses."""
    return f"dataroom__{ENV}__{name}"


def job(name: str):
    return defs.resolve_job_def(f"dataroom_{ENV}_{name}")


def labels_version(pos, neg, val, backbone) -> str:
    """Dataroom's data version for a labels observation: backbone and sorted slug_versions."""
    return f"{backbone}:{','.join(sorted([*pos, *neg, *([val] if val else [])]))}"


def report_labels(instance, fake, classifier=CLASSIFIER, pos=(POS,), neg=(NEG,), backbone=SPACE) -> str:
    """What Dataroom POSTs to /report_asset_observation/ whenever a version's
    labelled sets change, and before every launch. Returns the data version."""
    val = fake.val_dataset
    version = labels_version(pos, neg, val, backbone)
    instance.add_dynamic_partitions(PARTS.classifiers.name, [classifier])
    instance.report_runless_asset_event(
        dg.AssetObservation(
            asset_key=LABELS,
            partition=classifier,
            tags={DATA_VERSION_TAG: version},
            metadata={
                "pos_datasets": dg.MetadataValue.json(list(pos)),
                "neg_datasets": dg.MetadataValue.json(list(neg)),
                "val_dataset": val,
                "embedding_space": backbone,
            },
        )
    )
    return version


@pytest.fixture
def instance(fake):
    """A Dagster instance where Dataroom has already reported cats/1's labels."""
    with DagsterInstance.ephemeral() as instance:
        report_labels(instance, fake)
        yield instance


def run_train(fake, instance=None, training_id="t-1", classifier=CLASSIFIER, **execute):
    if instance is None:
        instance = DagsterInstance.ephemeral()
        report_labels(instance, fake, classifier=classifier)
    config = DataroomTrainConfig(training_id=training_id, image_size=IMAGE_SIZE, iterations=40, val_every=10, lr=1e-2)
    return job("train_classifier").execute_in_process(
        run_config=RunConfig(ops={op("trained_classifier"): config}),
        resources={f"dataroom_{ENV}": fake},
        raise_on_error=False,
        instance=instance,
        **({"partition_key": classifier} | execute),
    )


def target(set_name: str, classifier: str = CLASSIFIER) -> dg.MultiPartitionKey:
    return dg.MultiPartitionKey({"classifier": classifier, "set": set_name})


def run_apply(fake, instance, model_id, run_id="r-1", set_name=ALL_CATS, image_size=IMAGE_SIZE, **execute):
    instance.add_dynamic_partitions(PARTS.sets.name, [set_name])
    config = DataroomApplyConfig(model_id=model_id, apply_run_id=run_id, image_size=image_size)
    return job("apply_classifier").execute_in_process(
        run_config=RunConfig(ops={op("target_embeddings"): config, op("classified_images"): config}),
        resources={f"dataroom_{ENV}": fake},
        raise_on_error=False,
        instance=instance,
        **({"partition_key": target(set_name)} | execute),
    )


def stale_status(instance, key, partition) -> str:
    resolver = CachingStaleStatusResolver(instance, defs.resolve_asset_graph(), LoadingContextForTest(instance))
    return resolver.get_status(key, str(partition)).value


# --- training -----------------------------------------------------------------


def test_train_reports_a_trained_model_with_its_versions_and_stores_no_features(fake, instance):
    result = run_train(fake, instance)
    assert result.success
    (report,) = fake.training_reports
    assert report["status"] == "trained"
    assert report["model_id"]
    assert report["metrics"]["val_ap"] > 0.9
    # The versions Dataroom compares against: which code trained, which labels it saw.
    assert report["code_version"] == TRAIN_CODE_VERSION
    assert report["labels_version"] == labels_version([POS], [NEG], VAL, SPACE)
    assert fake.embeds_written == 0
    assert not any(doc["latents"] for doc in fake.docs.values())

    (materialization,) = result.asset_materializations_for_node(op("trained_classifier"))
    assert materialization.partition == CLASSIFIER
    assert materialization.tags[DATA_VERSION_TAG] == report["model_id"]
    assert materialization.metadata["labels_version"].value == report["labels_version"]
    assert materialization.metadata["pos_datasets"].value == [POS]


def test_train_failure_is_reported(fake, instance):
    fake.docs = {}
    result = run_train(fake, instance, training_id="t-2")
    assert not result.success
    (report,) = fake.training_reports
    assert report["status"] == "failed"
    assert report["error"]


def test_training_without_a_labels_observation_fails_and_says_so(fake):
    """The labels observation is the pinned record of what the version trains
    on; without it there is nothing to train on, and the error names it."""
    with DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(PARTS.classifiers.name, [CLASSIFIER])
        result = run_train(fake, instance, training_id="t-nolabels")
    assert not result.success
    assert "labels observation" in fake.training_reports[-1]["error"]
    assert fake.training_reports[-1]["status"] == "failed"


def test_training_without_a_validation_dataset_is_refused(fake, instance):
    """AP is the whole selection criterion and cannot be measured on nothing."""
    fake.val_dataset = ""
    report_labels(instance, fake)
    result = run_train(fake, instance, training_id="t-noval")
    assert not result.success
    assert "validation dataset" in fake.training_reports[-1]["error"]


def test_extra_datasets_on_the_labels_are_trained_on(fake, instance):
    """The labels observation lists every dataset of a side, borrowed ones
    included; training does not go back to Dataroom to ask."""
    for i in range(10):
        fake.docs[f"pos-more-{i}"] = {"datasets": ["more-cats/2"], "tags": ["cats"], "latents": {}}
    report_labels(instance, fake, pos=(POS, "more-cats/2"))

    result = run_train(fake, instance, training_id="t-extra")
    assert result.success
    (materialization,) = result.asset_materializations_for_node(op("trained_classifier"))
    assert materialization.metadata["n_train"].value == 48 + 10
    assert materialization.metadata["pos_datasets"].value == [POS, "more-cats/2"]


def test_a_run_by_hand_without_a_training_record_reports_nothing(fake, instance):
    result = run_train(fake, instance, training_id="")
    assert result.success
    assert fake.training_reports == []
    assert len(fake.scores) == 60  # the examples still get scored


def test_held_out_examples_are_measured_on_but_never_trained_on(fake, instance):
    result = run_train(fake, instance, training_id="t-val")
    (materialization,) = result.asset_materializations_for_node(op("trained_classifier"))
    assert result.success
    # 30 per side, 6 held out per side: 48 train, 12 validate.
    assert materialization.metadata["n_train"].value == 48
    assert materialization.metadata["n_val"].value == 12
    assert materialization.metadata["val_dataset"].value == VAL
    metrics = fake.training_reports[-1]["metrics"]
    assert metrics["val_n"] == 12
    assert metrics["val_n_pos"] == 6


def test_one_sided_holdout_is_refused(fake, instance):
    """A validation set on one side alone says nothing about the other."""
    for i in range(6):
        fake.docs[f"neg-{i}"]["datasets"].remove(VAL)
    result = run_train(fake, instance, training_id="t-onesided")
    assert not result.success
    assert "held-out negatives" in fake.training_reports[-1]["error"]


def test_train_config_defaults_track_the_source_of_truth():
    """DataroomTrainConfig restates every field of Config and TrainArgs, so its
    defaults can drift from theirs without anything failing. Adding a field is
    caught by head_config()/train_args() raising AttributeError; removing one,
    or changing a default, is silent. This is what catches those."""
    from dataroom.classifier.ml.heads import Config
    from dataroom.classifier.ml.train_utils import TrainArgs

    config = DataroomTrainConfig()
    assert config.head_config() == Config()
    assert config.train_args() == TrainArgs()
    restated = set(DataroomTrainConfig.model_fields)
    assert set(TrainArgs.__dataclass_fields__) <= restated
    assert set(Config.__dataclass_fields__) <= restated
    assert DataroomTrainConfig(image_size=1036).head_config().image_size == 1036


def test_training_scores_its_own_examples(fake, instance):
    """The annotation view shows what the current model thinks of every
    example, so training scores the pixels it already has cached rather
    than waiting for someone to launch an apply run over them."""
    assert run_train(fake, instance, training_id="t-scores-examples").success
    assert len(fake.scores) == 60
    assert set(fake.scores) == set(fake.docs)
    assert all(0.0 <= score <= 1.0 for score in fake.scores.values())
    assert fake.embeds_written == 0


def test_training_on_cpu_uses_no_loader_worker(fake, instance, monkeypatch):
    """A run pod has Kubernetes' default 64 MB of /dev/shm, and a DataLoader
    worker hands a 26 MB batch through it, with prefetch: the pod dies with
    "unable to allocate shared memory". On CPU the worker buys nothing, so
    there is none; the GPU path keeps it."""
    from dataroom.classifier import assets

    seen = {}
    real = assets.train_head

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(assets, "train_head", spy)
    assert run_train(fake, instance, training_id="t-workers").success
    assert seen["num_workers"] == 0


def test_a_scoring_failure_does_not_undo_a_good_training(fake, instance, monkeypatch):
    """Scoring runs after the training is reported, so a failure there costs
    the scores and nothing else."""

    def boom(slug_version, scores, run_id=None):
        raise RuntimeError("scores endpoint down")

    monkeypatch.setattr(fake.classifiers, "add_scores", boom)
    assert run_train(fake, instance, training_id="t-scores-fail").success
    assert fake.training_reports[-1]["status"] == "trained"
    assert not fake.scores


# --- apply --------------------------------------------------------------------


def test_apply_embeds_the_target_once_and_scores_from_the_stored_features(fake, instance):
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]

    result = run_apply(fake, instance, model_id)
    assert result.success
    assert fake.embeds_written == 60
    assert all(LATENT in doc["latents"] for doc in fake.docs.values())
    assert len(fake.scores) == 60
    positives = [s for image_id, s in fake.scores.items() if image_id.startswith("pos")]
    negatives = [s for image_id, s in fake.scores.items() if image_id.startswith("neg")]
    assert min(positives) > max(negatives), "the head should rank positives above negatives"
    assert {"status": "running", "total": 60} in fake.run_reports
    assert fake.run_reports[-1] == {"status": "completed", "processed": 60}
    for node in ("target_embeddings", "classified_images"):
        (materialization,) = result.asset_materializations_for_node(op(node))
        assert materialization.partition == str(target(ALL_CATS))
        assert materialization.metadata["set"].value == ALL_CATS

    assert run_apply(fake, instance, model_id, run_id="r-again").success
    assert fake.embeds_written == 60


def test_apply_with_nothing_missing_starts_no_compute(fake, instance, monkeypatch):
    """On Sky an embed job costs minutes of Slurm and setup even with nothing to embed."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    assert run_apply(fake, instance, model_id).success

    monkeypatch.setattr(assets, "_compute", lambda: pytest.fail("embed ran with nothing missing"))
    result = run_apply(fake, instance, model_id, run_id="r-again")
    assert result.success
    (materialization,) = result.asset_materializations_for_node(op("target_embeddings"))
    assert materialization.metadata["embedded_now"].value == 0


def test_embedding_more_than_one_batch_stores_every_image(fake, instance, monkeypatch):
    monkeypatch.setattr(assets, "EMBED_BATCH_SIZE", 7)
    assert run_train(fake, instance).success
    assert run_apply(fake, instance, fake.training_reports[-1]["model_id"]).success
    assert fake.embeds_written == 60
    assert all(LATENT in doc["latents"] for doc in fake.docs.values())


def test_apply_embeds_only_the_missing_part_of_the_target(fake, instance):
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    assert run_apply(fake, instance, model_id).success
    written_after_first_apply = fake.embeds_written

    for i in range(5):  # new, never-embedded images join the target
        fake.docs[f"pos-new-{i}"] = {"datasets": [POS], "tags": ["cats"], "latents": {}}

    result = run_apply(fake, instance, model_id, run_id="r-2")
    assert result.success
    assert fake.embeds_written == written_after_first_apply + 5
    assert len(fake.scores) == 65


def test_apply_to_an_unknown_set_kind_reports_failure(fake, instance):
    result = run_apply(fake, instance, model_id="missing", run_id="r-3", set_name="nonsense/x")
    assert not result.success
    assert fake.run_reports[-1]["status"] == "failed"
    assert "unknown set kind" in fake.run_reports[-1]["error"]


def test_a_query_set_is_the_saved_query_by_slug(fake, instance):
    """A saved query has a slug, which the images API resolves (?query=<slug>)
    — so the key names it outright and nothing about the target travels in the
    run config."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]

    result = run_apply(fake, instance, model_id, run_id="r-q", set_name=set_key("query", "cats-on-sofas"))

    assert result.success
    assert set(fake.queries) == {"cats-on-sofas"}
    assert fake.run_reports[-1] == {"status": "completed", "processed": 60}


def test_apply_refuses_a_model_trained_on_another_backbone(fake, instance):
    """vitb14 and vitb14_reg are both 768-wide, so in_proj would accept the
    wrong tokens without complaint and the scores would be quietly wrong.
    Editing embedding_space after training is a new labels observation."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    for doc in fake.docs.values():  # force the embed step to have work to do
        doc["latents"].clear()
    written_before = fake.embeds_written
    report_labels(instance, fake, backbone="vitl14")

    result = run_apply(fake, instance, model_id, run_id="r-moved")
    assert not result.success
    assert "foreign tokens" in fake.run_reports[-1]["error"]
    assert fake.embeds_written == written_before, "should have failed before embedding"


def test_stored_tokens_are_the_backbone_sequence_at_half_precision(fake, instance):
    """What the latent holds is checked by the fake on write (fp16 .npy,
    [T, D]); this checks the values are the backbone's, so apply can score
    from them without re-running it."""
    assert run_train(fake, instance).success
    assert run_apply(fake, instance, fake.training_reports[-1]["model_id"]).success
    tokens = np.load(io.BytesIO(fake.docs["pos-0"]["latents"][LATENT]))
    # White positives normalize above 2, black negatives below -1.
    assert tokens.dtype == np.float16
    assert float(tokens.mean()) > 2.0
    assert float(np.load(io.BytesIO(fake.docs["neg-0"]["latents"][LATENT])).mean()) < -1.0


def test_apply_at_a_larger_size_computes_its_own_features_and_scores_over_them(fake, instance):
    """image_size is part of the feature type. A head trained at one size
    can be applied at another — a patch then covers a smaller part of the
    image — and the target gets features at the new size, under a latent of
    its own, without touching the ones stored at the training size."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    assert run_apply(fake, instance, model_id).success
    written_at_training_size = fake.embeds_written

    result = run_apply(fake, instance, model_id, run_id="r-2x", image_size=2 * IMAGE_SIZE)

    assert result.success
    larger = f"{SPACE}_{2 * IMAGE_SIZE}_features"
    assert fake.embeds_written == written_at_training_size + 60, "every image needed features at the new size"
    assert all({LATENT, larger} <= set(doc["latents"]) for doc in fake.docs.values())
    assert len(fake.scores) == 60
    positives = [s for image_id, s in fake.scores.items() if image_id.startswith("pos")]
    negatives = [s for image_id, s in fake.scores.items() if image_id.startswith("neg")]
    assert min(positives) > max(negatives)
    (materialization,) = result.asset_materializations_for_node(op("classified_images"))
    assert materialization.metadata["image_size"].value == 2 * IMAGE_SIZE
    assert materialization.metadata["trained_at"].value == IMAGE_SIZE


def test_apply_at_a_size_the_backbone_cannot_patch_fails_before_embedding(fake, instance):
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    written_before = fake.embeds_written

    result = run_apply(fake, instance, model_id, run_id="r-odd", image_size=IMAGE_SIZE + 2)

    assert not result.success
    assert "multiple" in fake.run_reports[-1]["error"]
    assert fake.embeds_written == written_before


def test_rescoring_the_examples_is_one_apply_per_labelled_dataset(fake, instance):
    """There is no 'annotations' pseudo-set: the annotation view re-scores by
    applying to each of the version's own datasets, which are ordinary sets."""
    assert run_train(fake, instance, training_id="t-ann").success
    model_id = fake.training_reports[-1]["model_id"]
    fake.scores.clear()

    assert run_apply(fake, instance, model_id, run_id="r-pos", set_name=set_key("dataset", POS)).success
    assert run_apply(fake, instance, model_id, run_id="r-neg", set_name=set_key("dataset", NEG)).success
    assert set(fake.scores) == set(fake.docs)
    assert fake.run_reports[-1] == {"status": "completed", "processed": 30}


# --- partitions, keys and staleness ------------------------------------------


def test_set_keys_round_trip_to_filters():
    """A key is the whole selection: the asset needs no run config to resolve it."""
    assert set_filter(set_key("dataset", "shop/3")) == {"datasets": ["shop/3"]}
    assert set_filter(set_key("tag", "sofa")) == {"tags": ["sofa"]}
    assert set_filter(set_key("source", "web")) == {"sources": ["web"]}
    assert set_filter(set_key("query", "cats-on-sofas")) == {"query": "cats-on-sofas"}
    with pytest.raises(ValueError, match="unknown set kind"):
        set_key("all", "")
    with pytest.raises(ValueError, match="needs a value"):
        set_key("dataset", "")
    # "|" joins the dimensions of a key, so no name may carry one.
    with pytest.raises(ValueError, match="cannot contain"):
        set_key("tag", "cats|dogs")


def test_a_launch_with_an_unregistered_key_registers_it(fake, instance):
    """Dataroom launches over GraphQL with the key as a run tag, and a tag is
    not validated against the registered keys. The assets register what the
    tag names, so the materialization lands on the right partition."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    fresh = set_key("dataset", "never-seen/7")
    for i in range(3):
        fake.docs[f"pos-fresh-{i}"] = {"datasets": ["never-seen/7"], "tags": [], "latents": {}}
    key = target(fresh)

    result = job("apply_classifier").execute_in_process(
        run_config=RunConfig(
            ops={
                op(n): DataroomApplyConfig(model_id=model_id, image_size=IMAGE_SIZE)
                for n in ("target_embeddings", "classified_images")
            }
        ),
        resources={f"dataroom_{ENV}": fake},
        instance=instance,
        tags={"dagster/partition": str(key)},
    )
    assert result.success
    assert fresh in instance.get_dynamic_partitions(PARTS.sets.name)
    assert str(key) in instance.get_materialized_partitions(SCORES)
    assert fake.run_reports == [], "a run by hand has no Dataroom record to report onto"


def test_changing_the_labels_marks_the_head_stale_and_retraining_marks_the_scores_stale(fake, instance):
    """The chain Dataroom reads back: a new labels observation makes the head
    stale, a retrain makes every set it was applied to stale, and nothing
    here launches anything on its own."""
    assert run_train(fake, instance).success
    model_id = fake.training_reports[-1]["model_id"]
    assert run_apply(fake, instance, model_id).success
    assert stale_status(instance, HEAD, CLASSIFIER) == "FRESH"
    assert stale_status(instance, SCORES, target(ALL_CATS)) == "FRESH"

    # The user borrows another positive dataset: Dataroom reports, nothing runs.
    report_labels(instance, fake, pos=(POS, "more-cats/2"))
    assert stale_status(instance, HEAD, CLASSIFIER) == "STALE"
    assert stale_status(instance, SCORES, target(ALL_CATS)) == "FRESH"

    # Reporting the same labels again changes nothing.
    report_labels(instance, fake, pos=(POS, "more-cats/2"))
    assert stale_status(instance, HEAD, CLASSIFIER) == "STALE"

    for i in range(4):
        fake.docs[f"pos-more-{i}"] = {"datasets": ["more-cats/2"], "tags": ["cats"], "latents": {}}
    assert run_train(fake, instance, training_id="t-retrain").success
    assert fake.training_reports[-1]["model_id"] != model_id
    assert stale_status(instance, HEAD, CLASSIFIER) == "FRESH"
    assert stale_status(instance, SCORES, target(ALL_CATS)) == "STALE"


def test_features_can_be_extracted_for_a_set_without_any_classifier(fake, instance):
    """Feature extraction is its own operation: a set and a backbone, no
    classifier, no model, no scores. It is also how the cost of a big set gets
    paid before the first apply run over it rather than inside it."""
    key = dg.MultiPartitionKey({"set": ALL_CATS, "backbone": SPACE})
    instance.add_dynamic_partitions(PARTS.sets.name, [ALL_CATS])

    result = job("embed_set").execute_in_process(
        run_config=RunConfig(ops={op("image_embeddings"): DataroomEmbedConfig(image_size=IMAGE_SIZE)}),
        resources={f"dataroom_{ENV}": fake},
        instance=instance,
        partition_key=key,
    )

    assert result.success
    assert fake.embeds_written == 60
    assert not fake.scores, "nothing was scored: no classifier was involved"
    (materialization,) = result.asset_materializations_for_node(op("image_embeddings"))
    assert materialization.metadata["latent"].value == LATENT
    assert materialization.metadata["embedded_now"].value == 60

    # Both assets write the same latent, so an apply over the same set finds
    # the features already there and embeds nothing.
    assert run_train(fake, instance).success
    assert run_apply(fake, instance, fake.training_reports[-1]["model_id"]).success
    assert fake.embeds_written == 60


def test_every_deployment_has_its_own_graph_group_and_jobs():
    graph = defs.resolve_asset_graph()
    for env in ENVS:
        for name in ("labels", "trained_classifier", "target_embeddings", "classified_images", "image_embeddings"):
            node = graph.get(dg.AssetKey(["dataroom", env, name]))
            assert node.group_name == f"dataroom_{env}"
        assert not graph.get(dg.AssetKey(["dataroom", env, "labels"])).is_materializable
        for name in ("train_classifier", "apply_classifier", "embed_set"):
            assert defs.resolve_job_def(f"dataroom_{env}_{name}")
    scores = graph.get(dg.AssetKey(["dataroom", "prod", "classified_images"]))
    assert {k.to_user_string() for k in scores.parent_keys} == {
        "dataroom/prod/target_embeddings",
        "dataroom/prod/trained_classifier",
    }
