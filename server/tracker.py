"""Credit & timing tracker: persists Colab CU balance and per-stage execution durations."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config

USAGE_FILE = config.DATA_DIR / "usage.json"
TIMINGS_FILE = config.DATA_DIR / "timings.json"
STARTUP_FILE = config.DATA_DIR / "startup_timings.json"

MAX_SAMPLES = 25
MAX_DAYS = 90
OUTLIER_FACTOR = 4.0

STARTUP_BASELINES: dict[str, float] = {
    "boot": 180.0,
    "pack:image": 85.0,
    "pack:image_turbo": 95.0,
    "pack:video": 180.0,
    "pack:video_wan22": 150.0,
}

BASELINES: dict[str, tuple[float, float]] = {
    "image:正在加载模型": (28.0, 2.0),
    "image:正在读取参考图": (3.0, 2.0),
    "image:正在编码提示词": (6.0, 4.0),
    "image:正在准备画布": (1.0, 1.0),
    "image:正在生成": (55.0, 55.0),
    "image:正在保存": (3.0, 3.0),
    "video:正在加载模型": (50.0, 3.0),
    "video:正在读取参考图": (2.0, 2.0),
    "video:正在编码提示词": (15.0, 10.0),
    "video:正在准备画布": (2.0, 2.0),
    "video:正在生成": (180.0, 180.0),
    "video:正在生成（高噪阶段）": (110.0, 110.0),
    "video:正在生成（低噪阶段）": (110.0, 110.0),
    "video:正在解码音频": (4.0, 4.0),
    "video:正在保存": (12.0, 12.0),
    "faceswap:正在释放显存与上传素材": (4.0, 2.0),
    "faceswap:正在执行换脸流水线": (45.0, 35.0),
    "faceswap:正在回传换脸结果": (4.0, 3.0),
}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_usage(raw: dict, gpu_tier: str, runtime_active: bool) -> dict:
    """Update usage history from raw `colab usage --json` and return enriched summary."""
    now = time.time()
    balance = float(raw.get("balance") or 0.0)
    rates = dict(raw.get("burn_rates_hourly") or {})
    if "a100" in rates and "g2-standard-12" not in rates:
        rates["g2-standard-12"] = round(float(rates["a100"]) * 0.4, 2)
    burn_rate = float(rates.get(gpu_tier) or rates.get("l4") or 1.8)

    hist = _read_json(USAGE_FILE, {})
    last_bal = hist.get("last_balance")
    delta = (last_bal - balance) if isinstance(last_bal, (int, float)) and last_bal > balance else 0.0

    sess = hist.get("session")
    if runtime_active:
        if not sess or not sess.get("active"):
            sess = {"active": True, "started_at": now, "start_balance": balance, "used": 0.0}
        else:
            sess["used"] = round(max(0.0, float(sess.get("start_balance", balance)) - balance), 2)
    else:
        if sess and sess.get("active"):
            sess["active"] = False

    day = _today()
    days: dict[str, float] = hist.get("days") or {}
    days.setdefault(day, 0.0)
    if 0 < delta < 50:
        days[day] = round(days[day] + delta, 3)
    if len(days) > MAX_DAYS:
        for k in sorted(days)[:-MAX_DAYS]:
            del days[k]

    hist = {"last_balance": balance, "last_ts": now, "session": sess, "days": days}
    _write_json(USAGE_FILE, hist)

    recent = [v for k, v in sorted(days.items())[-7:] if v > 0]
    daily_avg = round(sum(recent) / len(recent), 2) if recent else None
    return {
        **raw,
        "burn_rates_hourly": rates,
        "gpu_tier": gpu_tier,
        "current_burn_rate": round(burn_rate, 2),
        "remaining_hours_active": round(balance / burn_rate, 1) if burn_rate > 0 else None,
        "session_used": round(sess["used"], 2) if sess else 0.0,
        "today_used": round(days.get(day, 0.0), 2),
        "daily_avg_7d": daily_avg,
        "days_Observed": len(recent),
        "projected_days_left": round(balance / daily_avg, 1) if daily_avg and daily_avg > 0.05 else None,
        "daily_history": [{"date": k, "used": round(v, 2)} for k, v in sorted(days.items())[-14:]],
    }


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def record_stage(kind: str, stage: str, warm: bool, duration_s: float) -> None:
    if duration_s < 0.2 or duration_s > 3600:
        return
    key = f"{kind}:{stage}"
    bucket = "warm" if warm else "cold"
    data: dict = _read_json(TIMINGS_FILE, {})
    entry = data.setdefault(key, {"cold": [], "warm": []})
    samples: list[float] = entry.setdefault(bucket, [])
    if len(samples) >= 3:
        med = _median(samples)
        if med > 1.0 and duration_s > med * OUTLIER_FACTOR:
            return
    samples.append(round(duration_s, 2))
    del samples[:-MAX_SAMPLES]
    _write_json(TIMINGS_FILE, data)


def get_estimates() -> dict:
    data: dict = _read_json(TIMINGS_FILE, {})
    keys = set(BASELINES) | set(data)
    out: dict[str, dict] = {}
    for k in keys:
        base_c, base_w = BASELINES.get(k, (15.0, 10.0))
        rec = data.get(k) or {}
        cold_s = rec.get("cold") or []
        warm_s = rec.get("warm") or []
        out[k] = {
            "cold": round(_median(cold_s), 1) if cold_s else base_c,
            "warm": round(_median(warm_s), 1) if warm_s else base_w,
            "samples": len(cold_s) + len(warm_s),
        }
    return out


def record_startup(key: str, duration_s: float) -> None:
    if duration_s < 1.0 or duration_s > 3600:
        return
    data: dict = _read_json(STARTUP_FILE, {})
    samples: list[float] = data.setdefault(key, [])
    if len(samples) >= 3:
        med = _median(samples)
        if med > 5.0 and duration_s > med * OUTLIER_FACTOR:
            return
    samples.append(round(duration_s, 1))
    del samples[:-MAX_SAMPLES]
    _write_json(STARTUP_FILE, data)


def get_startup_estimates() -> dict:
    data: dict = _read_json(STARTUP_FILE, {})
    out: dict[str, dict] = {}
    for k in set(STARTUP_BASELINES) | set(data):
        s = data.get(k) or []
        out[k] = {
            "expected": round(_median(s), 1) if s else STARTUP_BASELINES.get(k, 120.0),
            "samples": len(s),
        }
    return out
