"""Unit tests for FaceFusion dual-patcher, FaceFusion CLI runner, and DreamID-V 81-frame slicer."""
from __future__ import annotations

from pathlib import Path
import pytest

from station import faceswap_runner, patch_facefusion
from server import dreamid_pipeline

SAMPLE_CONTENT_ANALYSER = """\
from typing import Any

PROBABILITY_LIMIT = 0.80

def pre_check() -> bool:
    download_directory_path = '/content/models'
    conditional_download_hashes(download_directory_path, {})
    return True

def analyse_stream(vision_frame: Any, video_fps: float) -> bool:
    return detect_nsfw(vision_frame)

def analyse_frame(vision_frame: Any) -> bool:
    return detect_nsfw(vision_frame)

def analyse_image(image_path: str) -> bool:
    frame = read_image(image_path)
    return analyse_frame(frame)

def analyse_video(video_path: str, trim_frame_start: int, trim_frame_end: int) -> bool:
    return True

def detect_nsfw(vision_frame: Any) -> bool:
    return True
"""

SAMPLE_CORE = """\
import sys
from facefusion import content_analyser, face_classifier, face_detector

def common_pre_check() -> bool:
    common_modules = [
        content_analyser,
        face_classifier,
        face_detector,
    ]
    return all(module.pre_check() for module in common_modules) and validate_hash(content_analyser.__file__)

def processors_pre_check() -> bool:
    return True
"""


def test_patch_content_analyser_disables_nsfw_and_skips_downloads():
    patched = patch_facefusion.patch_content_analyser(SAMPLE_CONTENT_ANALYSER)
    assert patch_facefusion.verify_content_analyser(patched)
    ns: dict = {}
    exec(compile(patched, "content_analyser.py", "exec"), ns)
    assert ns["pre_check"]() is True
    assert ns["analyse_frame"](None) is False
    assert ns["analyse_image"]("test.png") is False
    assert ns["analyse_video"]("test.mp4", 0, 100) is False
    assert ns["analyse_stream"](None, 24.0) is False
    assert ns["detect_nsfw"](None) is False
    assert "conditional_download_hashes" not in patched


def test_patch_core_bypasses_common_pre_check_hash_validation():
    patched = patch_facefusion.patch_core(SAMPLE_CORE)
    assert patch_facefusion.verify_core(patched)
    assert "validate_hash" not in patched
    # Idempotency check
    patched_twice = patch_facefusion.patch_core(patched)
    assert patch_facefusion.verify_core(patched_twice)


def test_apply_patches_on_directory(tmp_path: Path):
    ff_dir = tmp_path / "facefusion" / "facefusion"
    ff_dir.mkdir(parents=True)
    ca_file = ff_dir / "content_analyser.py"
    core_file = ff_dir / "core.py"
    ca_file.write_text(SAMPLE_CONTENT_ANALYSER, encoding="utf-8")
    core_file.write_text(SAMPLE_CORE, encoding="utf-8")

    patch_facefusion.apply_patches(tmp_path / "facefusion")
    assert patch_facefusion.verify_content_analyser(ca_file.read_text(encoding="utf-8"))
    assert patch_facefusion.verify_core(core_file.read_text(encoding="utf-8"))


def test_resolve_swapper_models_single_and_compare_all():
    assert faceswap_runner.resolve_swapper_models("hyperswap_1a_256", compare_all=False) == ["hyperswap_1a_256"]
    assert faceswap_runner.resolve_swapper_models("alphaface_256", compare_all=False) == ["alphaface_256"]
    assert faceswap_runner.resolve_swapper_models("hyperswap_1a_256", compare_all=True) == [
        "hyperswap_1a_256",
        "alphaface_256",
        "inswapper_128_fp16",
    ]
    with pytest.raises(ValueError, match="无效的换脸底模"):
        faceswap_runner.resolve_swapper_models("unknown_model", compare_all=False)


def test_build_facefusion_cmd_without_and_with_enhancer():
    cmd_raw = faceswap_runner.build_facefusion_cmd(
        source_paths=["/tmp/src1.png", "/tmp/src2.png"],
        target_path="/tmp/target.mp4",
        output_path="/tmp/out.mp4",
        swapper_model="hyperswap_1a_256",
        pixel_boost="512x512",
        enhancer_model="none",
        enhancer_blend=50,
    )
    assert "face_swapper" in cmd_raw
    assert "face_enhancer" not in cmd_raw
    assert "--face-swapper-model" in cmd_raw
    assert cmd_raw[cmd_raw.index("--face-swapper-model") + 1] == "hyperswap_1a_256"
    assert cmd_raw[cmd_raw.index("--face-swapper-pixel-boost") + 1] == "512x512"
    assert "-s" in cmd_raw

    cmd_enh = faceswap_runner.build_facefusion_cmd(
        source_paths=["/tmp/src1.png"],
        target_path="/tmp/target.png",
        output_path="/tmp/out.png",
        swapper_model="alphaface_256",
        pixel_boost="256x256",
        enhancer_model="codeformer",
        enhancer_blend=50,
    )
    assert "face_enhancer" in cmd_enh
    assert cmd_enh[cmd_enh.index("--face-enhancer-model") + 1] == "codeformer"
    assert cmd_enh[cmd_enh.index("--face-enhancer-blend") + 1] == "50"


def test_dreamid_plan_frame_chunks():
    assert dreamid_pipeline.plan_frame_chunks(45) == [(0, 45)]
    assert dreamid_pipeline.plan_frame_chunks(81) == [(0, 81)]
    assert dreamid_pipeline.plan_frame_chunks(200) == [(0, 81), (81, 81), (162, 38)]
    assert dreamid_pipeline.align_4n_plus_1(81) == 81
    assert dreamid_pipeline.align_4n_plus_1(38) == 37
    assert dreamid_pipeline.align_4n_plus_1(2) == 5

    slice_cmd = dreamid_pipeline.build_ffmpeg_slice_cmd("in.mp4", "chunk0.mp4", 0, 81, fps=24.0)
    assert slice_cmd[0] == "ffmpeg"
    assert "between(n\\,0\\,80)" in " ".join(slice_cmd)

    wan_cmd = dreamid_pipeline.build_wan_swapface_cmd(
        source_image="face.png",
        chunk_video="chunk0.mp4",
        output_chunk="swapped0.mp4",
        frame_count=81,
    )
    assert "--frame_num" in wan_cmd
    assert wan_cmd[wan_cmd.index("--frame_num") + 1] == "81"
    assert wan_cmd[wan_cmd.index("--ref_Path") + 1] == "chunk0.mp4,face.png"
