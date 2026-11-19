#!/bin/bash
# Colab GPU 运行时轻量化初始化脚本（ComfyUI 核心环境 + 可选按需模型预热）
#
# 用法: bash /content/station/runtime_setup.sh [pack ...]
#   仅后台预热传入的模型包（未传参时不预下载任何大模型，避免浪费开机耗时与流量）；
#   FaceFusion 与 DreamID-V 均改为首次换脸时按需部署。
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_HTTP_TIMEOUT=120
export UV_LINK_MODE=copy

COMFY_COMMIT="bc5f880dbdd43e426077f42ccec53bb577ffee9f"
INITIAL_PACKS=("$@")
STEP_FILE="/content/setup.step"

step() { echo "$1" > "$STEP_FILE"; echo "=== $1 ==="; }

mkdir -p /content/models/{diffusion_models,text_encoders,vae,loras,facefusion}
export XDG_CACHE_HOME=/content/models/.cache
export HF_HOME=/content/models/.cache/huggingface

# ---------------------------------------------------------------------------
# 1/2 准备模型下载环境；若指定了首个任务所需的模型包，立即在后台并行预热
# ---------------------------------------------------------------------------
step "1/2 准备模型下载环境"
if ! uv --version 2>/dev/null | grep -q '^uv 0.13.4'; then
    python3 -m pip install 'uv==0.13.4'
fi
if [ ! -x /content/hfenv/bin/python ]; then
    uv venv --python 3.12 /content/hfenv
fi
uv pip install --python /content/hfenv/bin/python 'huggingface_hub==1.20.1' 'hf_xet==1.8.0'

if [ "${#INITIAL_PACKS[@]}" -gt 0 ] && ! pgrep -f "/content/station/[m]odels.py" >/dev/null; then
    nohup /content/hfenv/bin/python /content/station/models.py "${INITIAL_PACKS[@]}" \
        > /content/models.log 2>&1 < /dev/null &
fi

# ---------------------------------------------------------------------------
# 2/2 安装 ComfyUI 核心环境（不阻塞等待大模型下载，由 ensure_models 接管进度）
# ---------------------------------------------------------------------------
step "2/2 下载并配置 ComfyUI"
if ! command -v ffmpeg >/dev/null; then
    apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null
fi

if [ ! -d /content/ComfyUI/.git ]; then
    git init -q /content/ComfyUI
    git -C /content/ComfyUI remote add origin https://github.com/comfyanonymous/ComfyUI.git
    git -C /content/ComfyUI fetch -q --depth 1 origin "$COMFY_COMMIT"
    git -C /content/ComfyUI checkout -q FETCH_HEAD
fi
for sub in diffusion_models text_encoders vae loras; do
    rm -rf "/content/ComfyUI/models/$sub"
    ln -s "/content/models/$sub" "/content/ComfyUI/models/$sub"
done

if [ ! -x /content/comfyenv/bin/python ]; then
    uv venv --python 3.13 --python-preference only-managed /content/comfyenv
fi
uv pip install --python /content/comfyenv/bin/python --no-deps \
    --index-strategy unsafe-best-match -r /content/station/comfy-requirements.lock

touch /content/.setup_done
rm -f "$STEP_FILE"
echo "=== SETUP OK ==="
