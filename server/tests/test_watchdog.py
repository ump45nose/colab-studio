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


@pytest.mark.asyncio
async def test_run_setup_remote_only_prewarms_requested_pack(monkeypatch: pytest.MonkeyPatch):
    rt = Runtime()
    cmds: list[str] = []

    async def _fake_ssh(cmd: str, timeout: int = 120) -> str:
        cmds.append(cmd)
        if "test -f" in cmd or ".setup_done" in cmd:
            return "done"
        return ""

    async def _noop():
        return None

    async def _fast_sleep(_):
        return None

    monkeypatch.setattr(rt, "ssh", _fake_ssh)
    monkeypatch.setattr(rt, "_refresh_telemetry", _noop)
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    await rt._run_setup_Remote(initial_pack="video_wan22")
    assert "[r]untime_setup.sh video_wan22" in cmds[0]

    cmds.clear()
    await rt._run_setup_Remote(initial_pack=None)
    assert "[r]untime_setup.sh >" in cmds[0]


@pytest.mark.asyncio
async def test_start_tunnel_accepts_mux_exit_zero(monkeypatch: pytest.MonkeyPatch):
    rt = Runtime()
    rt._ssh_flags = ["-o", "ControlMaster=auto", "-o", "ControlPath=/tmp/ctl"]
    rt._ssh_host = "root@colab-studio"
    captured: list[list[str]] = []

    class _MuxZeroProc:
        stderr = None
        returncode = 0

        def poll(self):
            return 0

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    async def _fast_sleep(_):
        return None

    monkeypatch.setattr("server.runtime.subprocess.Popen", lambda cmd, **kw: captured.append(cmd) or _MuxZeroProc())
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    await rt._start_tunnel()
    assert "ControlPath=none" not in captured[0]
    assert "ControlMaster=auto" in captured[0]
