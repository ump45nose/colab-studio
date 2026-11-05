"""Colab Studio configuration (environment variables + `.env` loader)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv(Path(os.environ.get("STUDIO_ENV_FILE", REPO_DIR / ".env")))

HOST = os.environ.get("STUDIO_HOST") or os.environ.get("HOST") or "0.0.0.0"
PORT = int(os.environ.get("STUDIO_PORT") or os.environ.get("PORT") or "8190")
DATA_DIR = Path(
    os.environ.get("STUDIO_DATA") or os.environ.get("DATA_DIR") or (REPO_DIR / "data")
).expanduser()
IDLE_TIMEOUT_MIN = int(
    os.environ.get("STUDIO_IDLE_MINUTES") or os.environ.get("IDLE_TIMEOUT_MIN") or "30"
)
GPU_TIER = (os.environ.get("GPU_TIER") or os.environ.get("STUDIO_GPU") or "l4").lower()
COLAB_BIN = (
    os.environ.get("COLAB_BIN")
    or shutil.which("colab")
    or str(Path("~/.local/bin/colab").expanduser())
)
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
