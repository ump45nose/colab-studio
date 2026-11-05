#!/bin/bash
# Colab GPU 运行时轻量化初始化脚本（ComfyUI + FaceFusion Headless 双补丁流水线）
#
# 用法: bash /content/station/runtime_setup.sh [pack ...]
#   默认仅后台预热下载 `image` 模型包，其余包（`image_turbo`、`video`、`video_wan22`）按需触发下载。
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_HTTP_TIMEOUT=120
export UV_LINK_MODE=copy

COMFY_COMMIT="a91bbcc5a2ebbf3fb3fe5efac2ce9bf1fbef6cab"
FACEFUSION_REF="${FACEFUSION_REF:-3.1.2}"
INITIAL_PACKS=("${@:-image}")
STEP_FILE="/content/setup.step"

step() { echo "$1" > "$STEP_FILE"; echo "=== $1 ==="; }

mkdir -p /content/models/{diffusion_models,text_encoders,vae,loras,facefusion}
export XDG_CACHE_HOME=/content/models/.cache
export HF_HOME=/content/models/.cache/huggingface

# ---------------------------------------------------------------------------
# 1/4 创建模型下载环境并后台拉取初始模型包
# ---------------------------------------------------------------------------
step "1/4 准备模型下载环境"
if [ ! -x /content/hfenv/bin/python ]; then
    uv venv --python 3.12 /content/hfenv
    uv pip install --python /content/hfenv/bin/python "huggingface_hub>=0.25,<1.0" "hf_transfer>=0.1.8"
fi

if ! pgrep -f "/content/station/models.py" >/dev/null; then
    nohup /content/hfenv/bin/python /content/station/models.py "${INITIAL_PACKS[@]}" \
        > /content/models.log 2>&1 < /dev/null &
fi

# ---------------------------------------------------------------------------
# 2/4 安装 ComfyUI 核心环境
# ---------------------------------------------------------------------------
step "2/4 下载并配置 ComfyUI"
git config --global advice.detachedHead false
if ! command -v ffmpeg >/dev/null; then
    apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null &
fi

if [ ! -d /content/ComfyUI/.git ]; then
    git init -q /content/ComfyUI
    git -C /content/ComfyUI remote add origin https://github.com/comfyanonymous/ComfyUI.git
    git -C /content/ComfyUI fetch -q --depth 1 origin "$COMFY_COMMIT"
    git -C /content/ComfyUI checkout -q FETCH_HEAD
fi
wait

for sub in diffusion_models text_encoders vae loras; do
    rm -rf "/content/ComfyUI/models/$sub"
    ln -s "/content/models/$sub" "/content/ComfyUI/models/$sub"
done

uv pip install --system \
    -r /content/ComfyUI/requirements.txt \
    gguf scipy

# ---------------------------------------------------------------------------
# 3/4 部署 FaceFusion CLI 并应用 NSFW 短路与哈希自检绕过双补丁
# ---------------------------------------------------------------------------
step "3/4 部署 FaceFusion CLI 并应用安全自检绕过补丁"
if [ ! -d /content/facefusion/.git ]; then
    git init -q /content/facefusion
    git -C /content/facefusion remote add origin https://github.com/facefusion/facefusion.git
    git -C /content/facefusion fetch -q --depth 1 origin "$FACEFUSION_REF" || git -C /content/facefusion fetch -q --depth 1 origin master
    git -C /content/facefusion checkout -q FETCH_HEAD
fi

if [ -f /content/facefusion/requirements.txt ]; then
    uv pip install --system -r /content/facefusion/requirements.txt onnxruntime-gpu || true
fi

python3 /content/station/patch_facefusion.py /content/facefusion

# ---------------------------------------------------------------------------
# 4/4 等待初始模型包就绪
# ---------------------------------------------------------------------------
for pack in "${INITIAL_PACKS[@]}"; do
    step "4/4 等待模型包就绪 ($pack)"
    while true; do
        status=$(python3 - "$pack" <<'PY'
import json, sys
p = sys.argv[1]
try:
    d = json.load(open("/content/models/.status.json"))["packs"].get(p, {})
    if d.get("ready"):
        print("ready")
    elif d.get("error"):
        print("err:" + str(d["error"]))
except Exception:
    pass
PY
        )
        if [ "$status" = "ready" ]; then
            break
        elif [[ "$status" == err:* ]]; then
            echo "模型下载失败 ($pack): ${status#err:}" >&2
            tail -n 30 /content/models.log >&2 || true
            exit 1
        fi
        if ! pgrep -f "/content/station/models.py" >/dev/null; then
            /content/hfenv/bin/python /content/station/models.py "$pack" >> /content/models.log 2>&1
            break
        fi
        sleep 2
    done
done

touch /content/.setup_done
rm -f "$STEP_FILE"
echo "=== SETUP OK ==="
