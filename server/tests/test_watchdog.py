"""Tests for `server/runtime.py` lifecycle, SSH file transfer helpers, and idle disconnect."""
from __future__ import annotations

import asyncio
import pytest

from server.runtime import Runtime, _clean_err


def test_clean_err_detects_unauthenticated_colab_cli():
    msg = _clean_err("Error: not authenticated; run colab auth login")
    assert "colab usage" in msg


@pytest.mark.asyncio
async def test_stop_resets_state(monkeypatch: pytest.MonkeyPatch):
    rt = Runtime()
    rt.state = "ready"
    rt.gpu_name = "NVIDIA L4"
    rt.vram_used_mb = 4096
    rt.warm.add("image")

    async def _fake_run(*args, **kw):
        return ""

    monkeypatch.setattr(rt, "_run", _fake_run)
    await rt.stop("测试关闭")
    assert rt.state == "off"
    assert rt.gpu_name is None
    assert not rt.warm


@pytest.mark.asyncio
async def test_ensure_models_returns_immediately_when_already_ready(monkeypatch: pytest.MonkeyPatch):
    rt = Runtime()
    rt.models = {"packs": {"image": {"ready": True, "total_gb": 17.4, "done_gb": 17.4}}}

    async def _noop():
        return None

    monkeypatch.setattr(rt, "_refresh_telemetry", _noop)
    await asyncio.wait_for(rt.ensure_models("image"), timeout=2.0)
