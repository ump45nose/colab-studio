#!/usr/bin/env bash
# Prepare DreamID-V Faster only when that engine is first used.
set -Eeuo pipefail

ROOT=/content/DreamID-V
ENV=/content/dreamenv
MODELS=/content/models/dreamid_v
COMMIT=9b589940577559c91481fb3a13bae000a55f97a1

if [[ -f /content/.dreamid_ready ]]; then
    exit 0
fi

if [[ ! -d "$ROOT/.git" ]]; then
    git init -q "$ROOT"
    git -C "$ROOT" remote add origin https://github.com/bytedance/DreamID-V.git
    git -C "$ROOT" fetch -q --depth 1 origin "$COMMIT"
    git -C "$ROOT" checkout -q FETCH_HEAD
fi

if [[ ! -x "$ENV/bin/python" ]]; then
    uv venv --python 3.12 "$ENV"
fi
uv pip install --python "$ENV/bin/python" --index-url https://download.pytorch.org/whl/cu128 \
    'torch==2.7.1' 'torchvision==0.22.1'
uv pip install --python "$ENV/bin/python" \
    'numpy>=1.23.5,<2' 'opencv-python-headless==4.10.0.84' \
    'diffusers==0.35.2' 'transformers==4.49.0' 'tokenizers==0.21.4' \
    'accelerate==1.11.0' 'onnxruntime-gpu==1.24.4' \
    tqdm imageio easydict ftfy dashscope imageio-ffmpeg einops matplotlib scipy decord

# The upstream Faster model calls flash_attention directly. Use its own PyTorch
# fallback when a prebuilt FlashAttention wheel is unavailable on Colab.
"$ENV/bin/python" - "$ROOT/dreamidv_wan_faster/modules/model.py" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text()
original = 'from .attention import flash_attention'
replacement = 'from .attention import attention as flash_attention'
if original in text:
    p.write_text(text.replace(original, replacement, 1))
elif replacement not in text:
    raise SystemExit('DreamID-V attention import changed; refusing to patch')
PY

mkdir -p "$MODELS/Wan2.1-T2V-1.3B" "$ROOT/pose/models"
/content/hfenv/bin/python - "$ROOT" "$MODELS" <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path
import sys
root, models = map(Path, sys.argv[1:])
for repo, name, dest in (
    ('XuGuo699/DreamID-V', 'dreamidv_faster.pth', models),
    ('XuGuo699/DreamID-V', 'dw-ll_ucoco_384.onnx', root / 'pose/models'),
    ('XuGuo699/DreamID-V', 'yolox_l.onnx', root / 'pose/models'),
    ('Wan-AI/Wan2.1-T2V-1.3B', 'Wan2.1_VAE.pth', models / 'Wan2.1-T2V-1.3B'),
):
    hf_hub_download(repo_id=repo, filename=name, local_dir=str(dest))
PY
touch /content/.dreamid_ready
