"""Tests for `server/studio.py` worker queue, pack resolution, and FaceSwap execution."""
from __future__ import annotations

from pathlib import Path
import pytest

from server import studio
from server.runtime import runtime


def test_pack_for_job_resolution():
    assert studio._pack_for_job({"kind": "image", "params": {"profile": "krea2_noct"}, "inputs": []}) == "image"
    assert studio._pack_for_job({"kind": "image", "params": {"profile": "z_image_turbo_nsfw"}, "inputs": []}) == "image_turbo"
    # Image edit with reference inputs always uses Krea2-Noct pack
    assert studio._pack_for_job({"kind": "image", "params": {"profile": "z_image_turbo_nsfw"}, "inputs": ["a.png"]}) == "image"
    assert studio._pack_for_job({"kind": "video", "params": {"profile": "minimax_h3"}}) == "video"
    assert studio._pack_for_job({"kind": "video", "params": {"profile": "wan22_remix"}}) == "video_wan22"
    assert studio._pack_for_job({"kind": "faceswap", "params": {}}) is None


@pytest.mark.asyncio
async def test_faceswap_worker_frees_vram_and_runs_compare_all(monkeypatch: pytest.MonkeyPatch):
    studio.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (studio.MEDIA_DIR / "src.png").write_bytes(b"src_face")
    (studio.MEDIA_DIR / "tgt.png").write_bytes(b"tgt_img")

    runtime.state = "ready"
    runtime.warm.add("image")

    freed_calls: list[str] = []
    ssh_cmds: list[str] = []

    async def _fake_ensure_ready():
        runtime.state = "ready"

    async def _fake_free(http):
        freed_calls.append("freed")
        runtime.warm.clear()

    async def _fake_ssh(cmd: str, timeout: int = 120) -> str:
        ssh_cmds.append(cmd)
        if "faceswap_runner.py" in cmd:
            return (
                "STUDIO_OUTPUT\thyperswap_1a_256\t/content/jobs/j/out/swap_1_hyperswap_1a_256.png\n"
                "STUDIO_OUTPUT\talphaface_256\t/content/jobs/j/out/swap_2_alphaface_256.png\n"
                "STUDIO_OUTPUT\tinswapper_128_fp16\t/content/jobs/j/out/swap_3_inswapper_128_fp16.png\n"
            )
        return ""

    def _fake_upload(local_path: Path, remote_path: str, timeout: int = 180) -> None:
        assert local_path.exists()

    def _fake_download(remote_path: str, local_path: Path, timeout: int = 300) -> None:
        local_path.write_bytes(b"swapped_image_bytes")

    monkeypatch.setattr(runtime, "ensure_ready", _fake_ensure_ready)
    monkeypatch.setattr(studio, "_free_comfy_vram", _fake_free)
    monkeypatch.setattr(runtime, "ssh", _fake_ssh)
    monkeypatch.setattr(runtime, "upload_file", _fake_upload)
    monkeypatch.setattr(runtime, "download_file", _fake_download)

    job = studio.enqueue(
        None,
        "faceswap",
        "三底模对比",
        {
            "engine": "facefusion_cli",
            "swapper_model": "hyperswap_1a_256",
            "compare_all": True,
            "pixel_boost": "512x512",
            "enhancer_model": "codeformer",
            "enhancer_blend": 50,
        },
        ["src.png", "tgt.png"],
    )
    await studio._work(job["id"])

    done = studio.jobs[job["id"]]
    assert done["status"] == "done"
    assert freed_calls == ["freed"]
    assert len(done["outputs"]) == 3
    assert [o["model"] for o in done["outputs"]] == [
        "hyperswap_1a_256",
        "alphaface_256",
        "inswapper_128_fp16",
    ]
