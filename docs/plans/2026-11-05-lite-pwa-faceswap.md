# Colab Studio 轻量化、PWA 改造与换脸流水线集成计划

## 1. 背景与目标

基于 `berkeduruu/colab-studio` 进行二次开发（Fork 仓库 `ump45nose/colab-studio`），替代原 `fn` NAS 上的过渡型 `colab-comfy-gateway`，构建专注 **图片生成/编辑 + 视频生成 + 全自动换脸** 的轻量级远程 GPU 工作站（前端 Web PWA + 后端 FastAPI 状态/队列引擎 + MCP Server）。

## 2. 范围与关键决定

### 2.1 轻量化裁剪与中文化
- **移除冗余模态**：彻底移除 `model3d`（TRELLIS.2）、`music`（YuE2）、`speech`（Qwen3-TTS / Chatterbox 及其独立 Python 3.13 `shared_legacy_t4` 虚拟环境）、`transcribe`（Whisper）以及 `enhance`（9.5 GB Qwen3.5-9B 提示词扩写模型）。
- **清理依赖**：从 `server/web/package.json` 移除 `@google/model-viewer` 与 `three`，删除 `server/web/src/Model3D.tsx`、`station/audio_requirements.txt` 与 `server/prompts/`。
- **保留并聚焦三大核心模式**：`image`（生图/修图）、`video`（文生视频/图生视频）、`faceswap`（全自动换脸流水线）。
- **语言与界面**：以中文（`zh`）为默认主语言，保留英文（`en`）切换映射，清理原有的土耳其语硬编码。

### 2.2 多工作流（Profile）支持
- **图片模式 (`image`)**：
  - `krea2_noct`（默认）：支持 `Noctaluna/Krea2-Noct-Uncensored` (`KreaNoct_V4_int8_convrot.safetensors` / `NoctQ_V4_int8_convrot.safetensors`) + `qwen3vl_8b_int8_convrot.safetensors` + `qwen_image_2.1_vae_bf16.safetensors` + Turbo LoRA，原生兼顾文生图与多参考图编辑。
  - `z_image_turbo_nsfw`：`tewea/z_image_turbo_bf16_nsfw` (`z_image_turbo_bf16_nsfw_v2.safetensors`) + `CLIPLoader(type="lumina2", clip_name="qwen_3_4b.safetensors")` + `zimage-ae.safetensors`，8 步 CFG=1.0 极速生图。
- **视频模式 (`video`)**：
  - `wan22_remix`：`FX-FeiHou/wan2.2-Remix` A14B High/Low Noise 双阶段 FP8 模型 + `WanImageToVideo` + 双 `KSamplerAdvanced` 接力采样。
  - `minimax_h3`（默认）：`Comfy-Org/MiniMax-H3` INT8/NVFP4 量化包，支持首尾帧图生视频与音视频同步生成。

### 2.3 PWA 渐进式 Web 应用改造
- 新增 `server/web/public/manifest.webmanifest`、`server/web/public/sw.js` 与矢量图标 `server/web/public/icon.svg`。
- 在 `server/web/index.html` 与 `server/web/src/styles.css` 注入移动端 `standalone` 视口与 `safe-area-inset-*` 适配。
- 在 `server/app.py` 暴露 `/manifest.webmanifest`、`/sw.js` 与 `/icon.svg`。

### 2.4 换脸（FaceSwap）全链路集成
- **阶段一：远端 GPU `FaceFusion CLI` 全自动批处理流水线**：
  - 在 `station/patch_facefusion.py` 与 `station/runtime_setup.sh` 中自动克隆 `facefusion/facefusion` 并确定性执行**两处补丁**（带自动校验）：
    1. `facefusion/content_analyser.py`：短路 `analyse_frame`、`analyse_image`、`analyse_video`、`detect_nsfw` 返回 `False`，`pre_check` 返回 `True`（跳过 NSFW 模型下载与拦截）。
    2. `facefusion/core.py`：移除 `common_pre_check()` 中对 `content_analyser.py` 的文件哈希校验，防止篡改自检退出。
  - **底模与同管道对比基准**：
    - `hyperswap_1a_256`（默认主力，256×256 原生分辨率，肤色光影融合更自然）
    - `alphaface_256`（大侧脸/夸张姿态增强对比）
    - `inswapper_128_fp16`（经典速度基线）
    - 支持 `compare_all: true` 一键在同一管道内跑完三个底模并排输出对比。
  - **画质增强后处理受控策略**：
    - `enhancer_model`：默认 `"none"`（换脸基准测试先关闭以观察底模真实表现），按需开启 `"codeformer"` 或 `"gfpgan_1.4"`。
    - `enhancer_blend`：默认 `50`（推荐维持在 `40–60` 区间，避免五官塑料感与假皮感）。
  - **显存互斥调度**：在 `server/studio.py` 启动换脸任务前，若 ComfyUI 已加载模型，先调用 `POST /free` (`{"unload_models": true, "free_memory": true}`) 释放显存。
- **本地桌面精修升级边界（`VisoMaster-Fusion`）**：
  - 保持清晰解耦（不导出不兼容的遮罩或色彩参数），在换脸结果卡片提供一键下载原素材与初筛结果入口，供复杂遮挡（手挡脸、刘海、眼镜）镜头在本地 `VisoMaster-Fusion` GUI 手工画 XSeg 遮罩精修。
- **阶段二预留（`DreamID-V Faster` 扩散级视频换脸切片器）**：
  - 新增 `server/dreamid_pipeline.py`：针对 `wan_swapface.py` 单次仅读取前 `frame_num=81` 帧的限制，由外层 FFmpeg 自动按 `≤81` 帧切片、逐段调用 `wan_swapface.py` 并在结尾无损拼接视频与合并原音轨。

## 3. 验收标准

1. `station/patch_facefusion.py` 对 `content_analyser.py` 与 `core.py` 的双补丁逻辑通过单元测试校验。
2. `server/tests/` 全部单元测试通过（包括工作流构建、换脸参数校验、81 帧切片规划、i18n 完整性、API 与队列调度）。
3. `server/web` 前端 TypeScript 编译与 Vite 打包通过（产物体积显著下降，包含 PWA `manifest.webmanifest` 与 `sw.js`）。
4. `mcp` TypeScript 编译通过，暴露 `generate_image`、`generate_video`、`swap_face` 工具。
5. 部署至 `fn` (`192.168.31.201:18104`) 替换原 `colab-comfy-gateway` 容器，实测 HTTP API、PWA 清单与前端静态页面正常响应。

## 4. 进度记录

- [x] Fork 并克隆 `ump45nose/colab-studio` 至 `/Users/sm5145/WorkSpace/Code/github/Others/colab-studio`，建立 `.worktree/feat-lite-pwa-faceswap`。
- [x] 完成上游全量代码审计与架构梳理。
- [x] 完成 `station/` 轻量化模型目录、FaceFusion 双补丁脚本与运行器改造。
- [x] 完成 `server/` 多工作流、FaceSwap 调度、DreamID-V 81 帧切片器与 API 改造。
- [x] 完成 `server/web/` 轻量化、中文界面、PWA 与换脸交互改造。
- [x] 完成 `mcp/` 工具同步更新。
- [x] 完成本地全量测试（75 项 pytest + ruff + Web PWA 打包 + MCP 打包）。
- [ ] 完成 `fn:18104` 容器部署验证。
