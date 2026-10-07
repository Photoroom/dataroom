"""DinoV2Backbones: what a name says about the tokens, without loading weights."""

import pytest

from dataroom.classifier.ml.embedders.dino import DinoV2Backbones


def test_token_count_follows_image_size_patch_and_registers():
    assert DinoV2Backbones.VITB14_REG.num_tokens(518) == 37 * 37 + 1 + 4
    assert DinoV2Backbones.VITS14.num_tokens(28) == 4 + 1
    assert DinoV2Backbones.VITB14_REG.num_tokens(1036) == 74 * 74 + 1 + 4


def test_size_must_be_a_multiple_of_the_patch():
    with pytest.raises(ValueError, match="multiple of"):
        DinoV2Backbones.VITB14_REG.num_tokens(520)
