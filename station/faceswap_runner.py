"""Headless FaceFusion CLI runner for Colab Studio.

Supports single-model execution (`hyperswap_1a_256` default) and same-pipeline
benchmark comparison (`compare_all=True`: runs `hyperswap_1a_256`, `alphaface_256`,
and `inswapper_128_fp16` sequentially on the same source and target media).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BENCHMARK_SWAPPER_MODELS: tuple[str, ...] = (
    "hyperswap_1a_256",
    "alphaface_256",
    "inswapper_128_fp16",
)
VALID_PIXEL_BOOSTS: tuple[str, ...] = (
    "256x256",
    "512x512",
    "768x768",
    "1024x1024",
)
VALID_ENHANCERS: tuple[str, ...] = (
    "none",
    "codeformer",
    "gfpgan_1.4",
)

MODEL_LABELS: dict[str, str] = {
    "hyperswap_1a_256": "HyperSwap 1A 256",
    "alphaface_256": "AlphaFace 256",
    "inswapper_128_fp16": "InSwapper 128 FP16",
}


def resolve_swapper_models(
    swapper_model: str = "hyperswap_1a_256",
    compare_all: bool = False,
) -> list[str]:
    """Return ordered list of swapper models to execute in this pipeline run."""
    if compare_all:
        return list(BENCHMARK_SWAPPER_MODELS)
    if swapper_model not in BENCHMARK_SWAPPER_MODELS:
        raise ValueError(f"无效的换脸底模: {swapper_model}")
    return [swapper_model]


def build_facefusion_cmd(
    *,
    source_paths: list[str | Path],
    target_path: str | Path,
    output_path: str | Path,
    swapper_model: str = "hyperswap_1a_256",
    pixel_boost: str = "256x256",
    enhancer_model: str = "none",
    enhancer_blend: int = 50,
    facefusion_dir: str | Path = "/content/facefusion",
    python_bin: str = "python3",
    execution_provider: str = "cuda",
) -> list[str]:
    """Construct the exact `facefusion.py headless-run` command line."""
    if not source_paths:
        raise ValueError("至少需要 1 张源人脸图像 (source_paths)")
    if swapper_model not in BENCHMARK_SWAPPER_MODELS:
        raise ValueError(f"无效的换脸底模: {swapper_model}")
    if pixel_boost not in VALID_PIXEL_BOOSTS:
        raise ValueError(f"无效的超分像素倍率: {pixel_boost}")
    if enhancer_model not in VALID_ENHANCERS:
        raise ValueError(f"无效的后处理增强模型: {enhancer_model}")
    if not (0 <= int(enhancer_blend) <= 100):
        raise ValueError(f"增强混合比必须在 0-100 之间: {enhancer_blend}")

    processors = ["face_swapper"]
    if enhancer_model != "none":
        processors.append("face_enhancer")

    script = Path(facefusion_dir) / "facefusion.py"
    cmd: list[str] = [
        python_bin,
        str(script),
        "headless-run",
        "--processors",
        *processors,
        "--face-swapper-model",
        swapper_model,
        "--face-swapper-pixel-boost",
        pixel_boost,
        "--target-path",
        str(target_path),
        "--output-path",
        str(output_path),
        "--execution-providers",
        execution_provider,
        "--log-level",
        "info",
    ]
    for src in source_paths:
        cmd.extend(["-s", str(src)])
    if enhancer_model != "none":
        cmd.extend([
            "--face-enhancer-model",
            enhancer_model,
            "--face-enhancer-blend",
            str(int(enhancer_blend)),
        ])
    return cmd


def emit_progress(stage: str, pct: int) -> None:
    print(f"STUDIO_PROGRESS\t{stage}\t{max(0, min(100, int(pct)))}", flush=True)


def emit_output(model: str, path: Path) -> None:
    print(f"STUDIO_OUTPUT\t{model}\t{path}", flush=True)


def run_facefusion_job(spec: dict) -> list[tuple[str, Path]]:
    """Execute one or all benchmark swapper models according to `spec`."""
    source_paths = [Path(p) for p in spec["source_paths"]]
    target_path = Path(spec["target_path"])
    output_dir = Path(spec["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    models = resolve_swapper_models(
        swapper_model=spec.get("swapper_model", "hyperswap_1a_256"),
        compare_all=bool(spec.get("compare_all", False)),
    )
    pixel_boost = spec.get("pixel_boost", "256x256")
    enhancer_model = spec.get("enhancer_model", "none")
    enhancer_blend = int(spec.get("enhancer_blend", 50))
    facefusion_dir = Path(spec.get("facefusion_dir") or os.environ.get("FACEFUSION_DIR", "/content/facefusion"))
    python_bin = spec.get("python_bin") or os.environ.get("FACEFUSION_PYTHON", "python3")
    provider = spec.get("execution_provider") or os.environ.get("FACEFUSION_PROVIDER", "cuda")

    ext = target_path.suffix.lower() or ".png"
    results: list[tuple[str, Path]] = []
    total = len(models)

    for idx, model in enumerate(models):
        label = MODEL_LABELS.get(model, model)
        base_pct = int(idx * 100 / total)
        emit_progress(f"正在运行 {label} ({idx + 1}/{total})", base_pct + 5)
        out_path = output_dir / f"swap_{idx + 1}_{model}{ext}"
        cmd = build_facefusion_cmd(
            source_paths=source_paths,
            target_path=target_path,
            output_path=out_path,
            swapper_model=model,
            pixel_boost=pixel_boost,
            enhancer_model=enhancer_model,
            enhancer_blend=enhancer_blend,
            facefusion_dir=facefusion_dir,
            python_bin=python_bin,
            execution_provider=provider,
        )
        proc = subprocess.run(cmd, cwd=str(facefusion_dir), text=True, capture_output=True)
        if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-600:]
            raise RuntimeError(f"FaceFusion ({model}) 执行失败 (code={proc.returncode}): {tail}")
        emit_output(model, out_path)
        emit_progress(f"已完成 {label} ({idx + 1}/{total})", int((idx + 1) * 100 / total))
        results.append((model, out_path))

    return results


def main(argv: list[str]) -> int:
    if not argv:
        print("用法: python3 faceswap_runner.py <spec.json>", file=sys.stderr)
        return 2
    spec_path = Path(argv[0])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    run_facefusion_job(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
