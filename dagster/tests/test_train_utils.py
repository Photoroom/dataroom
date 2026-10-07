"""BinaryDataset: what comes out of a labelled example image."""

import inspect
import json

import numpy as np
import pytest
import torch
from PIL import Image
from torch import nn

from dataroom.classifier.ml.metrics import compute_metrics
from dataroom.classifier.ml.optimizer import AdamWScheduleFree
from dataroom.classifier.ml.train_utils import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    BinaryDataset,
    TrainArgs,
    _decode,
    balanced_sampler,
    decode_bytes,
    embed_tokens,
    evaluate,
    normalize_batch,
    samples_from_paths,
    to_rgb,
    train_head,
)

SIZE = 28  # a multiple of 14, small enough to keep the test fast


def _write(path, mode, color, size=(40, 30)):
    Image.new(mode, size, color).save(path)
    return path


@pytest.fixture
def cutout(tmp_path):
    """A PNG whose left half is opaque red and right half fully transparent
    over red — what a cutout looks like."""
    array = np.zeros((30, 40, 4), dtype=np.uint8)
    array[:, :, 0] = 255  # red everywhere, including under the transparency
    array[:, :20, 3] = 255  # left half opaque, right half alpha=0
    path = tmp_path / "cutout.png"
    Image.fromarray(array, mode="RGBA").save(path)
    return path


def test_transparent_regions_composite_onto_white_not_black(cutout):
    image = _decode(cutout)
    assert image.shape[0] == 3
    assert image[:, :, :20].float().mean(dim=(1, 2)).tolist() == pytest.approx([255, 0, 0], abs=1)
    assert image[:, :, 20:].float().mean(dim=(1, 2)).tolist() == pytest.approx([255, 255, 255], abs=1)


def test_decode_bytes_matches_decode_from_path(cutout):
    """The embed step decodes from memory and training decodes from disk;
    both must see the same pixels or stored tokens and training tokens
    would come from different images."""
    assert torch.equal(decode_bytes(cutout.read_bytes()), _decode(cutout))


def test_grayscale_expands_to_three_channels():
    assert to_rgb(torch.full((1, 4, 4), 128, dtype=torch.uint8)).shape == (3, 4, 4)


def test_rgb_passes_through_unchanged():
    rgb = torch.randint(0, 255, (3, 4, 4), dtype=torch.uint8)
    assert torch.equal(to_rgb(rgb), rgb)


def test_items_are_uint8_at_the_configured_size(tmp_path):
    path = _write(tmp_path / "white.png", "RGB", (255, 255, 255))
    dataset = BinaryDataset(samples_from_paths([path], []), image_size=SIZE, train=False)
    image, label = dataset[0]

    assert image.dtype == torch.uint8
    assert image.shape == (3, SIZE, SIZE)
    assert label == 1
    assert dataset.images.shape == (1, 3, SIZE, SIZE)


def test_normalize_batch_matches_imagenet_stats(tmp_path):
    path = _write(tmp_path / "white.png", "RGB", (255, 255, 255))
    dataset = BinaryDataset(samples_from_paths([path], []), image_size=SIZE, train=False)
    batch = torch.stack([dataset[0][0]])

    out = normalize_batch(batch)
    assert out.dtype == torch.float32
    expected = [(1.0 - m) / s for m, s in zip(IMAGENET_MEAN, IMAGENET_STD)]
    assert out.mean(dim=(0, 2, 3)).tolist() == pytest.approx(expected, abs=1e-3)


def test_positives_come_first_and_labels_match(tmp_path):
    pos = [_write(tmp_path / f"p{i}.png", "RGB", (255, 0, 0)) for i in range(2)]
    neg = [_write(tmp_path / f"n{i}.png", "RGB", (0, 0, 255)) for i in range(3)]
    dataset = BinaryDataset(samples_from_paths(pos, neg), image_size=SIZE, train=False)

    assert len(dataset) == 5
    assert dataset.labels == [1, 1, 0, 0, 0]
    assert [dataset[i][1] for i in range(5)] == [1, 1, 0, 0, 0]


def test_cache_rows_stay_aligned_with_samples(tmp_path):
    """Threaded cache building must not scramble row order."""
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
    paths = [_write(tmp_path / f"c{i}.png", "RGB", c) for i, c in enumerate(colors)]
    dataset = BinaryDataset(samples_from_paths(paths, []), image_size=SIZE, train=False, cache_workers=4)

    for i, color in enumerate(colors):
        assert dataset[i][0].float().mean(dim=(1, 2)).tolist() == pytest.approx(list(color), abs=2)


def test_eval_is_deterministic_and_train_flips(tmp_path):
    # An asymmetric image, so a horizontal flip is detectable.
    array = np.zeros((30, 40, 3), dtype=np.uint8)
    array[:, :20] = 255
    path = tmp_path / "half.png"
    Image.fromarray(array).save(path)
    samples = samples_from_paths([path], [])

    evaluation = BinaryDataset(samples, image_size=SIZE, train=False)
    assert {evaluation[0][0].numpy().tobytes() for _ in range(20)} == {evaluation[0][0].numpy().tobytes()}

    torch.manual_seed(0)
    training = BinaryDataset(samples, image_size=SIZE, train=True)
    views = {training[0][0].numpy().tobytes() for _ in range(40)}
    assert len(views) == 2, "train mode should produce both the flipped and unflipped view"


def test_rejects_empty_samples_and_bad_image_size(tmp_path):
    path = _write(tmp_path / "x.png", "RGB", (0, 0, 0))
    with pytest.raises(ValueError, match="no samples"):
        BinaryDataset([], image_size=SIZE)
    with pytest.raises(ValueError, match="multiple of the backbone.s patch size"):
        BinaryDataset(samples_from_paths([path], []), image_size=30, patch_size=14)


def test_balanced_sampler_evens_out_a_lopsided_split():
    labels = [1] * 10 + [0] * 190
    drawn = [labels[i] for i in balanced_sampler(labels, seed=0)]

    assert len(drawn) == len(labels), "an epoch should stay the same length"
    positive_share = sum(drawn) / len(drawn)
    assert positive_share == pytest.approx(0.5, abs=0.08)


def test_balanced_sampler_repeats_the_small_side_rather_than_dropping_the_large_one():
    labels = [1] * 3 + [0] * 60
    indices = list(balanced_sampler(labels, seed=0))
    positives = [i for i in indices if labels[i] == 1]

    assert len(positives) > len(set(positives))
    assert set(positives) <= {0, 1, 2}


def test_balanced_sampler_is_reproducible_and_varies_without_a_seed():
    labels = [1] * 5 + [0] * 20
    assert list(balanced_sampler(labels, seed=7)) == list(balanced_sampler(labels, seed=7))
    assert list(balanced_sampler(labels, seed=7)) != list(balanced_sampler(labels, seed=8))


def test_balanced_sampler_needs_both_sides():
    with pytest.raises(ValueError, match="both sides"):
        balanced_sampler([1, 1, 1])


def test_balanced_sampler_pairs_with_the_dataset_labels(tmp_path):
    pos = [_write(tmp_path / "p0.png", "RGB", (255, 0, 0))]
    neg = [_write(tmp_path / f"n{i}.png", "RGB", (0, 0, 255)) for i in range(9)]
    dataset = BinaryDataset(samples_from_paths(pos, neg), image_size=SIZE, train=False)

    drawn = [dataset[i][1] for i in balanced_sampler(dataset.labels, seed=0)]
    assert sum(drawn) / len(drawn) == pytest.approx(0.5, abs=0.25)


# --- train_head ---------------------------------------------------------------


class StubBackbone(nn.Module):
    """images [B,3,S,S] -> tokens [B,T,D], standing in for a frozen DINOv2."""

    TOKENS, DIM = 4, 8

    def __init__(self, size=SIZE):
        super().__init__()
        self.proj = nn.Linear(3 * size * size, self.TOKENS * self.DIM)

    def forward(self, images):
        return self.proj(images.flatten(1)).view(-1, self.TOKENS, self.DIM)


class StubHead(nn.Module):
    """tokens [B,T,D] -> logits [B,1], the un-squeezed shape QueryHead returns."""

    def __init__(self):
        super().__init__()
        self.net = nn.Linear(StubBackbone.TOKENS * StubBackbone.DIM, 1)

    def forward(self, tokens):
        return self.net(tokens.flatten(1))


def _separable(tmp_path, n_pos=4, n_neg=4):
    """Positives white, negatives black — learnable in a handful of epochs."""
    pos = [_write(tmp_path / f"p{i}.png", "RGB", (255, 255, 255)) for i in range(n_pos)]
    neg = [_write(tmp_path / f"n{i}.png", "RGB", (0, 0, 0)) for i in range(n_neg)]
    return samples_from_paths(pos, neg)


CPU = torch.device("cpu")


@pytest.fixture(autouse=True)
def _deterministic():
    """Stub weights are randomly initialised; without a fixed seed the suite
    passes or fails depending on what ran before it."""
    torch.manual_seed(0)


def _args(**kw):
    kw.setdefault("lr", 1e-2)  # 8 steps total; the 1e-4 default needs far more
    return TrainArgs(batch_size=4, iterations=4, val_every=1, **kw)


@pytest.fixture
def datasets(tmp_path):
    samples = _separable(tmp_path)
    train = BinaryDataset(samples, image_size=SIZE, train=True)
    val = BinaryDataset(samples, image_size=SIZE, train=False)
    return train, val


def test_train_head_learns_a_separable_split(datasets):
    train, val = datasets
    result = train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)

    assert result.metrics["val_ap"] == pytest.approx(1.0, abs=1e-6)
    assert result.best_iteration in {h["iteration"] for h in result.history}


def test_returns_the_best_epoch_not_the_last(datasets):
    train, val = datasets
    result = train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)

    scored = [h for h in result.history if h["ap"] is not None]
    assert result.metrics["val_ap"] == max(h["ap"] for h in scored)
    assert len(result.history) == 4, "val_every=1 over 4 iterations should validate 4 times"


def test_metrics_are_val_prefixed_and_json_safe(datasets):
    train, val = datasets
    result = train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)

    assert all(k.startswith("val_") for k in result.metrics)
    json.dumps(result.metrics, allow_nan=False)


def test_single_class_validation_is_rejected(tmp_path):
    """AP is the entire selection criterion and is undefined on one class, so
    this is caught before 800 epochs rather than after."""
    train = BinaryDataset(_separable(tmp_path), image_size=SIZE, train=True)
    only_pos = [_write(tmp_path / f"v{i}.png", "RGB", (255, 255, 255)) for i in range(3)]
    val = BinaryDataset(samples_from_paths(only_pos, []), image_size=SIZE, train=False)

    with pytest.raises(ValueError, match="validation set needs both sides"):
        train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)


def test_compute_metrics_returns_null_not_nan_on_one_class():
    """train_head rejects this, but the metric function still has to be safe:
    NaN is not valid JSON and these dicts are reported to Dataroom."""
    out = compute_metrics([0.9, 0.8, 0.7], [1, 1, 1])
    assert out["ap"] is None and out["auroc"] is None
    assert json.loads(json.dumps(out, allow_nan=False))["ap"] is None


def test_backbone_is_neither_trained_nor_checkpointed(datasets):
    train, val = datasets
    head, backbone = StubHead(), StubBackbone()
    before = backbone.proj.weight.detach().clone()

    result = train_head(head, backbone, train, val, _args(), device=CPU, log=lambda _: None)

    assert torch.equal(backbone.proj.weight, before)
    assert backbone.proj.weight.grad is None
    assert set(result.state_dict) == set(head.state_dict())


def test_checkpoint_is_a_copy_not_a_live_view(datasets):
    """The best epoch must not track later training."""
    train, val = datasets
    head = StubHead()
    result = train_head(head, StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)
    saved = {k: v.clone() for k, v in result.state_dict.items()}

    with torch.no_grad():
        head.net.weight.add_(100.0)

    assert torch.equal(result.state_dict["net.weight"], saved["net.weight"])


def test_schedulefree_is_toggled_around_evaluation(datasets, monkeypatch):
    """train_head must put the optimizer in eval mode before scoring: with
    schedule-free the training weights are not the ones to measure."""
    train, val = datasets
    modes = []
    real_eval = AdamWScheduleFree.eval
    real_train = AdamWScheduleFree.train
    monkeypatch.setattr(AdamWScheduleFree, "eval", lambda self: (modes.append("eval"), real_eval(self))[1])
    monkeypatch.setattr(AdamWScheduleFree, "train", lambda self: (modes.append("train"), real_train(self))[1])

    train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)

    assert modes.count("eval") == 4, f"expected one eval per validation, got {modes}"


def test_train_head_needs_both_sides(tmp_path):
    only_pos = [_write(tmp_path / f"p{i}.png", "RGB", (255, 255, 255)) for i in range(3)]
    dataset = BinaryDataset(samples_from_paths(only_pos, []), image_size=SIZE, train=False)
    with pytest.raises(ValueError, match="both sides"):
        train_head(StubHead(), StubBackbone(), dataset, dataset, _args(), device=CPU, log=lambda _: None)


def test_evaluate_returns_scores_in_range(datasets):
    train, val = datasets
    scores, labels = evaluate(
        StubHead(), StubBackbone(), torch.utils.data.DataLoader(val, batch_size=4), CPU
    )
    assert scores.shape == labels.shape == (len(val),)
    assert ((scores >= 0) & (scores <= 1)).all()


def test_train_args_rejects_bad_values():
    with pytest.raises(ValueError, match="label_smoothing"):
        _args(label_smoothing=0.6)


# --- vendored optimizer --------------------------------------------------------


def test_schedulefree_needs_train_mode_before_stepping():
    """The train/eval contract is the easiest thing to get wrong when wiring
    this in; stepping in eval mode must fail loudly rather than silently
    updating the averaged weights."""
    model = nn.Linear(4, 1)
    opt = AdamWScheduleFree(model.parameters(), lr=1e-3)
    model(torch.randn(2, 4)).sum().backward()
    with pytest.raises(Exception, match="train mode"):
        opt.step()


def test_schedulefree_eval_swaps_in_different_weights():
    model = nn.Linear(4, 1)
    opt = AdamWScheduleFree(model.parameters(), lr=1e-1)
    opt.train()
    for _ in range(3):
        opt.zero_grad(set_to_none=True)
        model(torch.randn(8, 4)).sum().backward()
        opt.step()
    train_weights = model.weight.detach().clone()
    opt.eval()
    assert not torch.equal(model.weight, train_weights)


def test_schedulefree_actually_optimizes():
    torch.manual_seed(0)
    model = nn.Linear(4, 1)
    x, y = torch.randn(32, 4), torch.randn(32, 1)
    opt = AdamWScheduleFree(model.parameters(), lr=1e-2)
    opt.train()
    first = last = None
    for step in range(50):
        opt.zero_grad(set_to_none=True)
        loss = nn.functional.mse_loss(model(x), y)
        loss.backward()
        opt.step()
        first = loss.item() if step == 0 else first
        last = loss.item()
    assert last < first


def test_dataset_rejects_a_size_the_backbone_cannot_patch(tmp_path):
    path = _write(tmp_path / "x.png", "RGB", (0, 0, 0))
    with pytest.raises(ValueError, match="multiple of the backbone's patch size"):
        BinaryDataset(samples_from_paths([path], []), image_size=30, patch_size=14)
    BinaryDataset(samples_from_paths([path], []), image_size=32, patch_size=16)


def test_checkpoint_is_taken_on_the_weights_that_were_scored(datasets, monkeypatch):
    """The saved weights must be the ones AP was measured on.

    Schedule-free holds the averaged weights behind optimizer.eval() and swaps
    the training iterate back in on train(). Capture the state dict on the
    wrong side of that swap and you save a network that was never scored —
    silently, since it still trains and still scores plausibly. Comparing
    metrics cannot catch it (on an easy split both iterates score 1.0), so this
    compares the weights themselves.
    """
    train, val = datasets
    head, backbone = StubHead(), StubBackbone()
    scored: list[dict] = []
    real_eval = AdamWScheduleFree.eval

    def spy(self):
        real_eval(self)
        scored.append({k: v.detach().clone() for k, v in head.state_dict().items()})

    monkeypatch.setattr(AdamWScheduleFree, "eval", spy)
    result = train_head(head, backbone, train, val, _args(), device=CPU, log=lambda _: None)

    assert scored, "never validated"
    assert any(
        all(torch.equal(snapshot[k], result.state_dict[k]) for k in snapshot) for snapshot in scored
    ), "the returned checkpoint matches no set of weights that was ever evaluated"


# --- embed_tokens --------------------------------------------------------------


class RecordingBackbone(nn.Module):
    """Keeps what it was shown, so a test can check the preprocessing."""

    def __init__(self):
        super().__init__()
        self.seen = None

    def forward(self, images):
        self.seen = images
        return images.flatten(1)[:, :8].unsqueeze(1).to(torch.bfloat16)


def test_embed_tokens_normalizes_and_returns_float32(tmp_path):
    path = _write(tmp_path / "white.png", "RGB", (255, 255, 255))
    dataset = BinaryDataset(samples_from_paths([path], []), image_size=SIZE, train=False)
    images = torch.stack([dataset[0][0]])
    backbone = RecordingBackbone()

    tokens = embed_tokens(backbone, images, CPU)

    assert torch.equal(backbone.seen, normalize_batch(images))
    assert tokens.dtype == torch.float32
    assert tokens.shape == (1, 1, 8)


def test_train_loader_keeps_one_worker_alive_across_passes(datasets, monkeypatch):
    """One worker prepares batch N+1 while the GPU runs batch N. It has to be
    persistent: the loop re-enters the loader every pass over the data, and a
    100-example set is 4 batches a pass, so a non-persistent worker would be
    forked hundreds of times per run."""
    import dataroom.classifier.ml.train_utils as module

    train, val = datasets
    loaders = []
    real = module.DataLoader

    def spy(dataset, **kwargs):
        loaders.append((dataset, kwargs))
        return real(dataset, **kwargs)

    monkeypatch.setattr(module, "DataLoader", spy)
    train_head(StubHead(), StubBackbone(), train, val, _args(), device=CPU, log=lambda _: None)

    assert inspect.signature(train_head).parameters["num_workers"].default == 1
    (_, train_kwargs), (_, val_kwargs) = loaders
    assert train_kwargs["num_workers"] == 1
    assert train_kwargs["persistent_workers"] is True
    assert train_kwargs["prefetch_factor"] == 2
    assert val_kwargs["num_workers"] == 0


def test_train_loop_syncs_with_the_device_only_at_validation(datasets, monkeypatch):
    """``loss.item()`` every step makes the CPU wait for the GPU before it can
    even launch the next batch. The running loss stays on the device and is
    read once per validation, so the sync count follows val_every, not
    iterations."""
    import traceback

    train, val = datasets
    syncs = []
    real_item = torch.Tensor.item

    def spy(self):
        # The DataLoader's own item() on its CPU seed tensor is not a sync.
        if traceback.extract_stack()[-2].filename.endswith("train_utils.py"):
            syncs.append(1)
        return real_item(self)

    monkeypatch.setattr(torch.Tensor, "item", spy)

    train_head(
        StubHead(), StubBackbone(), train, val,
        TrainArgs(batch_size=4, iterations=8, val_every=4, lr=1e-2), device=CPU, log=lambda _: None, num_workers=0,
    )

    assert len(syncs) == 2, f"expected one sync per validation, got {len(syncs)}"
