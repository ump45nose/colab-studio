"""Test fixtures: isolated temporary data directory and clean state per test."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.update(
    STUDIO_ENV_FILE="/nonexistent",
    STUDIO_DATA=tempfile.mkdtemp(prefix="studio-test-"),
    STUDIO_IDLE_MINUTES="30",
    STUDIO_PORT="0",
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server import config, studio, tracker  # noqa: E402
from server.runtime import runtime  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_test_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(studio, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(studio, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(tracker, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(tracker, "TIMINGS_FILE", tmp_path / "timings.json")
    monkeypatch.setattr(tracker, "STARTUP_FILE", tmp_path / "startup_timings.json")

    studio.chats.clear()
    studio.jobs.clear()
    studio.presets.clear()
    studio._queue = asyncio.Queue()
    studio._running_tasks.clear()
    studio._comfy_prompt_ids.clear()

    runtime.state = "off"
    runtime.step = "GPU 已关闭"
    runtime.error = None
    runtime.gpu_name = None
    runtime.vram_used_mb = 0
    runtime.vram_total_mb = 0
    runtime.models = {}
    runtime.setup_step = None
    runtime.active_jobs = 0
    runtime.warm.clear()
    runtime.log.clear()
    yield
