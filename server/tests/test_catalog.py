"""Tests for `station/catalog.py` and `station/models.default.toml`."""
from __future__ import annotations

import copy
import tomllib
import pytest

from station import catalog


def _raw_default() -> dict:
    with open(catalog.DEFAULT_TOML, "rb") as f:
        return tomllib.load(f)


def test_default_toml_validates():
    loaded = catalog.load(catalog.DEFAULT_TOML)
    assert set(loaded) == set(catalog.SLOTS)
    for pack, slots in catalog.SLOTS.items():
        assert set(loaded[pack]) == set(slots)


def test_unknown_pack_rejected():
    raw = _raw_default()
    raw["unknown_pack"] = {}
    with pytest.raises(ValueError, match="未知模型包"):
        catalog.validate(raw)


def test_missing_slot_rejected():
    raw = copy.deepcopy(_raw_default())
    del raw["image"]["vae"]
    with pytest.raises(ValueError, match=r"\[image\.vae\]"):
        catalog.validate(raw)


def test_invalid_target_path_traversal_rejected():
    raw = copy.deepcopy(_raw_default())
    raw["image"]["vae"]["target"] = "../evil.safetensors"
    with pytest.raises(ValueError, match="纯文件名"):
        catalog.validate(raw)


def test_file_names_returns_targets():
    names = catalog.file_names("image_turbo", catalog.DEFAULT_TOML)
    assert names["diffusion"] == "z_image_turbo_bf16_nsfw_v2.safetensors"
    assert names["encoder"] == "qwen_3_4b.safetensors"
    assert names["vae"] == "zimage-ae.safetensors"
