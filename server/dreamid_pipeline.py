"""DreamID-V Faster (`wan_swapface.py`) 81-frame video slicing & concat orchestrator.

Why this module exists:
`DreamID-V/express_adaption/wan_swapface.py` only loads the first `frame_num=81` frames
(`4n + 1`, ~3.37s at 24fps) of a target video and discards the rest. To support arbitrary-length
videos without modifying `DreamID-V`'s internal diffusion tensor shapes, this orchestrator:
1. Splits the input video into contiguous `<= 81`-frame segments via FFmpeg.
2. Runs `wan_swapface.py` on each segment (aligning `frame_num` to `4n + 1`).
3. Concatenates all swapped segments via FFmpeg `concat` demuxer and muxes back the original audio track.
"""
from __future__ import annotations

from pathlib import Path

MAX_DREAMID_FRAMES = 81


def align_4n_plus_1(frames: int, max_frames: int = MAX_DREAMID_FRAMES) -> int:
    """Clamp and align a frame count to `4n + 1` required by Wan2.1 3D VAE."""
    clamped = max(5, min(int(frames), int(max_frames)))
    return ((clamped - 1) // 4) * 4 + 1


def plan_frame_chunks(total_frames: int, max_frames: int = MAX_DREAMID_FRAMES) -> list[tuple[int, int]]:
    """Plan `(start_frame, frame_count)` slices so no slice exceeds `max_frames` (81)."""
    if total_frames <= 0:
        raise ValueError(f"视频总帧数必须大于 0: {total_frames}")
    if max_frames < 5 or (max_frames - 1) % 4 != 0:
        raise ValueError(f"max_frames 必须满足 4n+1 (>=5): {max_frames}")

    chunks: list[tuple[int, int]] = []
    cursor = 0
    while cursor < total_frames:
        rem = total_frames - cursor
        count = min(rem, max_frames)
        chunks.append((cursor, count))
        cursor += count
    return chunks


def build_ffmpeg_slice_cmd(
    input_video: str | Path,
    output_chunk: str | Path,
    start_frame: int,
    frame_count: int,
    fps: float = 24.0,
) -> list[str]:
    """Build FFmpeg command to extract frames `[start_frame, start_frame + frame_count)`."""
    end_frame = start_frame + frame_count - 1
    vf = f"select='between(n\\,{start_frame}\\,{end_frame})',setpts=N/({fps}*TB)"
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "16",
        str(output_chunk),
    ]


def build_wan_swapface_cmd(
    *,
    source_image: str | Path,
    chunk_video: str | Path,
    output_chunk: str | Path,
    frame_count: int,
    size: str = "832*480",
    sample_steps: int = 12,
    dreamid_dir: str | Path = "/content/DreamID-V",
    ckpt_dir: str | Path = "/content/models/dreamid_v/Wan2.1-T2V-1.3B",
    dreamid_ckpt: str | Path = "/content/models/dreamid_v/dreamidv_faster.pth",
    python_bin: str = "python3",
) -> list[str]:
    """Build the `wan_swapface.py` CLI invocation for a single `<= 81`-frame slice."""
    aligned_frames = align_4n_plus_1(frame_count)
    script = Path(dreamid_dir) / "express_adaption" / "wan_swapface.py"
    return [
        python_bin,
        str(script),
        "--task",
        "swapface",
        "--size",
        size,
        "--ckpt_dir",
        str(ckpt_dir),
        "--dreamidv_ckpt",
        str(dreamid_ckpt),
        "--sample_steps",
        str(int(sample_steps)),
        "--frame_num",
        str(aligned_frames),
        "--Sample_guide_scale_img",
        "4.0",
        "--ref_Path",
        f"{chunk_video},{source_image}",
        "--save_file",
        str(output_chunk),
    ]


def build_ffmpeg_concat_mux_cmd(
    concat_list_path: str | Path,
    original_video: str | Path,
    final_output: str | Path,
) -> list[str]:
    """Build FFmpeg command to concatenate swapped video chunks and restore original audio."""
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-i",
        str(original_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-shortest",
        str(final_output),
    ]
