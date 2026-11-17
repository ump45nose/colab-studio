"""Build self-contained Kaggle trial notebooks; execute one workload inside Kaggle.

    python3.12 station/kaggle_trial.py prepare --mode faceswap
    python3.12 station/kaggle_trial.py prepare --mode image --owner YOUR_KAGGLE_NAME

Only public source files are embedded. Credentials and local media are never bundled.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMFY_COMMIT = "bc5f880dbdd43e426077f42ccec53bb577ffee9f"
FACEFUSION_REF = "3.9.2"
MODES = ("faceswap", "image", "image_turbo")
BUNDLE_FILES = (
    "station/kaggle_trial.py", "station/models.py", "station/catalog.py",
    "station/models.default.toml", "station/faceswap_runner.py",
    "station/comfy-requirements.lock", "server/workflows.py",
)
SAMPLES = {
    "source.jpg": "https://raw.githubusercontent.com/matplotlib/matplotlib/v3.10.0/lib/matplotlib/mpl-data/sample_data/grace_hopper.jpg",
    "target.png": "https://raw.githubusercontent.com/scikit-image/scikit-image/v0.19.3/skimage/data/astronaut.png",
}


def prepare(mode: str, output: Path, owner: str | None = None) -> Path:
    """Create an importable notebook, optionally with private T4 submission metadata."""
    if mode not in MODES:
        raise ValueError(f"未知试跑模式: {mode}")
    if owner and not re.fullmatch(r"[A-Za-z0-9_-]+", owner):
        raise ValueError("owner 必须是 Kaggle 用户名")
    output.mkdir(parents=True, exist_ok=True)
    notebook = output / "trial.ipynb"
    metadata = output / "kernel-metadata.json"
    if notebook.exists() or metadata.exists():
        raise FileExistsError(f"目录已有交付物，请换一个输出目录: {output}")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for filename in BUNDLE_FILES:
            bundle.writestr(filename, (REPO / filename).read_bytes())
    encoded = base64.b64encode(archive.getvalue()).decode("ascii")

    def cell(kind: str, source: str) -> dict:
        result = {"cell_type": kind, "metadata": {}, "source": source.splitlines(keepends=True)}
        if kind == "code":
            result.update(execution_count=None, outputs=[])
        return result

    cells = [
        cell("markdown", "# Colab Studio · Kaggle 免费 GPU 试跑\n\n"
             "选择 GPU T4 ×2 并启用 Internet，然后运行全部单元。只使用第一张卡。\n\n"
             "默认换脸素材为 Matplotlib 与 scikit-image 的公开示例，不上传本机素材。"
             "模型和环境留在临时盘，结果与运行记录保存在 `/kaggle/working`。\n\n"
             "先看换脸结果，再分别运行两套生图；生成完成不等于画质验收通过。\n"),
        cell("code", f'MODE = {mode!r}\nSOURCE_PATH = ""  # 留空使用公开示例，或填写已挂载的 Kaggle 素材路径\n'
             'TARGET_PATH = ""\nCOMPARE_ALL = True  # 同一素材比较三个换脸底模\n'
             'PROMPT = "A red ceramic teapot on a wooden table, morning window light, still life photography"\n'),
        cell("code", 'import base64, io, json, shutil, subprocess, sys, tempfile, zipfile\nfrom pathlib import Path\n'
             'if not Path("/kaggle/working").is_dir():\n    raise RuntimeError("请在 Kaggle GPU 笔记本运行")\n'
             'Path("/kaggle/temp").mkdir(exist_ok=True)\n'
             'bundle_root = Path(tempfile.mkdtemp(prefix="studio-source-", dir="/kaggle/temp"))\n'
             f'zipfile.ZipFile(io.BytesIO(base64.b64decode({encoded!r}))).extractall(bundle_root)\n'
             'output_dir = Path("/kaggle/working") / ("studio-" + MODE + "-" + bundle_root.name[-8:])\n'
             'cmd = [sys.executable, str(bundle_root / "station/kaggle_trial.py"), "run", "--mode", MODE,\n'
             '       "--output", str(output_dir), "--prompt", PROMPT]\n'
             'if SOURCE_PATH: cmd += ["--source", SOURCE_PATH]\n'
             'if TARGET_PATH: cmd += ["--target", TARGET_PATH]\n'
             'if COMPARE_ALL: cmd += ["--compare-all"]\n'
             'try:\n    result = subprocess.run(cmd)\nfinally:\n    shutil.rmtree(bundle_root)\n'
             'report = json.loads((output_dir / "result.json").read_text())\n'
             'print(json.dumps(report, ensure_ascii=False, indent=2))\n'
             'result.check_returncode()\n'),
        cell("code", 'from IPython.display import Image, display\n'
             'for item in report["outputs"]:\n    print(item["name"])\n    display(Image(filename=str(output_dir / item["name"])))\n'),
    ]
    notebook.write_text(json.dumps({
        "cells": cells,
        "metadata": {"accelerator": "gpu", "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4, "nbformat_minor": 4,
    }, ensure_ascii=False, indent=1) + "\n")
    if owner:
        slug = f"colab-studio-{mode.replace('_', '-')}-trial-{uuid.uuid4().hex[:8]}"
        metadata.write_text(json.dumps({
            "id": f"{owner}/{slug}", "title": slug.replace("-", " "),
            "code_file": notebook.name, "language": "python", "kernel_type": "notebook",
            "is_private": True, "enable_gpu": True, "enable_internet": True,
            "docker_image_pinning_type": "latest",
            "machine_shape": "NvidiaTeslaT4", "dataset_sources": [],
            "competition_sources": [], "kernel_sources": [], "model_sources": [],
        }, indent=2) + "\n")
    return notebook


def gpu_info() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        devices = [p.name for p in Path("/dev").glob("nvidia*")]
        raise RuntimeError(f"Kaggle 环境未提供 nvidia-smi；显卡设备: {devices}。请检查实际 GPU 分配")
    result = subprocess.run([
        "nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits",
    ], check=True, text=True, capture_output=True)
    return [dict(zip(("name", "memory_mb", "driver"), (v.strip() for v in line.split(",")), strict=True))
            for line in result.stdout.splitlines() if line.strip()]


class MemorySampler:
    """Sample physical GPU 0 usage; this is an observed peak, not a CUDA allocator peak."""

    def __init__(self):
        self.peak_mb = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        while not self.stop.is_set():
            try:
                result = subprocess.run([
                    "nvidia-smi", "--id=0", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                ], check=True, text=True, capture_output=True, timeout=10)
                self.peak_mb = max(self.peak_mb, int(result.stdout.strip()))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self.stop.wait(2)


def command(args: list[str], env: dict, *, cwd: Path | None = None) -> None:
    subprocess.run(args, env=env, cwd=cwd, check=True, timeout=1800)


def checkout(url: str, ref: str, destination: Path, env: dict) -> None:
    command(["git", "init", "-q", str(destination)], env)
    command(["git", "remote", "add", "origin", url], env, cwd=destination)
    command(["git", "fetch", "-q", "--depth", "1", "origin", ref], env, cwd=destination)
    command(["git", "checkout", "-q", "FETCH_HEAD"], env, cwd=destination)


def face_trial(root: Path, output: Path, env: dict, args: argparse.Namespace, report: dict) -> list[Path]:
    t0 = time.monotonic()
    source = Path(args.source).resolve() if args.source else root / "source.jpg"
    target = Path(args.target).resolve() if args.target else root / "target.png"
    for path, supplied in ((source, args.source), (target, args.target)):
        if not supplied:
            with urllib.request.urlopen(SAMPLES[path.name], timeout=60) as response:
                path.write_bytes(response.read())
        if not path.is_file():
            raise FileNotFoundError(f"未找到素材: {path}")
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
    facefusion = root / "facefusion"
    checkout("https://github.com/facefusion/facefusion.git", FACEFUSION_REF, facefusion, env)
    python = root / "faceenv/bin/python"
    command(["uv", "venv", "--python", "3.12", str(python.parent.parent)], env)
    requirements = root / "face-requirements.txt"
    requirements.write_text("\n".join(line for line in (facefusion / "requirements.txt").read_text().splitlines()
                                      if not line.startswith("onnxruntime")))
    command(["uv", "pip", "install", "--python", str(python), "-r", str(requirements),
             "onnxruntime-gpu[cuda,cudnn]==1.24.4"], env)
    # Expose the isolated CUDA 12 libraries to FaceFusion's subprocess.
    site = subprocess.check_output([str(python), "-c", "import site; print(site.getsitepackages()[0])"], env=env, text=True).strip()
    env["LD_LIBRARY_PATH"] = ":".join([*(str(p) for p in Path(site).glob("nvidia/*/lib")), env.get("LD_LIBRARY_PATH", "")])
    spec = {
        "source_paths": [str(source)], "target_path": str(target), "output_dir": str(output),
        "facefusion_dir": str(facefusion), "python_bin": str(python),
        "compare_all": args.compare_all, "execution_provider": "cuda",
    }
    spec_path = root / "faceswap.json"
    spec_path.write_text(json.dumps(spec))
    report["setup_seconds"] = round(time.monotonic() - t0, 2)
    t0 = time.monotonic()
    command([str(python), str(REPO / "station/faceswap_runner.py"), str(spec_path)], env)
    report["generation_seconds"] = round(time.monotonic() - t0, 2)
    # A compiled-in provider name alone does not establish working CUDA inference.
    command([str(python), "-c",
             "import onnxruntime as ort, sys; ort.preload_dlls(directory=''); "
             "s=ort.InferenceSession(sys.argv[1], providers=['CUDAExecutionProvider']); "
             "assert s.get_providers()[0]=='CUDAExecutionProvider', 'CUDA provider fell back to CPU'",
             str(facefusion / ".assets/models/hyperswap_1a_256.onnx")], env)
    return sorted(output.glob("swap_*"))


def http_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def image_trial(root: Path, output: Path, env: dict, args: argparse.Namespace, report: dict) -> list[Path]:
    driver = tuple(int(v) for v in report["gpus"][0]["driver"].split("."))
    if driver < (580, 65, 6):
        raise RuntimeError("当前生图环境要求 CUDA 13 驱动 >=580.65.06；此 Kaggle 驱动不足，保留 Colab 运行")
    t0 = time.monotonic()
    comfy = root / "ComfyUI"
    checkout("https://github.com/comfyanonymous/ComfyUI.git", COMFY_COMMIT, comfy, env)
    python = root / "comfyenv/bin/python"
    command(["uv", "venv", "--python", "3.13", str(python.parent.parent)], env)
    command(["uv", "pip", "install", "--python", str(python), "--no-deps", "--index-strategy", "unsafe-best-match",
             "-r", str(REPO / "station/comfy-requirements.lock")], env)
    command(["uv", "venv", "--python", "3.12", str(root / "hfenv")], env)
    command(["uv", "pip", "install", "--python", str(root / "hfenv/bin/python"),
             "huggingface_hub==1.20.1", "hf_xet==1.8.0"], env)
    report["setup_seconds"] = round(time.monotonic() - t0, 2)
    t0 = time.monotonic()
    command([str(root / "hfenv/bin/python"), str(REPO / "station/models.py"), args.mode], env)
    report["download_seconds"] = round(time.monotonic() - t0, 2)
    for directory in ("diffusion_models", "text_encoders", "vae", "loras"):
        # Use an extra model path rather than replacing ComfyUI's existing folders.
        (root / "models" / directory).mkdir(parents=True, exist_ok=True)
    paths = root / "model-paths.yaml"
    paths.write_text("studio:\n  base_path: " + str(root / "models") + "\n" +
                     "".join(f"  {d}: {d}/\n" for d in ("diffusion_models", "text_encoders", "vae", "loras")))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from server.workflows import image_generate
    workflow = image_generate(
        args.prompt, profile="krea2_noct" if args.mode == "image" else "z_image_turbo_nsfw",
        size="1024", steps=8, cfg=1.0, turbo=True, seed=7,
    )
    for node in workflow.values():
        if node["class_type"] == "CLIPLoader":
            node["inputs"]["device"] = "cpu"
        if node["class_type"] == "SaveImage":
            node["inputs"]["filename_prefix"] = "trial"
    base = "http://127.0.0.1:8188"
    with open(output / "comfy.log", "w") as log:
        process = subprocess.Popen([
            str(python), str(comfy / "main.py"), "--listen", "127.0.0.1", "--port", "8188",
            "--disable-auto-launch", "--lowvram", "--force-fp16", "--cpu-vae",
            "--extra-model-paths-config", str(paths), "--output-directory", str(output),
        ], env=env, cwd=comfy, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 300
            while True:
                if process.poll() is not None:
                    raise RuntimeError("ComfyUI 启动失败，查看 comfy.log")
                try:
                    http_json(base + "/system_stats")
                    break
                except (OSError, ValueError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("ComfyUI 启动超过 5 分钟，查看 comfy.log") from None
                    time.sleep(2)
            t0 = time.monotonic()
            prompt_id = http_json(base + "/prompt", {"prompt": workflow})["prompt_id"]
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("生成进程退出，查看 comfy.log")
                history = http_json(base + "/history/" + prompt_id).get(prompt_id)
                if history:
                    report["execution_status"] = history.get("status")
                    if history.get("status", {}).get("status_str") != "success":
                        raise RuntimeError("生图失败，查看 result.json 中的 execution_status 和 comfy.log")
                    report["generation_seconds"] = round(time.monotonic() - t0, 2)
                    return sorted(output.glob("trial*.png"))
                time.sleep(2)
            raise TimeoutError("生图超过 30 分钟，停止试跑并保留 Colab")
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run(args: argparse.Namespace) -> int:
    if not Path("/kaggle/working").is_dir():
        raise RuntimeError("run 仅用于 Kaggle；本机请使用 prepare 生成笔记本")
    output = args.output.resolve()
    if not output.is_relative_to(Path("/kaggle/working")):
        raise ValueError("结果必须保存在 /kaggle/working 内")
    output.mkdir(parents=True, exist_ok=False)
    Path("/kaggle/temp").mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="studio-runtime-", dir="/kaggle/temp"))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", HF_XET_HIGH_PERFORMANCE="1",
               MODELS_DIR=str(root / "models"), HF_HOME=str(root / "hf-cache"),
               UV_CACHE_DIR=str(root / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(root / "python"),
               UV_LINK_MODE="copy", UV_HTTP_TIMEOUT="120")
    report = {"mode": args.mode, "status": "failed", "outputs": [], "visual_acceptance": "pending"}
    sampler = MemorySampler()
    started = time.monotonic()
    try:
        report["gpus"] = gpu_info()
        if not report["gpus"]:
            raise RuntimeError("未分配 GPU，请选择 T4 ×2")
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Kaggle 环境缺少 ffmpeg")
        if not shutil.which("uv"):
            command([sys.executable, "-m", "pip", "install", "uv==0.13.4"], env)
        sampler.thread.start()
        outputs = (face_trial if args.mode == "faceswap" else image_trial)(root, output, env, args, report)
        if not outputs:
            raise RuntimeError("生成结束但没有结果文件")
        # Kaggle's notebook image includes Pillow; decode every artifact before declaring completion.
        from PIL import Image
        for path in outputs:
            with Image.open(path) as image:
                image.load()
                dimensions = list(image.size)
            report["outputs"].append({"name": path.name, "bytes": path.stat().st_size,
                                      "dimensions": dimensions, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        report["status"] = "completed"
        return 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        sampler.stop.set()
        if sampler.thread.is_alive():
            sampler.thread.join(timeout=12)
        report["observed_peak_gpu0_mb"] = sampler.peak_mb
        report["total_seconds"] = round(time.monotonic() - started, 2)
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        # Only this run's disposable runtime is removed; generated media stays in working/.
        shutil.rmtree(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--mode", choices=MODES, default="faceswap")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--owner", help="Kaggle 用户名；提供时同时生成私有 T4 提交配置")
    parser.add_argument("--source", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--compare-all", action="store_true")
    parser.add_argument("--prompt", default="A red ceramic teapot on a wooden table, morning light, still life photography")
    args = parser.parse_args()
    if args.output is None:
        args.output = REPO / "outputs" / f"kaggle-{args.mode}-{uuid.uuid4().hex[:8]}"
    if args.action == "prepare":
        print(prepare(args.mode, args.output, args.owner).resolve())
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
