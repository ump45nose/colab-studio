"""Job queue, persistent state (`chats` + `jobs`), ComfyUI WebSocket runner, and FaceSwap pipeline."""
from __future__ import annotations

import asyncio
import json
import os
import random
import shlex
import time
import uuid
from pathlib import Path

import httpx
import websockets

from station import faceswap_runner
from . import config, dreamid_pipeline, tracker, workflows
from .runtime import PACK_LABELS, runtime

STATE_FILE = config.DATA_DIR / "state.json"
MEDIA_DIR = config.DATA_DIR / "media"
JOB_TIMEOUT = 30 * 60

chats: dict[str, dict] = {}
jobs: dict[str, dict] = {}
presets: dict[str, dict] = {}
_queue: asyncio.Queue[str] = asyncio.Queue()
_running_tasks: dict[str, asyncio.Task] = {}
_comfy_prompt_ids: dict[str, str] = {}


def load_state() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text())
        chats.update(data.get("chats", {}))
        jobs.update(data.get("jobs", {}))
        presets.update(data.get("presets", {}))
        for j in jobs.values():
            if j.get("status") in ("queued", "running"):
                j["status"] = "error"
                j["error"] = "服务已重启，未完成的任务已终止"
    except Exception as e:
        print(f"[state] 状态读取失败: {e}")


def save_state() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    payload = json.dumps({"chats": chats, "jobs": jobs, "presets": presets}, ensure_ascii=False, indent=2)
    tmp.write_text(payload)
    os.replace(tmp, STATE_FILE)


def create_chat(mode: str = "image", title: str = "") -> dict:
    cid = uuid.uuid4().hex[:10]
    chat = {
        "id": cid,
        "mode": mode,
        "title": title or "新对话",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    chats[cid] = chat
    save_state()
    return chat


def delete_chat(cid: str) -> bool:
    if cid not in chats:
        return False
    dead_jids = [jid for jid, j in jobs.items() if j.get("chat_id") == cid]
    still_used: set[str] = set()
    for _jid, j in jobs.items():
        if j.get("chat_id") != cid:
            still_used.update(j.get("inputs") or [])
            still_used.update(o.get("file", "") for o in (j.get("outputs") or []))
    for jid in dead_jids:
        j = jobs.pop(jid, {})
        for f in [*(j.get("inputs") or []), *(o.get("file", "") for o in (j.get("outputs") or []))]:
            if f and f not in still_used:
                (MEDIA_DIR / Path(f).name).unlink(missing_ok=True)
    del chats[cid]
    save_state()
    return True


def enqueue(chat_id: str | None, kind: str, prompt: str, params: dict, inputs: list[str] | None = None) -> dict:
    jid = uuid.uuid4().hex[:10]
    now = time.time()
    job = {
        "id": jid,
        "chat_id": chat_id,
        "kind": kind,
        "prompt": prompt,
        "params": params,
        "inputs": inputs or [],
        "status": "queued",
        "stage": "排队中",
        "progress": 0,
        "outputs": [],
        "error": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
    }
    jobs[jid] = job
    if chat_id and chat_id in chats:
        c = chats[chat_id]
        c["updated_at"] = now
        if c["title"] in ("新对话", "Yeni sohbet") and prompt.strip():
            c["title"] = prompt.strip()[:48]
    save_state()
    _queue.put_nowait(jid)
    return job


def _update(jid: str, **fields) -> None:
    if jid in jobs:
        jobs[jid].update(fields)
        save_state()


async def cancel_job(jid: str) -> dict | None:
    j = jobs.get(jid)
    if not j:
        return None
    if j["status"] == "queued":
        _update(jid, status="cancelled", stage=None, error="已取消", finished_at=time.time())
        return jobs[jid]
    if j["status"] == "running":
        _update(jid, status="cancelled", stage=None, error="已取消", finished_at=time.time())
        task = _running_tasks.get(jid)
        if task:
            task.cancel()
        if runtime.state == "ready":
            try:
                async with httpx.AsyncClient(timeout=5) as http:
                    pid = _comfy_prompt_ids.get(jid)
                    if pid:
                        await http.post(f"{runtime.COMFY_URL}/queue", json={"delete": [pid]})
                    await http.post(f"{runtime.COMFY_URL}/interrupt")
            except Exception:
                pass
        elif runtime.state == "starting":
            other_active = any(
                o["id"] != jid and o["status"] in ("queued", "running")
                for o in jobs.values()
            )
            if not other_active:
                asyncio.create_task(runtime.stop("任务已取消，正在关闭 GPU"))
    return jobs[jid]


# --- Worker loop -----------------------------------------------------------

STAGES: dict[str, list[str]] = {
    "image": ["正在加载模型", "正在读取参考图", "正在编码提示词", "正在准备画布", "正在生成", "正在保存"],
    "video": [
        "正在加载模型",
        "正在读取参考图",
        "正在编码提示词",
        "正在准备画布",
        "正在生成",
        "正在生成（高噪阶段）",
        "正在生成（低噪阶段）",
        "正在解码音频",
        "正在保存",
    ],
    "faceswap": ["正在释放显存与上传素材", "正在执行换脸流水线", "正在回传换脸结果"],
}


def _pack_for_job(job: dict) -> str | None:
    """Resolve which station model pack (`image`, `image_turbo`, `video`, `video_wan22`, or `None`) a job needs."""
    kind = job["kind"]
    params = job.get("params") or {}
    if kind == "faceswap":
        return None
    if kind == "image":
        if params.get("profile") == "z_image_turbo_nsfw" and not job.get("inputs"):
            return "image_turbo"
        return "image"
    if kind == "video":
        if params.get("profile") == "wan22_remix":
            return "video_wan22"
        return "video"
    return None


async def worker_loop() -> None:
    while True:
        jid = await _queue.get()
        job = jobs.get(jid)
        if not job or job["status"] != "queued":
            continue
        task = asyncio.create_task(_work(jid))
        _running_tasks[jid] = task
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            _running_tasks.pop(jid, None)
            _comfy_prompt_ids.pop(jid, None)


async def _work(jid: str) -> None:
    job = jobs[jid]
    runtime.active_jobs += 1
    try:
        _update(jid, status="running", stage=runtime.step if runtime.state != "ready" else "正在准备", started_at=time.time())
        try:
            await runtime.ensure_ready()
        except Exception as e:
            if jobs[jid]["status"] != "cancelled":
                _update(jid, status="error", stage=None, error=f"GPU 启动失败: {e}", finished_at=time.time())
            return

        pack = _pack_for_job(job)
        if pack is not None:
            label = PACK_LABELS.get(pack, pack)

            def _pack_progress(p: dict) -> None:
                done = p.get("done_gb", 0)
                tot = p.get("total_gb") or 1
                pct = min(99, int(done * 100 / tot))
                cur = p.get("current")
                if p.get("writing"):
                    txt = f"正在将 {label} 模型写入磁盘 · {done}/{tot} GB"
                elif cur:
                    txt = f"正在下载 {label} 模型 · {cur} ({done}/{tot} GB)"
                else:
                    txt = f"正在准备 {label} 模型"
                _update(jid, stage=txt, progress=pct)

            await runtime.ensure_models(pack, on_progress=_pack_progress)

        await asyncio.wait_for(_run(job), timeout=JOB_TIMEOUT)
    except asyncio.TimeoutError:
        if jobs[jid]["status"] != "cancelled":
            _update(
                jid,
                status="error",
                stage=None,
                error=f"执行超时：任务超过 {JOB_TIMEOUT // 60} 分钟未完成，已自动中止",
                finished_at=time.time(),
            )
    except asyncio.CancelledError:
        if jobs[jid]["status"] != "cancelled":
            _update(jid, status="cancelled", stage=None, error="已取消", finished_at=time.time())
        raise
    except Exception as e:
        if jobs[jid]["status"] != "cancelled":
            _update(jid, status="error", stage=None, error=str(e), finished_at=time.time())
    finally:
        runtime.active_jobs = max(0, runtime.active_jobs - 1)
        runtime.touch()


async def _upload_to_comfy(http: httpx.AsyncClient, local_name: str) -> str:
    path = MEDIA_DIR / Path(local_name).name
    data = await asyncio.to_thread(path.read_bytes)
    r = await http.post(f"{runtime.COMFY_URL}/upload/image", files={"image": (path.name, data)})
    r.raise_for_status()
    return r.json()["name"]


async def _free_comfy_vram(http: httpx.AsyncClient) -> None:
    """Ask ComfyUI to unload models and free CUDA cache before running FaceFusion / DreamID-V."""
    if not runtime.warm:
        return
    try:
        await http.post(
            f"{runtime.COMFY_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=15,
        )
    except Exception:
        pass
    runtime.warm.clear()


async def _run_faceswap(http: httpx.AsyncClient, job: dict) -> None:
    jid = job["id"]
    p = job.get("params") or {}
    inputs = list(job.get("inputs") or [])
    if len(inputs) < 2:
        raise RuntimeError("换脸任务至少需要上传 2 个文件（前 N-1 张为源人脸图片，最后 1 个为目标图片或视频）")

    source_files = inputs[:-1]
    target_file = inputs[-1]
    engine = p.get("engine", "facefusion_cli")
    is_warm = "faceswap" in runtime.warm

    t0 = time.time()
    _update(jid, stage="正在释放显存与上传素材", stage_started_at=t0, stages=STAGES["faceswap"], warm=is_warm, progress=5)
    await _free_comfy_vram(http)

    remote_job_dir = f"/content/jobs/{jid}"
    remote_in_dir = f"{remote_job_dir}/in"
    remote_out_dir = f"{remote_job_dir}/out"
    await runtime.ssh(f"rm -rf {shlex.quote(remote_job_dir)} && mkdir -p {shlex.quote(remote_in_dir)} {shlex.quote(remote_out_dir)}")

    remote_sources: list[str] = []
    for idx, src_name in enumerate(source_files):
        local_src = MEDIA_DIR / Path(src_name).name
        remote_src = f"{remote_in_dir}/src_{idx}_{local_src.name}"
        await asyncio.to_thread(runtime.upload_file, local_src, remote_src)
        remote_sources.append(remote_src)

    local_target = MEDIA_DIR / Path(target_file).name
    remote_target = f"{remote_in_dir}/target_{local_target.name}"
    await asyncio.to_thread(runtime.upload_file, local_target, remote_target)
    tracker.record_stage("faceswap", "正在释放显存与上传素材", is_warm, time.time() - t0)

    t1 = time.time()
    _update(jid, stage="正在执行换脸流水线", stage_started_at=t1, progress=20)
    outputs: list[dict] = []

    try:
        if engine == "dreamid_v_faster":
            ext = local_target.suffix.lower() or ".mp4"
            remote_final = f"{remote_out_dir}/dreamid_v_faster{ext}"
            py_code = _build_dreamid_remote_runner(
                source_image=remote_sources[0],
                target_media=remote_target,
                work_dir=remote_job_dir,
                final_output=remote_final,
            )
            script_local = MEDIA_DIR / f".dreamid_{jid}.py"
            script_local.write_text(py_code, encoding="utf-8")
            try:
                await asyncio.to_thread(runtime.upload_file, script_local, f"{remote_job_dir}/run_dreamid.py")
            finally:
                script_local.unlink(missing_ok=True)
            await runtime.ssh(f"python3 {shlex.quote(remote_job_dir)}/run_dreamid.py", timeout=JOB_TIMEOUT)
            remote_outputs = [("dreamid_v_faster", remote_final)]
        else:
            spec = {
                "source_paths": remote_sources,
                "target_path": remote_target,
                "output_dir": remote_out_dir,
                "swapper_model": p.get("swapper_model", "hyperswap_1a_256"),
                "compare_all": bool(p.get("compare_all", False)),
                "pixel_boost": p.get("pixel_boost", "256x256"),
                "enhancer_model": p.get("enhancer_model", "none"),
                "enhancer_blend": int(p.get("enhancer_blend", 50)),
            }
            spec_local = MEDIA_DIR / f".spec_{jid}.json"
            spec_local.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            try:
                await asyncio.to_thread(runtime.upload_file, spec_local, f"{remote_job_dir}/spec.json")
            finally:
                spec_local.unlink(missing_ok=True)

            raw_out = await runtime.ssh(
                f"python3 /content/station/faceswap_runner.py {shlex.quote(remote_job_dir)}/spec.json",
                timeout=JOB_TIMEOUT,
            )
            remote_outputs = []
            for ln in raw_out.splitlines():
                if ln.startswith("STUDIO_OUTPUT\t"):
                    parts = ln.split("\t", 2)
                    if len(parts) == 3:
                        remote_outputs.append((parts[1], parts[2]))
            if not remote_outputs:
                models = faceswap_runner.resolve_swapper_models(
                    swapper_model=spec["swapper_model"],
                    compare_all=spec["compare_all"],
                )
                ext = local_target.suffix.lower() or ".png"
                remote_outputs = [
                    (m, f"{remote_out_dir}/swap_{idx + 1}_{m}{ext}")
                    for idx, m in enumerate(models)
                ]

        tracker.record_stage("faceswap", "正在执行换脸流水线", is_warm, time.time() - t1)

        t2 = time.time()
        _update(jid, stage="正在回传换脸结果", stage_started_at=t2, progress=85)
        for idx, (model_name, rpath) in enumerate(remote_outputs):
            ext = Path(rpath).suffix.lower() or local_target.suffix.lower() or ".png"
            fname = f"{jid}_{idx + 1}_{model_name}{ext}"
            local_out = MEDIA_DIR / fname
            await asyncio.to_thread(runtime.download_file, rpath, local_out)
            media_kind = "video" if ext in (".mp4", ".webm", ".mov") else "image"
            label = faceswap_runner.MODEL_LABELS.get(model_name, model_name)
            outputs.append({
                "file": fname,
                "url": f"/media/{fname}",
                "kind": media_kind,
                "model": model_name,
                "label": label,
            })
        tracker.record_stage("faceswap", "正在回传换脸结果", is_warm, time.time() - t2)
    finally:
        try:
            await runtime.ssh(f"rm -rf {shlex.quote(remote_job_dir)}", timeout=30)
        except Exception:
            pass

    runtime.warm.add("faceswap")
    _update(jid, status="done", stage=None, progress=100, outputs=outputs, finished_at=time.time())


def _build_dreamid_remote_runner(
    *,
    source_image: str,
    target_media: str,
    work_dir: str,
    final_output: str,
) -> str:
    """Generate the remote execution script that slices videos into <=81 frames for DreamID-V Faster."""
    return f"""import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "/content/station")

source_image = {source_image!r}
target_media = {target_media!r}
work_dir = Path({work_dir!r})
final_output = Path({final_output!r})

probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0",
     "-count_frames", "-show_entries", "stream=nb_read_frames,r_frame_rate",
     "-of", "json", target_media],
    capture_output=True, text=True, check=True,
)
info = json.loads(probe.stdout)["streams"][0]
total_frames = int(info.get("nb_read_frames") or 81)
num, den = (info.get("r_frame_rate") or "24/1").split("/")
fps = float(num) / max(1.0, float(den))

max_frames = {dreamid_pipeline.MAX_DREAMID_FRAMES}
chunks = []
cur = 0
while cur < total_frames:
    cnt = min(total_frames - cur, max_frames)
    chunks.append((cur, cnt))
    cur += cnt

swapped_files = []
for idx, (start_f, count_f) in enumerate(chunks):
    chunk_in = work_dir / f"chunk_in_{{idx:03d}}.mp4"
    chunk_out = work_dir / f"chunk_out_{{idx:03d}}.mp4"
    end_f = start_f + count_f - 1
    vf = f"select='between(n\\\\,{{start_f}}\\\\,{{end_f}})',setpts=N/({{fps}}*TB)"
    subprocess.run(
        ["ffmpeg", "-y", "-i", target_media, "-vf", vf, "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(chunk_in)],
        check=True,
    )
    aligned = max(5, min(count_f, max_frames))
    aligned = ((aligned - 1) // 4) * 4 + 1
    subprocess.run(
        ["python3", "/content/DreamID-V/express_adaption/wan_swapface.py",
         "--task", "swapface", "--size", "832*480",
         "--ckpt_dir", "/content/models/dreamid_v/Wan2.1-T2V-1.3B",
         "--dreamidv_ckpt", "/content/models/dreamid_v/dreamidv_faster.pth",
         "--sample_steps", "12", "--frame_num", str(aligned),
         "--Sample_guide_scale_img", "4.0",
         "--ref_Path", f"{{chunk_in}},{{source_image}}",
         "--save_file", str(chunk_out)],
        check=True,
    )
    swapped_files.append(chunk_out)

concat_txt = work_dir / "concat.txt"
concat_txt.write_text("\\n".join(f"file '{{p}}'" for p in swapped_files) + "\\n")
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
     "-i", target_media, "-map", "0:v:0", "-map", "1:a:0?",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
     "-c:a", "aac", "-shortest", str(final_output)],
    check=True,
)
"""


async def _run(job: dict) -> None:
    jid = job["id"]
    kind = job["kind"]
    prompt = job["prompt"]
    p = job["params"]
    inputs = job["inputs"]

    async with httpx.AsyncClient(timeout=60) as http:
        if kind == "faceswap":
            await _run_faceswap(http, job)
            return

        if kind == "image":
            uploaded = [await _upload_to_comfy(http, f) for f in inputs[:10]]
            count = int(p.get("count", 1))
            base_seed = p.get("seed") or random.randint(1, 2**32 - 1)
            p["seed"] = base_seed
            outputs: list[dict] = []
            for i in range(count):
                wf = workflows.image_generate(
                    prompt,
                    profile=p.get("profile", "krea2_noct"),
                    ratio=p.get("ratio", "1:1"),
                    size=p.get("size", "1536"),
                    edit_resolution=int(p.get("edit_resolution", 1080)),
                    steps=int(p.get("steps", 25)),
                    cfg=float(p.get("cfg", 3.0)),
                    sampler=p.get("sampler", "euler"),
                    scheduler=p.get("scheduler", "simple"),
                    turbo=bool(p.get("turbo", False)),
                    negative=p.get("negative", ""),
                    seed=base_seed + i,
                    images=uploaded,
                )
                outs = await _exec_workflow(http, jid, kind, wf, idx=i, total=count)
                outputs.extend(outs)
            _update(jid, status="done", stage=None, progress=100, outputs=outputs, finished_at=time.time())

        elif kind == "video":
            first = await _upload_to_comfy(http, inputs[0]) if len(inputs) >= 1 else None
            last = await _upload_to_comfy(http, inputs[1]) if len(inputs) >= 2 else None
            seed = p.get("seed") or random.randint(1, 2**32 - 1)
            p["seed"] = seed
            wf = workflows.video_generate(
                prompt,
                profile=p.get("profile", "minimax_h3"),
                ratio=p.get("ratio", "16:9"),
                resolution=p.get("resolution", "480p"),
                seconds=int(p.get("seconds", 5)),
                quality=p.get("quality", "turbo"),
                seed=seed,
                first_frame=first,
                last_frame=last,
            )
            outs = await _exec_workflow(http, jid, kind, wf)
            _update(jid, status="done", stage=None, progress=100, outputs=outs, finished_at=time.time())


async def _exec_workflow(
    http: httpx.AsyncClient, jid: str, kind: str, wf: dict, idx: int = 0, total: int = 1
) -> list[dict]:
    client_id = uuid.uuid4().hex
    ws_url = f"ws://127.0.0.1:{runtime.COMFY_PORT}/ws?clientId={client_id}"
    titles = {nid: n.get("_meta", {}).get("title", "正在执行") for nid, n in wf.items()}
    prefix = f"[{idx + 1}/{total}] " if total > 1 else ""
    is_warm = kind in runtime.warm
    cur_stage: str | None = None
    stage_t0 = time.time()

    def _enter_stage(new_stage: str) -> None:
        nonlocal cur_stage, stage_t0
        now = time.time()
        if cur_stage and cur_stage != new_stage:
            tracker.record_stage(kind, cur_stage, is_warm, now - stage_t0)
        if cur_stage != new_stage:
            cur_stage = new_stage
            stage_t0 = now
            _update(jid, stage=f"{prefix}{new_stage}", stage_started_at=now, stages=STAGES.get(kind, []), warm=is_warm)

    _enter_stage("正在加载模型")

    try:
        ws_cm = websockets.connect(ws_url, max_size=32 * 1024 * 1024, ping_interval=20, ping_timeout=60)
    except TypeError:
        ws_cm = websockets.connect(ws_url, max_size=32 * 1024 * 1024)

    try:
        async with ws_cm as ws:
            r = await http.post(f"{runtime.COMFY_URL}/prompt", json={"prompt": wf, "client_id": client_id})
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI 拒绝了任务: {r.text[:300]}")
            prompt_id = r.json()["prompt_id"]
            _comfy_prompt_ids[jid] = prompt_id

            while True:
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                t = msg.get("type")
                d = msg.get("data", {})
                if d.get("prompt_id") not in (None, prompt_id):
                    continue
                if t == "executing":
                    node = d.get("node")
                    if node is None:
                        break
                    _enter_stage(titles.get(str(node), "正在执行"))
                elif t == "progress":
                    v, m = d.get("value", 0), max(1, d.get("max", 1))
                    pct = int(((idx + v / m) / total) * 100)
                    node = str(d.get("node", ""))
                    stage = titles.get(node) or cur_stage or "正在生成"
                    _enter_stage(stage)
                    label = f"{prefix}{stage} ({v}/{m} 步)" if m <= 60 else f"{prefix}{stage} ({int(v * 100 / m)}%)"
                    _update(jid, stage=label, progress=pct)
                elif t == "execution_error":
                    em = d.get("exception_message", "ComfyUI 执行出错")
                    raise RuntimeError(em.strip())
    except websockets.ConnectionClosed as e:
        settled = await _wait_history(http, _comfy_prompt_ids.get(jid, ""), timeout=120)
        if not settled:
            raise RuntimeError(f"ComfyUI 连接中断: {e}") from e

    if cur_stage:
        tracker.record_stage(kind, cur_stage, is_warm, time.time() - stage_t0)
    runtime.warm.add(kind)

    hist = (await http.get(f"{runtime.COMFY_URL}/history/{prompt_id}")).json().get(prompt_id, {})
    return await _collect_outputs(http, jid, hist.get("outputs", {}), idx)


async def _wait_history(http: httpx.AsyncClient, prompt_id: str, timeout: int = 120) -> bool:
    if not prompt_id:
        return False
    for _ in range(timeout // 2):
        await asyncio.sleep(2)
        try:
            h = (await http.get(f"{runtime.COMFY_URL}/history/{prompt_id}")).json().get(prompt_id)
            if h and h.get("outputs"):
                return True
        except Exception:
            pass
    return False


async def _collect_outputs(http: httpx.AsyncClient, jid: str, raw_outputs: dict, idx: int) -> list[dict]:
    collected: list[dict] = []
    for node_out in raw_outputs.values():
        for key in ("images", "video", "videos", "gifs"):
            for item in node_out.get(key, []):
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                fn = item["filename"]
                ext = Path(fn).suffix.lower()
                r = await http.get(
                    f"{runtime.COMFY_URL}/view",
                    params={
                        "filename": fn,
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    },
                )
                r.raise_for_status()
                local_name = f"{jid}_{idx}_{len(collected)}{ext}"
                dest = MEDIA_DIR / local_name
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(r.content)
                os.replace(tmp, dest)
                kind = "video" if ext in (".mp4", ".webm", ".mov") else "image"
                collected.append({"file": local_name, "url": f"/media/{local_name}", "kind": kind})
    return collected
