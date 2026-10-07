"""Training-side helpers for the query head: what a labelled example is, and
how it becomes a batch the backbone can consume.

The head trains on pixels rather than on the tokens stored in Dataroom,
because the augmentation that keeps a few hundred curated examples from
overfitting lives in image space and cannot be applied to a cached embedding.
That is the whole reason this module exists.

Decoding is the expensive step (~8-25 ms per image, against ~1-2 ms to
resize), so ``BinaryDataset`` decodes and resizes every example once into one
contiguous uint8 tensor and each epoch then costs a slice and a flip. The
cache stays uint8: it is a quarter the memory of float32, a quarter the
host-to-device transfer, and the cast is bandwidth-bound work the GPU does for
free. ``embed_tokens`` is where that cast happens, after ``.to(device)``, and
it is also the one place the backbone is run, so apply's stored features and
training's live ones come out of the same code.

Nothing here talks to Dataroom. Which images are examples, which side they are
on and which are held out is decided upstream (``Examples`` in
``classifier.assets``); by the time a path reaches ``BinaryDataset`` it is a
local file with a label.
"""

import io
import os
import random
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision.io import decode_image
from torchvision.transforms import v2 as transforms

from dataroom.classifier.ml.metrics import PRIMARY, compute_metrics
from dataroom.classifier.ml.optimizer import AdamWScheduleFree

# What DINOv2 was trained with.
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# Not a TrainArgs field: 0 would clip every gradient to zero, not disable clipping.
GRAD_CLIP = 1.0


@dataclass
class TrainArgs:
    """The recipe. Every field is a magnitude, not a mode — there is one way to
    train a head here, and these are its numbers.

    The train/val split is deliberately absent: it comes from the classifier's
    ``val_dataset`` in Dataroom, and a second split mechanism would silently
    compete with it.
    """

    batch_size: int = 32
    lr: float = 1e-4
    weight_decay: float = 1e-2
    # The v6 value, kept on purpose; dino-bench's R2 drops it for calibration, not AP.
    label_smoothing: float = 0.05
    # Steps, not epochs. dino-bench: at lr 1e-4, 800 matches 1500 and 3000 overfits.
    iterations: int = 800
    val_every: int = 100
    seed: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.label_smoothing < 0.5:
            raise ValueError(f"label_smoothing must be in [0, 0.5), got {self.label_smoothing}")
        if self.val_every < 1 or self.iterations < 1:
            raise ValueError("iterations and val_every must be >= 1")


@dataclass
class TrainResult:
    """What ``train_head`` produced: the best head by validation AP, the
    metrics it was chosen on, and every validation along the way."""

    state_dict: dict
    metrics: dict
    best_iteration: int
    history: list[dict]


def samples_from_paths(positives: list[Path], negatives: list[Path]) -> list[tuple[Path, int]]:
    """Positives first (1), then negatives (0) — the same row order
    the trainer sees them in."""
    return [(path, 1) for path in positives] + [(path, 0) for path in negatives]


def balanced_sampler(labels: Sequence[int], seed: int = 0) -> WeightedRandomSampler:
    """Draw both sides equally often, regardless of how lopsided the examples are.

    Negatives are cheap to collect and positives are curated, so the two sides
    routinely differ by an order of magnitude; left alone, a batch is nearly
    all negative and the head learns the prior instead of the class. Weighting
    each example by the inverse frequency of its own side makes the two sides
    equally likely per draw.

    An epoch stays ``len(labels)`` draws, taken WITH replacement — that is what
    lets the smaller side repeat rather than the larger side go unseen.

    This is the only imbalance correction here, deliberately. The other option
    is ``pos_weight`` on the loss; the dino-bench
    sweep found it ties on AP (delta 0.000) while tripling calibration error
    (ECE 0.235 against 0.068). Scores from this head are written to Dataroom
    and thresholded by people, so calibration is not something to trade away.
    Never apply both: that corrects the imbalance twice.
    """
    counts = Counter(labels)
    if len(counts) < 2:
        raise ValueError(f"need both sides to balance, got only {sorted(counts)}")
    weights = torch.tensor([1.0 / counts[label] for label in labels], dtype=torch.double)
    return WeightedRandomSampler(
        weights, num_samples=len(labels), replacement=True, generator=torch.Generator().manual_seed(seed)
    )


def to_rgb(image: torch.Tensor) -> torch.Tensor:
    """A decoded image as 3-channel uint8, compositing any alpha onto white.

    Cutouts arrive with a transparent background; left as-is the alpha channel
    is dropped and whatever sits in the masked-out RGB becomes signal. White is
    what the rest of the product composites onto.
    """
    channels = image.shape[0]
    if channels == 4:
        rgb, alpha = image[:3].float(), image[3:4].float() / 255.0
        return (alpha * rgb + (1 - alpha) * 255.0).to(torch.uint8)
    if channels == 2:
        gray, alpha = image[0:1].float(), image[1:2].float() / 255.0
        return (alpha * gray + (1 - alpha) * 255.0).to(torch.uint8).expand(3, -1, -1)
    if channels == 1:
        return image.expand(3, -1, -1)
    return image


def decode_bytes(data: bytes) -> torch.Tensor:
    """Encoded image bytes -> uint8 CHW, alpha already composited.

    The one decoder for every image the backbone sees, whether it came from
    a URL (the embed step) or from disk (training): two decoders would give
    two sets of pixels for the same image, and tokens stored by one path
    would not match what the head was trained on by the other. Falls back
    to PIL for the formats torchvision cannot decode.
    """
    try:
        # bytearray: torch warns on an immutable buffer.
        return to_rgb(decode_image(torch.frombuffer(bytearray(data), dtype=torch.uint8)))
    except Exception:
        pil_image = Image.open(io.BytesIO(data)).convert("RGBA")
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        background.paste(pil_image, mask=pil_image.split()[3])
        return torch.from_numpy(np.array(background)).permute(2, 0, 1)


def _decode(path: Path) -> torch.Tensor:
    return decode_bytes(path.read_bytes())


@cache
def get_normalize_transform():
    transform = transforms.Compose(
        [
            transforms.ToDtype(torch.float32, scale=True),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    return transform


def normalize_batch(images: torch.Tensor) -> torch.Tensor:
    """uint8 [B,3,H,W] -> normalized float32."""
    transform = get_normalize_transform()
    return transform(images)


@cache
def _resize(image_size: int):
    return transforms.Resize((image_size, image_size), antialias=True)


def prepare_image(image: torch.Tensor, image_size: int) -> torch.Tensor:
    """One decoded image as uint8 [3, S, S]: alpha composited onto white, then
    square-resized.

    The single definition of what the backbone is shown. Both callers go
    through it — caching example images for training, and embedding straight
    from a URL — because tokens produced by two different preprocessing paths
    would not be comparable.
    """
    return _resize(image_size)(to_rgb(image))


def _build_cache(samples: list[tuple[Path, int]], image_size: int, workers: int) -> torch.Tensor:
    """Decode and resize every sample once into one contiguous uint8 tensor.

    Threaded because decoding releases the GIL and dominates the cost; each
    task owns one row, so the writes do not overlap.
    """
    cache = torch.empty((len(samples), 3, image_size, image_size), dtype=torch.uint8)

    def fill(index: int) -> None:
        cache[index] = prepare_image(_decode(samples[index][0]), image_size)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fill, range(len(samples))))
    return cache


class BinaryDataset(Dataset):
    """Labelled example images, decoded once and held as uint8.

    ``samples`` is (path, label) with label 1 for positive — build it with
    ``samples_from_paths`` so the ordering convention stays in one place.
    ``train`` only decides whether the horizontal flip is applied, so the same
    sample list can back both a training and an evaluation dataset.

    Items come out uint8: pass batches through ``embed_tokens``, which
    normalizes on the device. Because nothing is left to decode, an item is
    a slice and a flip; one persistent loader worker is enough to keep a
    batch ready ahead of the GPU (see ``train_head``).

    Rows are positives then negatives, so iterating in order yields one-sided
    batches. Give the DataLoader ``balanced_sampler(dataset.labels)`` (or at
    minimum ``shuffle=True``) rather than reading it straight through.
    """

    def __init__(
        self,
        samples: list[tuple[Path, int]],
        image_size: int,
        train: bool = True,
        patch_size: int = 14,
        cache_workers: int = min(8, os.cpu_count() or 1),
    ):
        if not samples:
            raise ValueError("no samples")
        if image_size % patch_size:
            raise ValueError(
                f"image_size must be a multiple of the backbone's patch size {patch_size}, got {image_size}"
            )
        self.samples = samples
        self.image_size = image_size
        self.train = train
        self.images = _build_cache(samples, image_size, cache_workers)

    @property
    def labels(self) -> list[int]:
        """Every label in row order — what a balanced sampler weights from."""
        return [label for _, label in self.samples]

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        image = self.images[idx]
        if self.train and torch.rand(()) < 0.5:
            image = torch.flip(image, dims=[2])
        return image, self.samples[idx][1]


@torch.no_grad()
def embed_tokens(backbone: nn.Module, images: torch.Tensor, device: torch.device) -> torch.Tensor:
    """uint8 images [B, 3, S, S] -> the backbone's tokens [B, T, D] as fp32.

    The single way the frozen backbone is run: training, validation and the
    embed step all come through here, so the tokens a head trains on and the
    tokens stored for scoring are computed identically. bf16 autocast on CUDA
    is part of that recipe (the bench found it harmless); the cast back to
    fp32 is for the head, whose Linear layers do not take half.
    """
    images = normalize_batch(images.to(device, non_blocking=True))
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=images.is_cuda):
        return backbone(images).float()


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@torch.no_grad()
def evaluate(
    head: nn.Module, backbone: nn.Module, loader: DataLoader, device: torch.device
) -> tuple[np.ndarray, np.ndarray]:
    """Sigmoid scores and labels for every item in ``loader``."""
    head.eval()
    scores, labels = [], []
    for images, batch_labels in loader:
        tokens = embed_tokens(backbone, images, device)
        logits = head(tokens).squeeze(-1)
        scores.append(torch.sigmoid(logits.float()).cpu())
        labels.append(batch_labels)
    return torch.cat(scores).numpy(), torch.cat(labels).numpy()


def train_head(
    head: nn.Module,
    backbone: nn.Module,
    train_dataset: BinaryDataset,
    val_dataset: BinaryDataset,
    args: TrainArgs,
    device: torch.device | None = None,
    num_workers: int = 1,
    log: Callable[[str], None] = print,
) -> TrainResult:
    """Train ``head`` on the tokens ``backbone`` produces, keeping the weights
    that scored best on validation AP.

    The loop is built to keep the GPU busy: one persistent loader worker
    collates and pins batch N+1 while the device runs batch N (an item is
    only a slice of the decoded cache, so one worker is plenty), and nothing
    in the step reads a value back from the device — the running loss stays
    there and is read once per validation.
    """
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _seed_everything(args.seed)
    head = head.to(device)
    backbone = backbone.to(device).eval()

    if len(set(val_dataset.labels)) < 2:
        raise ValueError("the validation set needs both sides")

    pin = device.type == "cuda"
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        sampler=balanced_sampler(train_dataset.labels, args.seed),
        num_workers=num_workers,
        # The loader is re-entered every pass; without this, one fork per pass.
        persistent_workers=num_workers > 0,
        prefetch_factor=2 if num_workers > 0 else None,
        pin_memory=pin,
    )
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0, pin_memory=pin)

    criterion = nn.BCEWithLogitsLoss()
    optimizer = AdamWScheduleFree(head.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    best_score, best_iteration, best_state, best_metrics = -torch.inf, 0, {}, {}
    history: list[dict] = []

    def infinite(loader):
        while True:
            yield from loader

    batches = infinite(train_loader)
    head.train()
    optimizer.train()
    # On the device: a per-step .item() would sync the GPU every step.
    running_loss, seen = torch.zeros((), device=device), 0

    for iteration in range(1, args.iterations + 1):
        images, batch_labels = next(batches)
        targets = batch_labels.float().to(device)
        targets = targets * (1 - 2 * args.label_smoothing) + args.label_smoothing

        optimizer.zero_grad(set_to_none=True)
        tokens = embed_tokens(backbone, images, device)
        loss = criterion(head(tokens).squeeze(-1), targets)
        loss.backward()
        nn.utils.clip_grad_norm_(head.parameters(), GRAD_CLIP)
        optimizer.step()
        running_loss += loss.detach() * images.size(0)
        seen += images.size(0)

        if iteration % args.val_every and iteration != args.iterations:
            continue

        optimizer.eval()
        metrics = compute_metrics(*evaluate(head, backbone, val_loader, device))
        metrics["iteration"] = iteration
        metrics["train_loss"] = (running_loss / seen).item()
        running_loss, seen = torch.zeros((), device=device), 0
        history.append(metrics)
        log(
            f"iteration {iteration}: train loss {metrics['train_loss']:.4f} "
            f"val AP {metrics[PRIMARY]} AUROC {metrics['auroc']} logloss {metrics['logloss']:.4f}"
        )
        if metrics[PRIMARY] >= best_score:
            best_score, best_iteration, best_metrics = metrics[PRIMARY], iteration, metrics
            # While the optimizer is in eval mode: these are the weights AP was measured on.
            best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}
        head.train()
        optimizer.train()

    head.load_state_dict(best_state)
    log(f"best val {PRIMARY} {best_score:.4f} at iteration {best_iteration}")
    return TrainResult(
        state_dict=best_state,
        metrics={f"val_{k}": v for k, v in best_metrics.items()},
        best_iteration=best_iteration,
        history=history,
    )
