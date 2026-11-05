"""Colab GPU lifecycle manager: allocate -> SSH -> setup -> ComfyUI + FaceFusion -> tunnel -> watchdog -> stop."""
from __future__ import annotations

import asyncio
import json
import shlex
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config, tracker

STATION_DIR = Path(__file__).resolve().parent.parent / "station"
MODELS_TOML = Path(__file__).resolve().parent.parent / "models.toml"
COMFY_PORT = 18188
COMFY_URL = f"http://127.0.0.1:{COMFY_PORT}"
IDLE_TIMEOUT = config.IDLE_TIMEOUT_MIN * 60
HEALTH_FAIL_LIMIT = 3
SETUP_STALL_TIMEOUT = 15 * 60

PACK_LABELS = {
    "image": "图片 (Krea2-Noct)",
    "image_turbo": "极速图片 (Z-Image-Turbo)",
    "video": "视频 (MiniMax-H3)",
    "video_wan22": "视频 (Wan2.2-Remix)",
}


def _check_host_tools() -> None:
    if not Path(config.COLAB_BIN).exists():
        raise RuntimeError(
            f"未找到 colab CLI ({config.COLAB_BIN})：请运行 ./install.sh 或在 .env 中设置 COLAB_BIN"
        )
    for tool in ("ssh", "tar"):
        if not shutil.which(tool):
            raise RuntimeError(f"未找到 {tool}：需安装 openssh-client 和 tar")


def _clean_err(raw: str) -> str:
    lines = [
        ln.strip() for ln in raw.splitlines()
        if ln.strip() and not ln.startswith(("WARNING:", "Warning: Permanently added"))
    ]
    msg = lines[-1] if lines else raw.strip()
    if "not authenticated" in msg.lower() or "colab auth login" in msg.lower():
        if Path("/.dockerenv").exists():
            return "colab CLI 未登录 Google：请执行 'docker compose run --rm studio colab usage' 完成登录，然后重新启动 GPU"
        return "colab CLI 未登录 Google：请在终端执行 'colab usage' 完成登录，然后重新启动 GPU"
    return msg


class Runtime:
    def __init__(self) -> None:
        self.state = "off"          # off | starting | ready | stopping | error
        self.step = "GPU 已关闭"
        self.error: str | None = None
        self.gpu_name: str | None = None
        self.vram_used_mb = 0
        self.vram_total_mb = 0
        self.disk_free_gb = 0.0
        self.disk_total_gb = 0.0
        self.models: dict = {}
        self.setup_step: str | None = None
        self.started_at: float | None = None
        self.last_used: float = time.time()
        self.active_jobs = 0
        self.warm: set[str] = set()
        self.log: list[str] = []

        self._lock = asyncio.Lock()
        self._pack_locks: dict[str, asyncio.Lock] = {}
        self._ssh_flags: list[str] = []
        self._ssh_host: str = ""
        self._tunnel: subprocess.Popen | None = None

    def _log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        self.log = (self.log + [line])[-200:]

    def touch(self) -> None:
        self.last_used = time.time()

    def status(self) -> dict:
        now = time.time()
        return {
            "state": self.state,
            "step": self.step,
            "error": self.error,
            "gpu_tier": config.GPU_TIER,
            "gpu_name": self.gpu_name,
            "vram_used_mb": self.vram_used_mb,
            "vram_total_mb": self.vram_total_mb,
            "disk_free_gb": self.disk_free_gb,
            "disk_total_gb": self.disk_total_gb,
            "models": self.models,
            "setup_step": self.setup_step,
            "uptime_s": int(now - self.started_at) if self.started_at else 0,
            "idle_s": int(now - self.last_used) if self.state == "ready" and self.active_jobs == 0 else 0,
            "idle_timeout_s": IDLE_TIMEOUT,
            "active_jobs": self.active_jobs,
            "warm": sorted(self.warm),
            "log": self.log[-40:],
        }

    # --- Low-level command execution ---------------------------------------

    def _cmd(self, *args: str) -> list[str]:
        if args and args[0] == "ssh" and self._ssh_host:
            return ["ssh", *self._ssh_flags, self._ssh_host, *args[1:]]
        return [config.COLAB_BIN, "--gpu", config.GPU_TIER, *args]

    async def _run(self, *args: str, timeout: int = 120) -> str:
        cmd = self._cmd(*args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as e:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise RuntimeError(f"执行超时 ({timeout}s): {' '.join(args[:2])}") from e
        if proc.returncode != 0:
            msg = _clean_err(err.decode(errors="replace") or out.decode(errors="replace"))
            raise RuntimeError(msg or f"命令执行失败 ({proc.returncode}): {' '.join(args[:2])}")
        return out.decode(errors="replace").strip()

    async def ssh(self, remote_cmd: str, timeout: int = 120) -> str:
        return await self._run("ssh", remote_cmd, timeout=timeout)

    def upload_file(self, local_path: Path, remote_path: str, timeout: int = 180) -> None:
        """Stream a local file to `remote_path` on the Colab instance over SSH."""
        parent = str(Path(remote_path).parent)
        cmd = self._cmd("ssh", f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(remote_path)}")
        with open(local_path, "rb") as f:
            proc = subprocess.run(cmd, stdin=f, capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"上传文件失败 ({local_path.name}): {err}")

    def download_file(self, remote_path: str, local_path: Path, timeout: int = 300) -> None:
        """Stream a remote file from the Colab instance to `local_path` atomically."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        part = local_path.with_suffix(local_path.suffix + ".part")
        cmd = self._cmd("ssh", f"cat {shlex.quote(remote_path)}")
        with open(part, "wb") as f:
            proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=timeout)
        if proc.returncode != 0 or not part.exists() or part.stat().st_size == 0:
            part.unlink(missing_ok=True)
            err = proc.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"下载文件失败 ({remote_path}): {err}")
        part.replace(local_path)

    async def _load_ssh_config(self) -> None:
        raw = await self._run("ssh", "--raw", timeout=180)
        tokens = shlex.split(raw)
        if not tokens or tokens[0] != "ssh":
            raise RuntimeError(f"无法解析 ssh --raw 输出: {raw[:120]}")
        self._ssh_flags = [
            "-o", "ControlMaster=auto",
            "-o", "ControlPersist=300",
            "-o", "ControlPath=/tmp/colab-ssh-%C",
            "-o", "ConnectTimeout=15",
            *tokens[1:-1],
        ]
        self._ssh_host = tokens[-1]

    def _ship_station_sync(self, tar_cmd: list[str], ssh_cmd: list[str]) -> tuple[int, str]:
        t_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE)
        s_proc = subprocess.Popen(ssh_cmd, stdin=t_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert t_proc.stdout is not None
        t_proc.stdout.close()
        _, err = s_proc.communicate(timeout=60)
        t_proc.wait(timeout=5)
        return s_proc.returncode, err.decode(errors="replace").strip()

    async def _ship_station(self) -> None:
        extra: list[str] = []
        if MODELS_TOML.is_file():
            extra = ["-C", str(MODELS_TOML.parent), MODELS_TOML.name]
        tar_cmd = ["tar", "-C", str(STATION_DIR.parent), "-cf", "-", "station", *extra]
        ssh_cmd = self._cmd(
            "ssh",
            "mkdir -p /content && tar -xf - -C /content "
            "&& ([ ! -f /content/models.toml ] || mv /content/models.toml /content/station/models.default.toml) "
            "&& chmod +x /content/station/runtime_setup.sh",
        )
        rc, err = await asyncio.to_thread(self._ship_station_sync, tar_cmd, ssh_cmd)
        if rc != 0:
            raise RuntimeError(f"station 同步失败: {err}")

    # --- Lifecycle ---------------------------------------------------------

    async def ensure_ready(self) -> None:
        if self.state == "ready":
            self.touch()
            return
        async with self._lock:
            if self.state == "ready":
                self.touch()
                return
            await self._boot()

    async def _boot(self) -> None:
        self.state = "starting"
        self.error = None
        self.warm.clear()
        self.setup_step = None
        boot_t0 = time.time()
        try:
            _check_host_tools()

            self.step = "正在分配 GPU"
            self._log(f"正在请求 Colab {config.GPU_TIER.upper()} 运行时...")
            await self._load_ssh_config()

            self.step = "正在连接"
            gpu = await self.ssh(
                "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits", timeout=60
            )
            parts = [p.strip() for p in gpu.split(",")]
            self.gpu_name = parts[0]
            self.vram_total_mb = int(float(parts[1])) if len(parts) > 1 else 0
            self._log(f"GPU 已连接: {self.gpu_name} ({self.vram_total_mb} MB)")

            await self._ship_station()
            done = await self.ssh("test -f /content/.setup_done && echo yes || echo no")
            if done != "yes":
                self.step = "正在下载模型并部署 ComfyUI 与 FaceFusion"
                self._log("开始首次环境初始化（下载图片主模型 + 部署 ComfyUI & FaceFusion 双补丁）...")
                await self._run_setup_Remote()

            self.step = "正在启动 ComfyUI"
            self.setup_step = None
            await self._start_comfy()
            await self._start_tunnel()
            await self._wait_comfy_http()
            await self._refresh_telemetry()

            self.state = "ready"
            self.step = "GPU 已就绪"
            self.started_at = time.time()
            self.touch()
            tracker.record_startup("boot", time.time() - boot_t0)
            self._log(f"GPU 已就绪（耗时 {int(time.time() - boot_t0)}s）")
        except Exception as e:
            self.state = "error"
            self.error = str(e)
            self.step = f"错误: {e}"
            self._log(f"错误: {e}")
            self._kill_tunnel()
            if self._ssh_host:
                self._log("启动失败，正在释放远端 GPU 以避免空转扣费...")
                await self._force_disconnect("启动失败，正在关闭")
            raise

    async def _run_setup_Remote(self) -> None:
        hf = shlex.quote(config.HF_TOKEN)
        await self.ssh(
            "pgrep -f '/content/station/runtime_setup.sh' >/dev/null || "
            f"nohup env HF_TOKEN={hf} bash /content/station/runtime_setup.sh image "
            "> /content/setup.log 2>&1 < /dev/null &"
        )
        while True:
            await asyncio.sleep(4)
            await self._refresh_telemetry()
            state = await self.ssh(
                "if [ -f /content/.setup_done ]; then echo done; "
                "elif pgrep -f '/content/station/runtime_setup.sh' >/dev/null; then echo running; "
                "else echo failed; fi",
                timeout=30,
            )
            if state == "done":
                self._log("runtime_setup.sh 执行完成")
                return
            if state == "failed":
                tail = await self.ssh("tail -n 25 /content/setup.log 2>/dev/null || true", timeout=20)
                raise RuntimeError(f"环境初始化失败:\n{tail[-600:]}")

    async def _start_comfy(self) -> None:
        cmd = (
            "pgrep -f '/content/ComfyUI/main.py' >/dev/null || "
            "nohup python3 /content/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch "
            "> /content/comfy.log 2>&1 < /dev/null &"
        )
        await self.ssh(cmd)

    def _spawn_tunnel_proc(self) -> None:
        self._kill_tunnel()
        subprocess.run(
            ["ssh", *self._ssh_flags, "-O", "exit", self._ssh_host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
        )
        cmd = [
            "ssh", *self._ssh_flags, "-N",
            "-o", "ControlMaster=no", "-o", "ControlPath=none",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-L", f"127.0.0.1:{COMFY_PORT}:127.0.0.1:8188",
            self._ssh_host,
        ]
        self._tunnel = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    async def _start_tunnel(self) -> None:
        await asyncio.to_thread(self._spawn_tunnel_proc)
        await asyncio.sleep(1.0)
        if self._tunnel and self._tunnel.poll() is not None:
            err = (self._tunnel.stderr.read().decode(errors="replace") if self._tunnel.stderr else "").strip()
            raise RuntimeError(f"SSH 隧道建立失败: {err or self._tunnel.returncode}")

    def _kill_tunnel(self) -> None:
        if self._tunnel and self._tunnel.poll() is None:
            self._tunnel.terminate()
            try:
                self._tunnel.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._tunnel.kill()
        self._tunnel = None
        if self._ssh_host:
            subprocess.run(
                ["ssh", *self._ssh_flags, "-O", "exit", self._ssh_host],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            )

    async def _wait_comfy_http(self) -> None:
        for i in range(90):
            if self._Comfy_alive():
                return
            if i % 5 == 4:
                alive = await self.ssh("pgrep -f '/content/ComfyUI/main.py' >/dev/null && echo y || echo n")
                if alive != "y":
                    tail = await self.ssh("tail -n 20 /content/comfy.log 2>/dev/null || true")
                    raise RuntimeError(f"ComfyUI 进程异常退出:\n{tail[-500:]}")
            await asyncio.sleep(2)
        tail = await self.ssh("tail -n 20 /content/comfy.log 2>/dev/null || true")
        raise RuntimeError(f"ComfyUI 启动超时:\n{tail[-500:]}")

    def _Comfy_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    async def _force_disconnect(self, reason: str) -> None:
        for attempt in range(3):
            try:
                await self._run("disconnect", timeout=30)
                self._ssh_host = ""
                self._ssh_flags = []
                self._log(f"GPU 已断开连接 ({reason})")
                return
            except Exception as e:
                self._log(f"disconnect 重试 {attempt + 1}/3: {e}")
                await asyncio.sleep(2)
        self._log("警告: colab disconnect 未确认，将继续由看门狗重试")

    async def stop(self, reason: str = "手动关闭", preserve_error: bool = False) -> None:
        async with self._lock:
            prev_error = self.error if preserve_error else None
            self.state = "stopping"
            self.step = f"正在关闭 ({reason})"
            self._log(f"正在关闭 GPU: {reason}")
            self._kill_tunnel()
            try:
                await self._run("disconnect", timeout=30)
            except Exception as e:
                self._log(f"disconnect 错误: {e}")
                self.state = "error"
                self.error = prev_error or f"GPU 无法关闭，将自动重试: {e}"
                self.step = f"错误: {self.error}"
                return
            self._ssh_host = ""
            self._ssh_flags = []
            self.state = "error" if prev_error else "off"
            self.error = prev_error
            self.step = f"错误: {prev_error}" if prev_error else "GPU 已关闭"
            self.gpu_name = None
            self.vram_used_mb = 0
            self.vram_total_mb = 0
            self.started_at = None
            self.warm.clear()
            self._log("GPU 已关闭")

    async def disconnect_on_shutdown(self) -> None:
        self._kill_tunnel()
        if self.state in ("ready", "starting", "error") and self._ssh_host:
            await self._force_disconnect("服务停止")

    # --- Model pack download & telemetry -----------------------------------

    async def ensure_models(self, pack: str, on_progress=None) -> None:
        lock = self._pack_locks.setdefault(pack, asyncio.Lock())
        async with lock:
            await self._refresh_telemetry()
            if self.models.get("packs", {}).get(pack, {}).get("ready"):
                return
            label = PACK_LABELS.get(pack, pack)
            self._log(f"开始按需下载 {label} 模型包...")
            pack_t0 = time.time()
            last_done = -1.0
            last_advance = time.time()
            hf = shlex.quote(config.HF_TOKEN)
            qpack = shlex.quote(pack)
            await self.ssh(
                f"pgrep -f 'models.py.*{qpack}' >/dev/null || "
                f"nohup env HF_TOKEN={hf} /content/hfenv/bin/python /content/station/models.py {qpack} "
                ">> /content/models.log 2>&1 < /dev/null &"
            )
            while True:
                await asyncio.sleep(2)
                await self._refresh_telemetry()
                p = self.models.get("packs", {}).get(pack, {})
                if on_progress:
                    on_progress(p)
                if p.get("ready"):
                    tracker.record_startup(f"pack:{pack}", time.time() - pack_t0)
                    self._log(f"{label} 模型包已就绪")
                    return
                if p.get("error"):
                    raise RuntimeError(f"{label} 模型下载失败: {p['error']}")
                done = float(p.get("done_gb") or 0.0)
                cur = p.get("current") or ""
                if done > last_done or (cur and time.time() - float(self.models.get("updated_at") or 0) < 30):
                    last_done = done
                    last_advance = time.time()
                elif time.time() - last_advance > SETUP_STALL_TIMEOUT:
                    await self.ssh("pkill -f '/content/station/models.py' || true")
                    raise RuntimeError(f"{label} 模型连续 {SETUP_STALL_TIMEOUT // 60} 分钟无进度，下载卡死")
                running = await self.ssh(f"pgrep -f 'models.py.*{qpack}' >/dev/null && echo y || echo n")
                if running != "y":
                    await self._refresh_telemetry()
                    p = self.models.get("packs", {}).get(pack, {})
                    if p.get("ready"):
                        tracker.record_startup(f"pack:{pack}", time.time() - pack_t0)
                        return
                    tail = await self.ssh("tail -n 20 /content/models.log 2>/dev/null || true")
                    raise RuntimeError(f"{label} 模型未完成下载:\n{tail[-400:]}")

    async def _refresh_telemetry(self) -> None:
        try:
            raw = await self.ssh(
                "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null || echo '0,0'; "
                "echo '---'; "
                "cat /content/models/.status.json 2>/dev/null || echo '{}'; "
                "echo '---'; "
                "cat /content/setup.step 2>/dev/null || true; "
                "echo '---'; "
                "stat -c '%n %s' /content/models/*/*.part /content/models/*/.hfcache/*.incomplete 2>/dev/null || true",
                timeout=15,
            )
            sections = raw.split("---")
            vram_line = sections[0].strip()
            status_raw = sections[1].strip() if len(sections) > 1 else "{}"
            step_line = sections[2].strip() if len(sections) > 2 else ""
            parts_raw = sections[3].strip() if len(sections) > 3 else ""
            used, total = [int(float(x.strip())) for x in vram_line.split(",")[:2]]
            self.vram_used_mb = used
            if total:
                self.vram_total_mb = total
            self.setup_step = step_line or None
            data = json.loads(status_raw or "{}")
            if data:
                part_gb = 0.0
                for ln in parts_raw.splitlines():
                    toks = ln.rsplit(" ", 1)
                    if len(toks) == 2 and toks[1].isdigit():
                        part_gb += int(toks[1]) / 1e9
                for p in data.get("packs", {}).values():
                    if p.get("current") and not p.get("ready"):
                        total_p = float(p.get("total_gb") or 0)
                        base = float(p.get("done_gb") or 0)
                        p["done_gb"] = round(min(total_p, base + part_gb), 2)
                        p["writing"] = part_gb < 0.05
                self.models = data
                self.disk_free_gb = data.get("disk_free_gb", self.disk_free_gb)
                self.disk_total_gb = data.get("disk_total_gb", self.disk_total_gb)
        except Exception:
            pass

    async def fetch_usage(self) -> dict:
        cmd = [config.COLAB_BIN, "usage", "--json"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            msg = _clean_err(err.decode(errors="replace") or out.decode(errors="replace"))
            raise RuntimeError(msg or "无法读取 colab usage 输出")
        try:
            data = json.loads(out.decode(errors="replace"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"无法解析 colab usage 输出: {e}") from e
        rates = data.get("burn_rates_hourly") or {}
        if "a100" in rates and "g2-standard-12" not in rates:
            rates["g2-standard-12"] = round(rates["a100"] * 0.4, 2)
        return data

    # --- Watchdog ----------------------------------------------------------

    async def watchdog_loop(self) -> None:
        health_fails = 0
        while True:
            await asyncio.sleep(20)
            if self.state == "error" and self._ssh_host:
                await self._force_disconnect("错误恢复")
                continue
            if self.state != "ready":
                health_fails = 0
                continue
            if self._tunnel is None or self._tunnel.poll() is not None:
                try:
                    self._log("SSH 隧道断开，正在重连...")
                    await self._start_tunnel()
                except Exception as e:
                    self._log(f"隧道重连失败: {e}")

            alive = await asyncio.to_thread(self._Comfy_alive)
            if alive:
                health_fails = 0
                await self._refresh_telemetry()
            else:
                health_fails += 1
                self._log(f"ComfyUI 健康检查失败 ({health_fails}/{HEALTH_FAIL_LIMIT})")
                if health_fails >= HEALTH_FAIL_LIMIT and self.active_jobs == 0:
                    try:
                        await self._start_comfy()
                        await self._start_tunnel()
                        if await asyncio.to_thread(self._Comfy_alive):
                            health_fails = 0
                            continue
                    except Exception as e:
                        self._log(f"ComfyUI 恢复失败 ({e})，正在释放 GPU...")
                        self.error = f"ComfyUI 无法访问，已停止运行时: {e}"
                        await self.stop("ComfyUI 无法访问，正在关闭", preserve_error=True)
                        health_fails = 0
                        continue

            idle = time.time() - self.last_used
            if self.active_jobs == 0 and idle >= IDLE_TIMEOUT:
                await self.stop(f"空闲满 {config.IDLE_TIMEOUT_MIN} 分钟，自动关闭 GPU")


runtime = Runtime()
