"""The frozen DINOv2 backbones: which ones exist, and what each one's tokens look like."""

from enum import Enum
from functools import cached_property

import torch
import torch.nn as nn


class DinoV2Backbones(str, Enum):
    VITS14 = "vits14"
    VITB14 = "vitb14"
    VITL14 = "vitl14"
    VITG14 = "vitg14"
    VITS14_REG = "vits14_reg"
    VITB14_REG = "vitb14_reg"
    VITL14_REG = "vitl14_reg"
    VITG14_REG = "vitg14_reg"

    @property
    def patch_size(self) -> int:
        """Read off the name: ``vitb14_reg`` -> 14."""
        return int(self.value.removesuffix("_reg")[-2:])

    @property
    def num_register_tokens(self) -> int:
        """The ``_reg`` variants prepend 4 register tokens; the others none.

        Same reasoning as ``patch_size``: derived from the name so a token
        count can be predicted without loading half a gigabyte of weights.
        """
        return 4 if self.value.endswith("_reg") else 0

    def num_tokens(self, image_size: int) -> int:
        """How long a sequence this backbone emits for a square image of
        ``image_size``: one token per patch, plus CLS and the registers.

        The size is not the backbone's to choose — it is part of the feature
        type, set per job — but what it implies for the sequence is.
        """
        if image_size % self.patch_size:
            raise ValueError(
                f"image_size must be a multiple of {self.value}'s patch size {self.patch_size}, got {image_size}"
            )
        return (image_size // self.patch_size) ** 2 + 1 + self.num_register_tokens

    @cached_property
    def backbone(self) -> "DinoV2Backbone":
        return DinoV2Backbone(dino_version=self.value)


class DinoV2Backbone(nn.Module):
    """A frozen DINOv2, exposing its final token sequence.

    Never trained: ``train_head`` runs it under ``no_grad`` and checkpoints only
    the head that reads from it.
    """

    def __init__(self, dino_version: str):
        super().__init__()
        expected = DinoV2Backbones(dino_version)
        self.backbone = torch.hub.load("facebookresearch/dinov2", f"dinov2_{dino_version}")
        self.backbone.eval()
        if self.patch_size != expected.patch_size:
            raise ValueError(
                f"{dino_version} loaded with patch size {self.patch_size}, but its name says {expected.patch_size}"
            )

    @property
    def dim(self) -> int:
        return self.backbone.embed_dim

    @property
    def patch_size(self) -> int:
        return int(getattr(self.backbone, "patch_size", 14))

    @property
    def num_register_tokens(self) -> int:
        """CLS aside, how many non-patch tokens lead the sequence."""
        return int(getattr(self.backbone, "num_register_tokens", 0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.embed(x)

    @torch.no_grad()
    def embed(self, x: torch.Tensor) -> torch.Tensor:
        """Normalized images [B, 3, S, S] -> final tokens [B, 1 + registers + patches, dim]."""
        x = self.backbone.prepare_tokens_with_masks(x)
        for block in self.backbone.blocks:
            x = block(x)
        return self.backbone.norm(x)
