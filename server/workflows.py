"""ComfyUI API workflow builders for Colab Studio (`image` and `video` modes).

Supports multiple model profiles per mode:
- `image`:
  - `krea2_noct` (default): Krea2-Noct / Noct-Q V4 (text-to-image + multi-reference image edit)
  - `z_image_turbo_nsfw`: Z-Image-Turbo NSFW BF16 (8-step fast text-to-image)
- `video`:
  - `minimax_h3` (default): MiniMax-H3 (text-to-video / first-last frame image-to-video with audio)
  - `wan22_remix`: Wan2.2-Remix A14B High/Low Noise dual-stage FP8 (image-to-video / text-to-video)

Model filenames are read from `station/models.default.toml` (or user `models.toml`) via `station.catalog`.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from station import catalog  # noqa: E402

IMG = catalog.file_names("image")
IMG_TURBO = catalog.file_names("image_turbo")
VID = catalog.file_names("video")
VID_WAN22 = catalog.file_names("video_wan22")

IMAGE_PROFILES = ("krea2_noct", "z_image_turbo_nsfw")
VIDEO_PROFILES = ("minimax_h3", "wan22_remix")

RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "21:9": (21, 9),
}

IMAGE_SIZES: dict[str, int] = {
    "1024": 1024 * 1024,
    "1536": 1536 * 1536,
    "2048": 2048 * 2048,
}
EDIT_RESOLUTIONS = (1080, 1440, 2160)
SAMPLERS = ("euler", "euler_ancestral", "res_multistep", "dpmpp_2m", "dpmpp_2m_sde", "er_sde", "uni_pc")
SCHEDULERS = ("simple", "beta", "normal", "karras", "sgm_uniform")

VIDEO_RESOLUTIONS: dict[str, dict[str, tuple[int, int]]] = {
    "480p": {
        "16:9": (832, 480),
        "9:16": (480, 832),
        "1:1": (640, 640),
        "4:3": (736, 544),
        "3:4": (544, 736),
    },
    "768p": {
        "16:9": (1376, 768),
        "9:16": (768, 1376),
        "1:1": (1024, 1024),
        "4:3": (1216, 896),
        "3:4": (896, 1216),
    },
}


def resolve_dims(ratio: str = "1:1", size: str = "1536") -> tuple[int, int]:
    rw, rh = RATIOS.get(ratio, (1, 1))
    area = IMAGE_SIZES.get(size, IMAGE_SIZES["1536"])
    h = math.sqrt(area * rh / rw)
    w = h * rw / rh
    return max(512, round(w / 32) * 32), max(512, round(h / 32) * 32)


def _node(class_type: str, title: str, **inputs) -> dict:
    return {"class_type": class_type, "inputs": inputs, "_meta": {"title": title}}


def _image_z_turbo(
    prompt: str,
    *,
    ratio: str = "1:1",
    size: str = "1536",
    steps: int = 8,
    cfg: float = 1.0,
    sampler: str = "res_multistep",
    scheduler: str = "simple",
    negative: str = "",
    seed: int = 0,
) -> dict[str, dict]:
    w, h = resolve_dims(ratio, size)
    wf: dict[str, dict] = {
        "1": _node("UNETLoader", "正在加载模型", unet_name=IMG_TURBO["diffusion"], weight_dtype="default"),
        "2": _node("CLIPLoader", "正在加载模型", clip_name=IMG_TURBO["encoder"], type="lumina2"),
        "3": _node("VAELoader", "正在加载模型", vae_name=IMG_TURBO["vae"]),
        "4": _node("CLIPTextEncode", "正在编码提示词", text=prompt, clip=["2", 0]),
        "6": _node("EmptySD3LatentImage", "正在准备画布", width=w, height=h, batch_size=1),
        "7": _node("ModelSamplingAuraFlow", "正在加载模型", model=["1", 0], shift=3.0),
        "9": _node("VAEDecode", "正在保存", samples=["8", 0], vae=["3", 0]),
        "10": _node("SaveImage", "正在保存", images=["9", 0], filename_prefix="studio_img"),
    }
    if cfg > 1.0 and negative.strip():
        wf["5"] = _node("CLIPTextEncode", "正在编码提示词", text=negative, clip=["2", 0])
    else:
        wf["5"] = _node("ConditioningZeroOut", "正在编码提示词", conditioning=["4", 0])

    wf["8"] = _node(
        "KSampler",
        "正在生成",
        model=["7", 0],
        seed=seed,
        steps=steps,
        cfg=cfg,
        sampler_name=sampler,
        scheduler=scheduler,
        positive=["4", 0],
        negative=["5", 0],
        latent_image=["6", 0],
        denoise=1.0,
    )
    return wf


def image_generate(
    prompt: str,
    *,
    profile: str = "krea2_noct",
    ratio: str = "1:1",
    size: str = "1536",
    edit_resolution: int = 1080,
    steps: int = 25,
    cfg: float = 3.0,
    sampler: str = "euler",
    scheduler: str = "simple",
    turbo: bool = False,
    negative: str = "",
    seed: int | None = None,
    images: list[str] | None = None,
) -> dict[str, dict]:
    """Build text-to-image or multi-reference image-edit workflow."""
    seed = seed if seed is not None else random.randint(1, 2**32 - 1)
    refs = list(images or [])

    if profile == "z_image_turbo_nsfw" and not refs:
        return _image_z_turbo(
            prompt,
            ratio=ratio,
            size=size,
            steps=steps,
            cfg=cfg,
            sampler=sampler,
            scheduler=scheduler,
            negative=negative,
            seed=seed,
        )

    wf: dict[str, dict] = {
        "1": _node("UNETLoader", "正在加载模型", unet_name=IMG["diffusion"], weight_dtype="default"),
        "2": _node("CLIPLoader", "正在加载模型", clip_name=IMG["encoder"], type="krea2"),
        "3": _node("VAELoader", "正在加载模型", vae_name=IMG["vae"]),
        "7": _node("VAEDecode", "正在保存", samples=["6", 0], vae=["3", 0]),
        "8": _node("SaveImage", "正在保存", images=["7", 0], filename_prefix="studio_img"),
    }
    unet_out = ["1", 0]
    if turbo:
        wf["10"] = _node("LoraLoaderModelOnly", "正在加载模型", model=unet_out, lora_name=IMG["turbo_lora"], strength_model=1.0)
        unet_out = ["10", 0]
    wf["4"] = _node("ModelSamplingSD3", "正在加载模型", model=unet_out, shift=3.0)

    if refs:
        wf["9"] = _node("QwenImage21Cache", "正在读取参考图", model=["4", 0], device="gpu", dtype="bf16")
        model_ref = ["9", 0]
        load_ids: list[list] = []
        for idx, name in enumerate(refs[:10]):
            nid = str(20 + idx)
            wf[nid] = _node("LoadImage", "正在读取参考图", image=name)
            load_ids.append([nid, 0])
        if len(load_ids) == 1:
            img_ref = load_ids[0]
        else:
            wf["30"] = _node("BatchImagesNode", "正在读取参考图", images=load_ids)
            img_ref = ["30", 0]
        wf["5"] = _node(
            "TextEncodeQwenImage21",
            "正在编码提示词",
            clip=["2", 0],
            vae=["3", 0],
            images=img_ref,
            prompt=prompt,
            negative_prompt=negative,
            resolution=edit_resolution,
        )
        latent_ref = ["5", 2]
    else:
        w, h = resolve_dims(ratio, size)
        model_ref = ["4", 0]
        wf["5"] = _node(
            "TextEncodeQwenImage21",
            "正在编码提示词",
            clip=["2", 0],
            prompt=prompt,
            negative_prompt=negative,
            resolution=1080,
        )
        wf["9"] = _node("EmptyLatentImage", "正在准备画布", width=w, height=h, batch_size=1)
        latent_ref = ["9", 0]

    wf["6"] = _node(
        "KSampler",
        "正在生成",
        model=model_ref,
        seed=seed,
        steps=steps,
        cfg=cfg,
        sampler_name=sampler,
        scheduler=scheduler,
        positive=["5", 0],
        negative=["5", 1],
        latent_image=latent_ref,
        denoise=1.0,
    )
    return wf


def _video_wan22_remix(
    prompt: str,
    *,
    ratio: str = "16:9",
    resolution: str = "480p",
    seconds: int = 5,
    quality: str = "turbo",
    seed: int = 0,
    first_frame: str | None = None,
) -> dict[str, dict]:
    res_map = VIDEO_RESOLUTIONS.get(resolution, VIDEO_RESOLUTIONS["480p"])
    w, h = res_map.get(ratio, (832, 480))
    fps = 16
    frames = max(17, round((seconds * fps - 1) / 4) * 4 + 1)
    total_steps = 8 if quality == "turbo" else 20
    split_step = max(2, total_steps // 2)
    cfg = 3.5 if quality != "turbo" else 2.0
    neg_text = "色调艳丽，过曝，静态，细节模糊不清，字幕，最差质量，低质量，残缺，多余的手指，画面静止"

    wf: dict[str, dict] = {
        "1": _node("UNETLoader", "正在加载模型", unet_name=VID_WAN22["high_noise"], weight_dtype="fp8_e4m3fn"),
        "2": _node("UNETLoader", "正在加载模型", unet_name=VID_WAN22["low_noise"], weight_dtype="fp8_e4m3fn"),
        "3": _node("CLIPLoader", "正在加载模型", clip_name=VID_WAN22["encoder"], type="wan"),
        "4": _node("VAELoader", "正在加载模型", vae_name=VID_WAN22["vae"]),
        "5": _node("CLIPTextEncode", "正在编码提示词", text=prompt, clip=["3", 0]),
        "6": _node("CLIPTextEncode", "正在编码提示词", text=neg_text, clip=["3", 0]),
        "8": _node("ModelSamplingSD3", "正在加载模型", model=["1", 0], shift=5.0),
        "9": _node("ModelSamplingSD3", "正在加载模型", model=["2", 0], shift=5.0),
    }

    i2v_inputs: dict = {
        "positive": ["5", 0],
        "negative": ["6", 0],
        "vae": ["4", 0],
        "width": w,
        "height": h,
        "length": frames,
        "batch_size": 1,
    }
    if first_frame:
        wf["20"] = _node("LoadImage", "正在读取参考图", image=first_frame)
        i2v_inputs["start_image"] = ["20", 0]
    wf["7"] = _node("WanImageToVideo", "正在准备画布", **i2v_inputs)

    wf["10"] = _node(
        "KSamplerAdvanced",
        "正在生成（高噪阶段）",
        model=["8", 0],
        add_noise="enable",
        noise_seed=seed,
        steps=total_steps,
        cfg=cfg,
        sampler_name="euler",
        scheduler="simple",
        positive=["7", 0],
        negative=["7", 1],
        latent_image=["7", 2],
        start_at_step=0,
        end_at_step=split_step,
        return_with_leftover_noise="enable",
    )
    wf["11"] = _node(
        "KSamplerAdvanced",
        "正在生成（低噪阶段）",
        model=["9", 0],
        add_noise="disable",
        noise_seed=seed,
        steps=total_steps,
        cfg=1.0,
        sampler_name="euler",
        scheduler="simple",
        positive=["7", 0],
        negative=["7", 1],
        latent_image=["10", 0],
        start_at_step=split_step,
        end_at_step=10000,
        return_with_leftover_noise="disable",
    )
    wf["12"] = _node("VAEDecode", "正在保存", samples=["11", 0], vae=["4", 0])
    wf["13"] = _node("CreateVideo", "正在保存", images=["12", 0], fps=fps)
    wf["14"] = _node("SaveVideo", "正在保存", video=["13", 0], filename_prefix="studio_vid", format="mp4", codec="h264")
    return wf


def video_generate(
    prompt: str,
    *,
    profile: str = "minimax_h3",
    ratio: str = "16:9",
    resolution: str = "480p",
    seconds: int = 5,
    quality: str = "turbo",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
) -> dict[str, dict]:
    """Build video workflow (`minimax_h3` or `wan22_remix`)."""
    seed = seed if seed is not None else random.randint(1, 2**32 - 1)
    if profile == "wan22_remix":
        return _video_wan22_remix(
            prompt,
            ratio=ratio,
            resolution=resolution,
            seconds=seconds,
            quality=quality,
            seed=seed,
            first_frame=first_frame,
        )

    res_map = VIDEO_RESOLUTIONS.get(resolution, VIDEO_RESOLUTIONS["480p"])
    w, h = res_map.get(ratio, (832, 480))
    frames = max(21, round((seconds * 24 - 4) / 17) * 17 + 4)
    turbo = quality == "turbo"

    wf: dict[str, dict] = {
        "1": _node("UNETLoader", "正在加载模型", unet_name=VID["diffusion"], weight_dtype="default"),
        "2": _node("CLIPLoader", "正在加载模型", clip_name=VID["encoder"], type="minimax"),
        "3": _node("VAELoader", "正在加载模型", vae_name=VID["video_vae"]),
        "4": _node("VAELoader", "正在加载模型", vae_name=VID["audio_vae"]),
    }

    i2v_inputs: dict = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "width": w,
        "height": h,
        "length": frames,
        "prompt": prompt,
    }
    if first_frame:
        wf["20"] = _node("LoadImage", "正在读取参考图", image=first_frame)
        i2v_inputs["first_frame"] = ["20", 0]
    if last_frame:
        wf["21"] = _node("LoadImage", "正在读取参考图", image=last_frame)
        i2v_inputs["last_frame"] = ["21", 0]
    wf["5"] = _node("MiniMaxH3ImageToVideo", "正在编码提示词", **i2v_inputs)

    if turbo:
        wf["6"] = _node("LoraLoaderModelOnly", "正在加载模型", model=["1", 0], lora_name=VID["turbo_lora"], strength_model=1.0)
        wf["7"] = _node("ModelSamplingSD3", "正在加载模型", model=["6", 0], shift=3.0)
        model_out, steps = ["7", 0], 8
    else:
        wf["6"] = _node("CFGOverride", "正在加载模型", model=["1", 0], cfg=3.5, start_percent=0.0, end_percent=0.75)
        wf["7"] = _node("RescaleCFG", "正在加载模型", model=["6", 0], multiplier=0.7)
        wf["8"] = _node("ModelSamplingSD3", "正在加载模型", model=["7", 0], shift=5.0)
        model_out, steps = ["8", 0], 20

    wf["9"] = _node("BasicGuider", "正在生成", model=model_out, conditioning=["5", 0])
    wf["10"] = _node("KSamplerSelect", "正在生成", sampler_name="euler")
    wf["11"] = _node("BasicScheduler", "正在生成", model=model_out, scheduler="simple", steps=steps, denoise=1.0)
    wf["12"] = _node("RandomNoise", "正在生成", noise_seed=seed)
    wf["13"] = _node(
        "SamplerCustomAdvanced",
        "正在生成",
        noise=["12", 0],
        guider=["9", 0],
        sampler=["10", 0],
        sigmas=["11", 0],
        latent_image=["5", 1],
    )
    wf["14"] = _node("VAEDecode", "正在保存", samples=["13", 0], vae=["3", 0])
    wf["15"] = _node("VAEDecodeAudio", "正在解码音频", samples=["13", 0], vae=["4", 0])
    wf["16"] = _node("CreateVideo", "正在保存", images=["14", 0], audio=["15", 0], fps=24)
    wf["17"] = _node("SaveVideo", "正在保存", video=["16", 0], filename_prefix="studio_vid", format="mp4", codec="h264")
    return wf
