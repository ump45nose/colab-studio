"""Model catalog reader (`station/models.default.toml` + optional `models.toml` override).

Pure standard library (`tomllib`, Python 3.11+); zero third-party dependencies so both the
station downloader and the FastAPI server can import it directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import tomllib

STATION_DIR = Path(__file__).resolve().parent
REPO_ROOT = STATION_DIR.parent
DEFAULT_TOML = STATION_DIR / "models.default.toml"

# Required model slots per pack. Removing or renaming a slot is caught by validate().
SLOTS: dict[str, tuple[str, ...]] = {
    "image": ("diffusion", "encoder", "vae", "turbo_lora"),
    "image_turbo": ("diffusion", "encoder", "vae"),
    "video": ("diffusion", "encoder", "video_vae", "audio_vae", "turbo_lora"),
    "video_wan22": ("high_noise", "low_noise", "encoder", "vae"),
}


@dataclass(frozen=True)
class Entry:
    repo: str
    file: str       # Path inside the HuggingFace repository (may include subdirectories)
    target: str     # Local filename under /content/models/<dir>/<target>
    dir: str        # ComfyUI models/ subdirectory (diffusion_models, text_encoders, vae, loras)
    size_gb: float
    sha256: str | None = None


def resolve_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Catalog file priority: explicit parameter > $MODELS_TOML > ./models.toml > models.default.toml."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("MODELS_TOML")
    if env:
        return Path(env)
    user = REPO_ROOT / "models.toml"
    return user if user.exists() else DEFAULT_TOML


def load(path: str | os.PathLike[str] | None = None) -> dict[str, dict[str, Entry]]:
    p = resolve_path(path)
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    return validate(raw, source=str(p))


def validate(raw: dict, source: str = "<models.toml>") -> dict[str, dict[str, Entry]]:
    out: dict[str, dict[str, Entry]] = {}
    unknown = set(raw) - set(SLOTS)
    if unknown:
        raise ValueError(f"{source}: 未知模型包 {sorted(unknown)}（有效值：{sorted(SLOTS)}）")
    for pack, slots in SLOTS.items():
        sec = raw.get(pack)
        if not isinstance(sec, dict):
            raise ValueError(f"{source}: 缺少 [{pack}] 配置段")
        extra = set(sec) - set(slots)
        if extra:
            raise ValueError(f"{source}: [{pack}] 存在未知槽位 {sorted(extra)}（预期：{list(slots)}）")
        entries: dict[str, Entry] = {}
        for slot in slots:
            item = sec.get(slot)
            if not isinstance(item, dict):
                raise ValueError(f"{source}: 缺少 [{pack}.{slot}]")
            for req in ("repo", "file", "dir", "size_gb"):
                if req not in item:
                    raise ValueError(f"{source}: [{pack}.{slot}] 缺少必填字段 '{req}'")
            repo = item["repo"]
            file = item["file"]
            target = item.get("target") or Path(file).name
            if not isinstance(repo, str) or "/" not in repo:
                raise ValueError(f"{source}: [{pack}.{slot}].repo 必须为 'owner/name' 格式：{repo!r}")
            if not isinstance(file, str) or not file or ".." in Path(file).parts:
                raise ValueError(f"{source}: [{pack}.{slot}].file 非法：{file!r}")
            if not isinstance(target, str) or "/" in target or "\\" in target or target in ("", ".", ".."):
                raise ValueError(f"{source}: [{pack}.{slot}].target 必须为纯文件名：{target!r}")
            try:
                size = float(item["size_gb"])
            except (TypeError, ValueError) as e:
                raise ValueError(f"{source}: [{pack}.{slot}].size_gb 必须为数字") from e
            if size <= 0:
                raise ValueError(f"{source}: [{pack}.{slot}].size_gb 必须大于 0")
            sha = item.get("sha256")
            if sha is not None and (not isinstance(sha, str) or len(sha) != 64):
                raise ValueError(f"{source}: [{pack}.{slot}].sha256 必须为 64 位十六进制字符串")
            entries[slot] = Entry(
                repo=repo, file=file, target=target,
                dir=str(item["dir"]), size_gb=size, sha256=sha,
            )
        out[pack] = entries
    return out


def file_names(pack: str, path: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """Return {slot: ComfyUI local filename} for server/workflows.py."""
    return {slot: e.target for slot, e in load(path)[pack].items()}
