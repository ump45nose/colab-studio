"""Colab GPU model downloader: pulls packs defined in `models.default.toml` (or `models.toml`)
into `/content/models` and writes real-time status to `/content/models/.status.json`.

Usage: `python3 models.py image` or `python3 models.py image video`
Runs inside `/content/hfenv` (isolated `huggingface_hub` + `hf_transfer` environment).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
from huggingface_hub import hf_hub_download, hf_hub_url

import catalog

ROOT = Path(os.environ.get("MODELS_DIR", "/content/models"))
STATUS = ROOT / ".status.json"
TOKEN = os.environ.get("HF_TOKEN") or None


def load_packs(path: str | os.PathLike[str] | None = None) -> dict[str, list[tuple[str, str, str, str, float, str | None]]]:
    """Read catalog into `{pack: [(repo, hf_file, local_target, subdir, size_gb, sha256), ...]}`."""
    return {
        pack: [(e.repo, e.file, e.target, e.dir, e.size_gb, e.sha256) for e in slots.values()]
        for pack, slots in catalog.load(path).items()
    }


PACKS = load_packs()


def _existing_bytes(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    except OSError:
        pass
    return 0


def write_status(state: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(ROOT)
    state["disk_free_gb"] = round(disk.free / 1e9, 1)
    state["disk_total_gb"] = round(disk.total / 1e9, 1)
    state["updated_at"] = time.time()
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(STATUS)


def verify_sha256(path: Path, expected: str | None) -> bool:
    if not expected:
        return True
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    if actual != expected.lower():
        print(f"[models] ✗ {path.name}: sha256 不匹配（实际 {actual[:12]}… != 期望 {expected[:12]}…），已删除", flush=True)
        path.unlink(missing_ok=True)
        return False
    return True


def _stream_url(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "colab-studio/2.0"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, length=16 * 1024 * 1024)


def download_file(repo: str, filename: str, dest: Path) -> None:
    """Download directly to `dest.with_suffix('.part')` then atomically rename to `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    cache = dest.parent / ".hfcache"
    url = hf_hub_url(repo_id=repo, filename=filename)
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            part.unlink(missing_ok=True)
            _stream_url(url, part)
            if part.stat().st_size == 0:
                raise RuntimeError("下载得到空文件")
            part.replace(dest)
            return
        except Exception as e:
            last_err = e
            print(f"[models] 直连流式下载重试 {attempt + 1}/3 ({dest.name}): {e}", flush=True)
            time.sleep(2 ** attempt)
    try:
        got = Path(hf_hub_download(
            repo_id=repo, filename=filename, token=TOKEN,
            local_dir=str(cache),
        ))
        shutil.move(str(got), str(dest))
        shutil.rmtree(cache, ignore_errors=True)
    except Exception as e:
        shutil.rmtree(cache, ignore_errors=True)
        if last_err is not None:
            raise last_err from e
        raise


def ensure_pack(name: str, state: dict) -> None:
    items = PACKS[name]
    total_gb = round(sum(sz for *_, sz, _ in items), 2)
    pstate = state["packs"].setdefault(name, {"ready": False, "total_gb": total_gb, "done_gb": 0.0, "current": None})
    pstate["total_gb"] = total_gb
    done = 0.0
    for repo, hf_file, target, subdir, size_gb, sha256 in items:
        dest = ROOT / subdir / target
        marker = dest.with_name(dest.name + ".ok")
        if dest.exists() and dest.stat().st_size > 0 and marker.exists():
            done += size_gb
            pstate["done_gb"] = round(done, 2)
            write_status(state)
            continue
        pstate["current"] = target
        write_status(state)
        t0 = time.time()
        print(f"[models] 正在下载 {name}/{target} ({size_gb} GB) <- {repo}:{hf_file} ...", flush=True)
        if not (dest.exists() and dest.stat().st_size > 0):
            download_file(repo, hf_file, dest)
        if not verify_sha256(dest, sha256):
            raise RuntimeError(f"{target}: sha256 校验失败")
        marker.touch()
        dt = max(time.time() - t0, 0.1)
        done += size_gb
        pstate["done_gb"] = round(done, 2)
        print(f"[models] ✓ {target} ({dt:.0f}s, {size_gb * 1024 / dt:.0f} MB/s)", flush=True)
        write_status(state)
    pstate["current"] = None
    pstate["ready"] = True
    write_status(state)


def main(argv: list[str]) -> int:
    packs = argv or ["image"]
    state: dict = {"packs": {}}
    if STATUS.exists():
        try:
            state = json.loads(STATUS.read_text())
        except Exception:
            state = {"packs": {}}
    state.setdefault("packs", {})
    write_status(state)
    rc = 0
    for name in packs:
        if name not in PACKS:
            print(f"[models] 未知模型包：{name}", file=sys.stderr)
            rc = 1
            continue
        try:
            ensure_pack(name, state)
        except Exception as e:
            state["packs"].setdefault(name, {})["error"] = str(e)
            state["packs"][name]["current"] = None
            write_status(state)
            print(f"[models] ✗ {name}: {e}", file=sys.stderr, flush=True)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
