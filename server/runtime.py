"""Colab GPU lifecycle manager: allocate -> SSH -> setup -> ComfyUI + FaceFusion -> tunnel -> watchdog -> stop."""
from __future__ import annotations

import asyncio
import json
import re
import shlex
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from . import config, tracker

STATION_DIR = Path(__file__).resolve().parent.parent / "station"
MODELS_TOML = Path(__file__).resolve().parent.parent / "models.toml"
COMFY_PORT = 18188
COMFY_URL = f"http://127.0.0.1:{COMFY_PORT}"
IDLE_TIMEOUT = config.IDLE_TIMEOUT_MIN * 60
HEALTH_FAIL_LIMIT = 3
SETUP_STALL_TIMEOUT = 15 * 60
SESSION_FILE = config.DATA_DIR / "studio_session.json"
SSH_KEY = config.DATA_DIR / "ssh" / "id_ed25519"
COLAB_SESSIONS = Path("~/.config/colab-cli/sessions.json").expanduser()

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
    for tool in ("ssh", "ssh-keygen", "tar"):
        if not shutil.which(tool):
            raise RuntimeError(f"未找到 {tool}：需安装 openssh-client 和 tar")


def _clean_err(raw: str) -> str:
    if config.HF_TOKEN:
        raw = raw.replace(config.HF_TOKEN, "[redacted]")
    lines = [
        ln.strip() for ln in raw.splitlines()
        if ln.strip() and not ln.startswith(("WARNING:", "Warning: Permanently added"))
    ]
    msg = "\n".join(lines[-40:])[-4000:] if lines else raw.strip()[-4000:]
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
        return [config.COLAB_BIN, *args]

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
            raise RuntimeError(f"执行超时 ({timeout}s): {args[0]}") from e
        if proc.returncode != 0:
            msg = _clean_err(err.decode(errors="replace") or out.decode(errors="replace"))
            raise RuntimeError(msg or f"命令执行失败 ({proc.returncode}): {args[0]}")
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
        # Resume our recorded session after an unclean server restart. Session names
        # are unique to this studio, so unrelated Colab sessions are never touched.
        SSH_KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not SSH_KEY.exists():
            result = await asyncio.to_thread(
                subprocess.run,
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(SSH_KEY)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode:
                raise RuntimeError(f"创建 SSH 密钥失败: {result.stderr.strip()}")
        # Some NAS bind mounts apply inherited ACLs that make new keys too open
        # for OpenSSH even when ssh-keygen requested mode 0600.
        SSH_KEY.chmod(0o600)
        resume = SESSION_FILE.exists()
        session = json.loads(SESSION_FILE.read_text()).get("name", "") if resume else f"{config.SESSION_PREFIX}-{uuid.uuid4().hex[:12]}"
        if not isinstance(session, str):
            raise RuntimeError("工作台会话记录无效")
        if not re.fullmatch(r"[A-Za-z0-9_-]+-[0-9a-f]{12}", session):
            raise RuntimeError("STUDIO_SESSION 只能包含字母、数字、下划线和连字符")
        if not resume:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps({"name": session}))
            await self._run("new", "--gpu", config.GPU_TIER.upper(), "-s", session, timeout=600)
        proxy = shlex.join([
            "sh", str(Path(__file__).with_name("colab_proxy.sh")), session,
            str(COLAB_SESSIONS), config.COLAB_BIN, str(SSH_KEY),
        ]).replace("%", "%%")
        self._ssh_flags = [
            "-o", f"ProxyCommand={proxy}",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "IdentitiesOnly=yes",
            "-i", str(SSH_KEY),
            "-o", "ConnectTimeout=60",
            "-o", "ControlMaster=auto",
            "-o", "ControlPersist=600",
            "-o", f"ControlPath={SSH_KEY.parent / ('control-' + session[-12:])}",
        ]
        self._ssh_host = "root@colab-studio"

    async def _stop_owned_session(self) -> None:
        if not SESSION_FILE.exists():
            return
        data = json.loads(SESSION_FILE.read_text())
        session = data.get("name", "")
        if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]+-[0-9a-f]{12}", session):
            raise RuntimeError("工作台会话记录无效，无法安全关闭远端会话")
        await self._run("stop", "-s", session, timeout=60)
        SESSION_FILE.unlink(missing_ok=True)

    def _ship_station_sync(self, tar_cmd: list[str], ssh_cmd: list[str]) -> tuple[int, str]:
        t_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE)
        s_proc = subprocess.Popen(ssh_cmd, stdin=t_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert t_proc.stdout is not None
        t_proc.stdout.close()
        _, err = s_proc.communicate(timeout=120)
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
            "&& chmod +x /content/station/*.sh",
        )
        rc, err = await asyncio.to_thread(self._ship_station_sync, tar_cmd, ssh_cmd)
        if rc != 0:
            raise RuntimeError(f"station 同步失败: {err}")

    # --- Lifecycle ---------------------------------------------------------

    async def ensure_ready(self, initial_pack: str | None = None) -> None:
        if self.state == "ready":
            self.touch()
            return
        async with self._lock:
            if self.state == "ready":
                self.touch()
                return
            await self._boot(initial_pack=initial_pack)

    async def _boot(self, initial_pack: str | None = None) -> None:
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
                if initial_pack:
                    label = PACK_LABELS.get(initial_pack, initial_pack)
                    self.step = f"正在部署 ComfyUI 并并行预热 {label}"
                    self._log(f"开始首次环境初始化（ComfyUI + 并行预热 {label}；FaceFusion 按需部署）...")
                else:
                    self.step = "正在部署 ComfyUI 核心环境"
                    self._log("开始首次环境初始化（仅部署 ComfyUI 核心环境；模型与换脸引擎按需部署）...")
                await self._run_setup_Remote(initial_pack=initial_pack)

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
            self._close_control_master()
            if SESSION_FILE.exists():
                self._log("启动失败，正在释放远端 GPU 以避免空转扣费...")
                await self._force_disconnect("启动失败，正在关闭")
            raise

    async def _run_setup_Remote(self, initial_pack: str | None = None) -> None:
        hf = shlex.quote(config.HF_TOKEN)
        pack_arg = f" {shlex.quote(initial_pack)}" if initial_pack else ""
        await self.ssh(
            "if ! pgrep -f '^bash /content/station/[r]untime_setup\\.sh' >/dev/null; then "
            f"nohup env HF_TOKEN={hf} bash /content/station/[r]untime_setup.sh{pack_arg} "
            "> /content/setup.log 2>&1 < /dev/null & fi"
        )
        while True:
            await asyncio.sleep(4)
            await self._refresh_telemetry()
            state = await self.ssh(
                "if [ -f /content/.setup_done ]; then echo done; "
                "elif pgrep -f '/content/station/[r]untime_setup.sh' >/dev/null; then echo running; "
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
            "if ! pgrep -f '/content/ComfyUI/[m]ain.py' >/dev/null; then "
            "nohup /content/comfyenv/bin/python /content/ComfyUI/[m]ain.py --listen 127.0.0.1 --port 8188 --disable-auto-launch "
            "> /content/comfy.log 2>&1 < /dev/null & fi"
        )
        await self.ssh(cmd)

    def _spawn_tunnel_proc(self) -> None:
        self._kill_tunnel()
        # Multiplex the local port forward over the active ControlMaster (`colab ssh --proxy-mode`).
        # Opening a second independent `colab ssh` proxy with ControlPath=none can stall against
        # the existing session relay; if the mux client returns 0, the ControlMaster keeps the
        # `-L` forward alive.
        cmd = [
            "ssh", *self._ssh_flags, "-N",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-L", f"127.0.0.1:{COMFY_PORT}:127.0.0.1:8188",
            self._ssh_host,
        ]
        self._tunnel = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    async def _start_tunnel(self) -> None:
        await asyncio.to_thread(self._spawn_tunnel_proc)
        await asyncio.sleep(1.0)
        if self._tunnel and self._tunnel.poll() not in (None, 0):
            err = (self._tunnel.stderr.read().decode(errors="replace") if self._tunnel.stderr else "").strip()
            raise RuntimeError(f"SSH 隧道建立失败: {err or self._tunnel.returncode}")

    def _close_control_master(self) -> None:
        if not self._ssh_host or not self._ssh_flags:
            return
        try:
            subprocess.run(
                ["ssh", *self._ssh_flags, "-O", "exit", self._ssh_host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass

    def _kill_tunnel(self) -> None:
        if self._tunnel and self._tunnel.poll() is None:
            self._tunnel.terminate()
            try:
                self._tunnel.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._tunnel.kill()
        self._tunnel = None

    async def _wait_comfy_http(self) -> None:
        for i in range(90):
            if self._Comfy_alive():
                return
            if i % 5 == 4:
                alive = await self.ssh("pgrep -f '/content/ComfyUI/[m]ain.py' >/dev/null && echo y || echo n")
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
                await self._stop_owned_session()
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
            self._close_control_master()
            try:
                await self._stop_owned_session()
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
        if self.state in ("ready", "starting", "error") and SESSION_FILE.exists():
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
            pack_pat = shlex.quote(f"[m]odels.py.*(^| ){pack}($| )")
            await self.ssh(
                f"if ! pgrep -f {pack_pat} >/dev/null; then "
                f"nohup env HF_TOKEN={hf} /content/hfenv/bin/python /content/station/[m]odels.py {qpack} "
                ">> /content/models.log 2>&1 < /dev/null & fi"
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
                    await self.ssh("pkill -f '/content/station/[m]odels.py' || true")
                    raise RuntimeError(f"{label} 模型连续 {SETUP_STALL_TIMEOUT // 60} 分钟无进度，下载卡死")
                running = await self.ssh(f"pgrep -f {pack_pat} >/dev/null && echo y || echo n")
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
                part_sizes: dict[str, float] = {}
                for ln in parts_raw.splitlines():
                    toks = ln.rsplit(" ", 1)
                    if len(toks) == 2 and toks[1].isdigit():
                        part_sizes[Path(toks[0]).name] = int(toks[1]) / 1e9
                for p in data.get("packs", {}).values():
                    if p.get("current") and not p.get("ready"):
                        part_gb = part_sizes.get(f"{p['current']}.part", 0.0)
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
        cmd = [config.COLAB_BIN, "usage"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            msg = _clean_err(err.decode(errors="replace") or out.decode(errors="replace"))
            raise RuntimeError(msg or "无法读取 colab usage 输出")
        usage = out.decode(errors="replace")
        balance = re.search(r"Current balance:\s*([\d.]+)", usage)
        rate = re.search(r"Usage rate:\s*([\d.]+)", usage)
        if not balance or not rate:
            raise RuntimeError("无法解析 Colab 算力余额")
        return {"balance": float(balance.group(1)), "burn_rates_hourly": {config.GPU_TIER: float(rate.group(1))}}

    # --- Watchdog ----------------------------------------------------------

    async def watchdog_loop(self) -> None:
        health_fails = 0
        while True:
            await asyncio.sleep(20)
            if self.state == "off" and SESSION_FILE.exists():
                async with self._lock:
                    if self.state == "off" and SESSION_FILE.exists():
                        await self._force_disconnect("恢复上次未关闭的工作台会话")
                continue
            if self.state == "error" and SESSION_FILE.exists():
                await self._force_disconnect("错误恢复")
                continue
            if self.state != "ready":
                health_fails = 0
                continue
            alive = await asyncio.to_thread(self._Comfy_alive)
            if not alive and (self._tunnel is None or self._tunnel.poll() is not None):
                try:
                    self._log("SSH 隧道断开，正在重连...")
                    await self._start_tunnel()
                    alive = await asyncio.to_thread(self._Comfy_alive)
                except Exception as e:
                    self._log(f"隧道重连失败: {e}")
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
