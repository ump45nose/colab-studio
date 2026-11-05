"""Colab Studio FastAPI server: REST API + PWA static hosting."""
from __future__ import annotations

import asyncio
import math
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from station import faceswap_runner
from . import config, studio, tracker, workflows
from .runtime import runtime

WEB_DIST = Path(__file__).parent / "web" / "dist"

MODES = {"image", "video", "faceswap"}
FACESWAP_ENGINES = ("facefusion_cli", "dreamid_v_faster")
UPLOAD_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}


def _bad(msg: str) -> HTTPException:
    return HTTPException(400, msg)


def _check_keys(d: dict, allowed: set[str]) -> None:
    extra = set(d) - allowed
    if extra:
        raise _bad(f"未知设置项: {sorted(extra)[0]}")


def _num(val, label: str, lo: float, hi: float, integer: bool = False):
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        raise _bad(f"{label} 必须是数字")
    if integer and not (isinstance(val, int) or float(val).is_integer()):
        raise _bad(f"{label} 必须是 {int(lo)}-{int(hi)} 之间的整数")
    v = int(val) if integer else float(val)
    if not (lo <= v <= hi):
        raise _bad(f"{label} 必须在 {lo}-{hi} 之间")
    return v


def _seed(val) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool) or not isinstance(val, int) or not (0 <= val < 2**32):
        raise _bad("seed 必须是 0 到 2^32 之间的整数")
    return val or None


def _image_params(p: dict, n_inputs: int) -> dict:
    _check_keys(
        p,
        {
            "profile",
            "ratio",
            "size",
            "edit_resolution",
            "steps",
            "cfg",
            "sampler",
            "scheduler",
            "turbo",
            "negative",
            "count",
            "seed",
        },
    )
    profile = p.get("profile", "krea2_noct")
    if profile not in workflows.IMAGE_PROFILES:
        raise _bad(f"无效的图片工作流: {profile}")
    ratio = p.get("ratio", "1:1")
    if ratio not in workflows.RATIOS:
        raise _bad(f"无效的宽高比: {ratio}")
    size = str(p.get("size", "1536"))
    if size not in workflows.IMAGE_SIZES:
        raise _bad(f"无效的尺寸: {size}")
    edit_res = p.get("edit_resolution", 1080)
    if edit_res not in workflows.EDIT_RESOLUTIONS:
        raise _bad(f"无效的编辑分辨率: {edit_res}")
    sampler = p.get("sampler", "euler")
    if sampler not in workflows.SAMPLERS:
        raise _bad(f"无效的采样器 (sampler): {sampler}")
    scheduler = p.get("scheduler", "simple")
    if scheduler not in workflows.SCHEDULERS:
        raise _bad(f"无效的调度器 (scheduler): {scheduler}")
    steps = _num(p.get("steps", 25), "步数", 4, 50, integer=True)
    cfg = _num(p.get("cfg", 3.0), "CFG", 1.0, 10.0)
    count = _num(p.get("count", 1), "张数", 1, 4, integer=True)
    turbo = bool(p.get("turbo", False))
    if n_inputs > 0 and edit_res == 2160 and cfg > 1.0 and steps >= 20:
        raise _bad(
            "2160p 编辑在 CFG > 1 时耗时约 33 分钟，超出 30 分钟上限；请选择 Turbo (CFG 1) 或降低分辨率"
        )
    return {
        "profile": profile,
        "ratio": ratio,
        "size": size,
        "edit_resolution": edit_res,
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "turbo": turbo,
        "negative": str(p.get("negative", ""))[:2000],
        "count": count,
        "seed": _seed(p.get("seed")),
    }


def _video_params(p: dict) -> dict:
    _check_keys(p, {"profile", "ratio", "resolution", "seconds", "quality", "seed"})
    profile = p.get("profile", "minimax_h3")
    if profile not in workflows.VIDEO_PROFILES:
        raise _bad(f"无效的视频工作流: {profile}")
    res = p.get("resolution", "480p")
    if res not in workflows.VIDEO_RESOLUTIONS:
        raise _bad(f"无效的分辨率: {res}")
    ratio = p.get("ratio", "16:9")
    if ratio not in workflows.VIDEO_RESOLUTIONS[res]:
        raise _bad(f"无效的宽高比: {ratio}")
    quality = p.get("quality", "turbo")
    if quality not in ("turbo", "quality"):
        raise _bad(f"无效的画质档位: {quality}")
    seconds = _num(p.get("seconds", 5), "时长（秒）", 2, 10, integer=True)
    if res == "768p" and quality == "quality" and seconds > 8:
        raise _bad(
            "768p 高画质视频超过 8 秒会超出 30 分钟上限；请选择 Turbo 或将时长缩短至 8 秒以内"
        )
    return {
        "profile": profile,
        "ratio": ratio,
        "resolution": res,
        "seconds": seconds,
        "quality": quality,
        "seed": _seed(p.get("seed")),
    }


def _faceswap_params(p: dict) -> dict:
    _check_keys(
        p,
        {
            "engine",
            "swapper_model",
            "compare_all",
            "pixel_boost",
            "enhancer_model",
            "enhancer_blend",
        },
    )
    engine = p.get("engine", "facefusion_cli")
    if engine not in FACESWAP_ENGINES:
        raise _bad(f"未知换脸引擎: {engine}")
    swapper_model = p.get("swapper_model", "hyperswap_1a_256")
    if swapper_model not in faceswap_runner.BENCHMARK_SWAPPER_MODELS:
        raise _bad(f"无效的换脸底模: {swapper_model}")
    compare_all = bool(p.get("compare_all", False))
    pixel_boost = p.get("pixel_boost", "256x256")
    if pixel_boost not in faceswap_runner.VALID_PIXEL_BOOSTS:
        raise _bad(f"无效的超分像素倍率: {pixel_boost}")
    enhancer_model = p.get("enhancer_model", "none")
    if enhancer_model not in faceswap_runner.VALID_ENHANCERS:
        raise _bad(f"无效的后处理增强模型: {enhancer_model}")
    enhancer_blend = _num(p.get("enhancer_blend", 50), "增强混合比", 0, 100, integer=True)
    return {
        "engine": engine,
        "swapper_model": swapper_model,
        "compare_all": compare_all,
        "pixel_boost": pixel_boost,
        "enhancer_model": enhancer_model,
        "enhancer_blend": enhancer_blend,
    }


def _validate_params(kind: str, raw) -> dict:
    if not isinstance(raw, dict):
        raise _bad("params 必须是一个对象")
    return {
        "image": lambda p: _image_params(p, 0),
        "video": _video_params,
        "faceswap": _faceswap_params,
    }[kind](raw)


async def _json_object(req: Request) -> dict:
    try:
        body = await req.json()
    except Exception as e:
        raise _bad("无效的 JSON") from e
    if not isinstance(body, dict):
        raise _bad("请求体必须是一个 JSON 对象")
    return body


@asynccontextmanager
async def lifespan(_: FastAPI):
    studio.load_state()
    w1 = asyncio.create_task(studio.worker_loop())
    w2 = asyncio.create_task(runtime.watchdog_loop())
    try:
        yield
    finally:
        w1.cancel()
        w2.cancel()
        await runtime.disconnect_on_shutdown()


app = FastAPI(title="Colab Studio", lifespan=lifespan)


class _SameOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, req: Request, call_next):
        if req.method in ("POST", "PUT", "PATCH", "DELETE") and req.url.path.startswith("/api/"):
            origin = req.headers.get("origin")
            host = req.headers.get("host")
            if origin and host and urlparse(origin).netloc != host:
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
        return await call_next(req)


app.add_middleware(_SameOriginMiddleware)


@app.get("/api/state")
async def get_state():
    return {
        "runtime": runtime.status(),
        "chats": sorted(studio.chats.values(), key=lambda c: c["updated_at"], reverse=True),
        "jobs": sorted(studio.jobs.values(), key=lambda j: j["created_at"]),
        "presets": studio.presets,
        "estimates": tracker.get_estimates(),
        "startup_estimates": tracker.get_startup_estimates(),
    }


@app.put("/api/presets/{mode}")
async def save_preset(mode: str, req: Request):
    if mode not in MODES:
        raise _bad(f"无效的模式: {mode}")
    body = await _json_object(req)
    name = str(body.get("name", "")).strip()[:40]
    if not name:
        raise _bad("预设名称不能为空")
    params = _validate_params(mode, body.get("params") or {})
    studio.presets.setdefault(mode, {})[name] = params
    studio.save_state()
    return studio.presets.get(mode, {})


@app.delete("/api/presets/{mode}/{name}")
async def delete_preset(mode: str, name: str):
    if mode in studio.presets:
        studio.presets[mode].pop(name, None)
        studio.save_state()
    return studio.presets.get(mode, {})


@app.post("/api/runtime/start")
async def start_runtime():
    if runtime.state not in ("starting", "ready"):
        asyncio.create_task(runtime.ensure_ready())
    return runtime.status()


@app.post("/api/runtime/stop")
async def stop_runtime():
    for jid, j in list(studio.jobs.items()):
        if j.get("status") in ("queued", "running"):
            await studio.cancel_job(jid)
    asyncio.create_task(runtime.stop("手动关闭"))
    return runtime.status()


@app.get("/api/usage")
async def get_usage():
    try:
        raw = await runtime.fetch_usage()
        return tracker.record_usage(raw, config.GPU_TIER, runtime.state == "ready")
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/chats")
async def new_chat(req: Request):
    body = await _json_object(req)
    mode = body.get("mode", "image")
    if mode not in MODES:
        raise _bad(f"无效的模式: {mode}")
    return studio.create_chat(mode=mode, title=str(body.get("title", ""))[:80])


@app.delete("/api/chats/{cid}")
async def remove_chat(cid: str):
    if not studio.delete_chat(cid):
        raise HTTPException(404, "未找到该对话")
    return {"ok": True}


@app.post("/api/jobs")
async def create_job(req: Request):
    body = await _json_object(req)
    kind = body.get("kind", "image")
    if kind not in MODES:
        raise _bad(f"未知任务类型: {kind}")

    prompt = str(body.get("prompt", "")).strip()
    if kind in ("image", "video") and not prompt:
        raise _bad("提示词不能为空")

    raw_inputs = body.get("inputs") or []
    if not isinstance(raw_inputs, list) or not all(isinstance(x, str) for x in raw_inputs):
        raise _bad("inputs 必须是文件名列表")
    inputs: list[str] = []
    for f in raw_inputs:
        name = Path(f).name
        if not name or not (studio.MEDIA_DIR / name).is_file():
            raise _bad(f"未找到上传的文件: {f}")
        inputs.append(name)

    if kind == "image" and len(inputs) > 10:
        raise _bad("最多支持 10 张参考图片")
    if kind == "video" and len(inputs) > 2:
        raise _bad("视频最多支持 2 张参考图（首帧与尾帧）")
    if kind == "faceswap":
        if len(inputs) < 2:
            raise _bad("换脸至少需要添加 2 个文件（第 1 个为源人脸图，最后 1 个为目标图片或视频）")
        if len(inputs) > 10:
            raise _bad("换脸最多支持 9 张源人脸图 + 1 个目标文件")

    raw_params = body.get("params") or {}
    if not isinstance(raw_params, dict):
        raise _bad("params 必须是一个对象")
    params = _image_params(raw_params, len(inputs)) if kind == "image" else _validate_params(kind, raw_params)

    if kind == "faceswap" and not prompt:
        if params.get("compare_all"):
            prompt = "全底模同管道对比 (HyperSwap / AlphaFace / InSwapper)"
        elif params.get("engine") == "dreamid_v_faster":
            prompt = "DreamID-V Faster 81帧切片换脸"
        else:
            prompt = f"换脸 · {faceswap_runner.MODEL_LABELS.get(params['swapper_model'], params['swapper_model'])}"

    cid = body.get("chat_id")
    if not cid or cid not in studio.chats:
        cid = studio.create_chat(mode=kind, title=prompt[:48])["id"]
    return studio.enqueue(cid, kind, prompt, params, inputs)


@app.post("/api/jobs/{jid}/cancel")
async def cancel(jid: str):
    j = await studio.cancel_job(jid)
    if not j:
        raise HTTPException(404, "未找到该任务")
    return j


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ct = (file.content_type or "").lower()
    ext = Path(file.filename or "").suffix.lower()
    if ct in UPLOAD_TYPES:
        ext = ext if ext in UPLOAD_TYPES.values() else UPLOAD_TYPES[ct]
    elif ext not in UPLOAD_TYPES.values():
        raise _bad("仅支持上传图片 (PNG, JPEG, WebP) 或目标视频 (MP4, WebM, MOV)")
    name = f"up_{uuid.uuid4().hex[:10]}{ext}"
    dest = studio.MEDIA_DIR / name
    studio.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(413, "文件过大（上限 200 MB）")
    dest.write_bytes(data)
    kind = "video" if ext in (".mp4", ".webm", ".mov") else "image"
    return {"file": name, "url": f"/media/{name}", "kind": kind}


@app.get("/media/{name}")
async def get_media(name: str):
    safe = Path(name).name
    p = studio.MEDIA_DIR / safe
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/manifest.webmanifest")
async def pwa_manifest():
    p = WEB_DIST / "manifest.webmanifest"
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/manifest+json")


@app.get("/sw.js")
async def pwa_sw():
    p = WEB_DIST / "sw.js"
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/icon.svg")
async def pwa_icon():
    p = WEB_DIST / "icon.svg"
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/svg+xml")


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
