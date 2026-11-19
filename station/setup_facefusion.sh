#!/usr/bin/env bash
# Prepare FaceFusion CLI + dual NSFW/hash bypass patches only when first used.
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_HTTP_TIMEOUT=120
export UV_LINK_MODE=copy

ROOT=/content/facefusion
ENV=/content/faceenv
FACEFUSION_REF="${FACEFUSION_REF:-3.9.2}"

if [[ -f /content/.facefusion_ready ]]; then
    exit 0
fi

if [[ ! -d "$ROOT/.git" ]]; then
    git init -q "$ROOT"
    git -C "$ROOT" remote add origin https://github.com/facefusion/facefusion.git
    git -C "$ROOT" fetch -q --depth 1 origin "$FACEFUSION_REF"
    git -C "$ROOT" checkout -q FETCH_HEAD
fi

if [[ ! -x "$ENV/bin/python" ]]; then
    uv venv --python 3.12 "$ENV"
fi

uv pip install --python "$ENV/bin/python" \
    -r <(sed '/^onnxruntime[=<>]/d' "$ROOT/requirements.txt") \
    'onnxruntime-gpu==1.24.4'

python3 /content/station/patch_facefusion.py "$ROOT"
touch /content/.facefusion_ready
