"""Tests for `station/models.py` downloader logic."""
from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
import pytest

_STATION = Path(__file__).resolve().parent.parent.parent / "station"
if str(_STATION) not in sys.path:
    sys.path.insert(0, str(_STATION))

if "huggingface_hub" not in sys.modules:
    stub = types.ModuleType("huggingface_hub")
    stub.hf_hub_download = lambda **kw: ""  # type: ignore[attr-defined]
    stub.hf_hub_url = lambda repo_id, filename: f"https://hf.test/{repo_id}/{filename}"  # type: ignore[attr-defined]
    sys.modules["huggingface_hub"] = stub

import models  # noqa: E402


def test_load_packs_contains_four_packs():
    packs = models.load_packs()
    assert set(packs) == {"image", "image_turbo", "video", "video_wan22"}


def test_verify_sha256_deletes_corrupted_file(tmp_path: Path):
    f = tmp_path / "weights.safetensors"
    f.write_bytes(b"hello")
    good = hashlib.sha256(b"hello").hexdigest()
    assert models.verify_sha256(f, good) is True
    assert f.exists()

    bad = "0" * 64
    assert models.verify_sha256(f, bad) is False
    assert not f.exists()


def test_ensure_pack_downloads_and_marks_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models, "ROOT", tmp_path)
    monkeypatch.setattr(models, "STATUS", tmp_path / ".status.json")
    monkeypatch.setattr(
        models,
        "PACKS",
        {"image": [("owner/repo", "m.safetensors", "m.safetensors", "diffusion_models", 1.5, None)]},
    )

    def _fake_download(repo: str, filename: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"weights")

    monkeypatch.setattr(models, "download_file", _fake_download)
    state: dict = {"packs": {}}
    models.ensure_pack("image", state)

    assert state["packs"]["image"]["ready"] is True
    assert (tmp_path / "diffusion_models" / "m.safetensors").exists()
    assert (tmp_path / "diffusion_models" / "m.safetensors.ok").exists()
    saved = json.loads((tmp_path / ".status.json").read_text())
    assert saved["packs"]["image"]["ready"] is True
