import { Coins, Cpu, HardDrive, Loader2, Package, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PackStatus, RuntimeStatus, StartupEstimates, UsageInfo } from "./api";
import { fmtDuration, fmtHours } from "./format";
import { t, translateServerText, useLang } from "./i18n";

const PACK_NAMES: Record<string, string> = {
  image: "图片 (Krea2-Noct)",
  image_turbo: "极速图片 (Z-Image-Turbo)",
  video: "视频 (MiniMax-H3)",
  video_wan22: "视频 (Wan2.2-Remix)",
};

const PACK_ORDER = ["image", "image_turbo", "video", "video_wan22"];

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

export function startupRemaining(
  rt: RuntimeStatus,
  startupEstimates?: StartupEstimates
): number | null {
  if (rt.state !== "starting") return null;
  const bootExp = startupEstimates?.boot?.expected ?? 180;
  return Math.max(5, bootExp - rt.uptime_s);
}

export function StartupPill({
  rt,
  startupEstimates,
}: {
  rt: RuntimeStatus;
  startupEstimates?: StartupEstimates;
}) {
  useLang();
  const { open, setOpen, ref } = usePopover();
  if (rt.state !== "starting") return null;

  const rem = startupRemaining(rt, startupEstimates) ?? 60;
  const bootExp = startupEstimates?.boot?.expected ?? 180;
  const pct = Math.min(95, Math.round((rt.uptime_s / bootExp) * 100));
  const stepText = translateServerText(rt.setup_step || rt.step);

  return (
    <div className="pop-anchor" ref={ref}>
      <button
        type="button"
        className="meta-pill meta-pill-btn startup-pill"
        onClick={() => setOpen(!open)}
        title={t("启动详情")}
      >
        <Loader2 size={12} className="spin" />
        <span>{stepText}</span>
        <span className="pill-dim">· ~{fmtDuration(rem)}</span>
      </button>
      {open && (
        <div className="popover">
          <div className="pop-head">
            <span>{t("正在启动 GPU")}</span>
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label={t("关闭详情")}>
              <X size={13} />
            </button>
          </div>
          <div className="pop-row">
            <span>{stepText}</span>
            <span className="mono">{pct}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${Math.max(6, pct)}%` }} />
          </div>
          <div className="pop-sub">
            {t("预计剩余 ~{left} · 已耗时 {elapsed}", {
              left: fmtDuration(rem),
              elapsed: fmtDuration(rt.uptime_s),
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function GpuStatsPill({ rt }: { rt: RuntimeStatus }) {
  useLang();
  const { open, setOpen, ref } = usePopover();
  if (rt.state !== "ready") return null;

  const vramGb = (rt.vram_used_mb / 1024).toFixed(1);
  const vramTotGb = (rt.vram_total_mb / 1024).toFixed(0);
  const vramPct = rt.vram_total_mb > 0 ? Math.round((rt.vram_used_mb / rt.vram_total_mb) * 100) : 0;
  const diskUsedGb = Math.max(0, rt.disk_total_gb - rt.disk_free_gb);
  const diskPct = rt.disk_total_gb > 0 ? Math.round((diskUsedGb / rt.disk_total_gb) * 100) : 0;

  return (
    <div className="pop-anchor" ref={ref}>
      <button
        type="button"
        className="meta-pill meta-pill-btn"
        onClick={() => setOpen(!open)}
        title={t("GPU 与系统详情")}
      >
        <Cpu size={12} />
        <span>
          VRAM {vramGb}/{vramTotGb} GB
        </span>
      </button>
      {open && (
        <div className="popover">
          <div className="pop-head">
            <span>{t("GPU 与系统")}</span>
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label={t("关闭详情")}>
              <X size={13} />
            </button>
          </div>
          <div className="pop-row">
            <span>VRAM</span>
            <span className="mono">
              {vramGb} / {vramTotGb} GB ({vramPct}%)
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${vramPct}%` }} />
          </div>
          {rt.disk_total_gb > 0 && (
            <>
              <div className="pop-row" style={{ marginTop: 8 }}>
                <span>
                  <HardDrive size={12} style={{ verticalAlign: "-2px" }} /> {t("磁盘")}
                </span>
                <span className="mono">
                  {diskUsedGb.toFixed(1)} / {rt.disk_total_gb.toFixed(0)} GB ({diskPct}%)
                </span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${diskPct}%` }} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function ModelPackPill({
  rt,
}: {
  rt: RuntimeStatus;
  startupEstimates?: StartupEstimates;
}) {
  useLang();
  const { open, setOpen, ref } = usePopover();
  const packs = rt.models?.packs || {};
  const entries = PACK_ORDER.filter((k) => k in packs).map((k) => [k, packs[k]] as [string, PackStatus]);
  if (entries.length === 0) return null;

  const readyCount = entries.filter(([, p]) => p.ready).length;
  const activeEntry = entries.find(([, p]) => p.current && !p.ready);

  return (
    <div className="pop-anchor" ref={ref}>
      <button
        type="button"
        className="meta-pill meta-pill-btn"
        onClick={() => setOpen(!open)}
        title={t("模型详情")}
      >
        <Package size={12} />
        {activeEntry ? (
          <span>
            {t(PACK_NAMES[activeEntry[0]] || activeEntry[0])}: {activeEntry[1].done_gb}/{activeEntry[1].total_gb} GB
          </span>
        ) : (
          <span>
            {t("模型")} {t("{n}/{total} 已就绪", { n: readyCount, total: entries.length })}
          </span>
        )}
      </button>
      {open && (
        <div className="popover">
          <div className="pop-head">
            <span>{t("模型包")}</span>
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label={t("关闭详情")}>
              <X size={13} />
            </button>
          </div>
          {entries.map(([k, p]) => {
            const pct = p.total_gb > 0 ? Math.min(100, Math.round((p.done_gb / p.total_gb) * 100)) : 0;
            return (
              <div key={k} className="pack-item">
                <div className="pop-row">
                  <span>{t(PACK_NAMES[k] || k)}</span>
                  <span className="mono">
                    {p.ready ? t("已就绪 ✓") : `${p.done_gb}/${p.total_gb} GB (${pct}%)`}
                  </span>
                </div>
                {!p.ready && (
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${pct}%` }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function CreditPill({
  usage,
  error,
}: {
  usage: UsageInfo | null;
  error?: string | null;
}) {
  useLang();
  const { open, setOpen, ref } = usePopover();
  if (!usage && !error) return null;

  return (
    <div className="pop-anchor" ref={ref}>
      <button
        type="button"
        className="meta-pill meta-pill-btn"
        onClick={() => setOpen(!open)}
        title={t("算力单元详情")}
      >
        <Coins size={12} />
        {usage ? (
          <span>
            {usage.balance.toFixed(1)} CU
            {usage.remaining_hours_active !== null && (
              <span className="pill-dim"> · {t("可用 {d}", { d: fmtHours(usage.remaining_hours_active) })}</span>
            )}
          </span>
        ) : (
          <span>{t("无法读取算力余额")}</span>
        )}
      </button>
      {open && (
        <div className="popover">
          <div className="pop-head">
            <span>{t("算力余额")}</span>
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label={t("关闭详情")}>
              <X size={13} />
            </button>
          </div>
          {error && <div className="pop-err">{translateServerText(error)}</div>}
          {usage && (
            <>
              <div className="pop-row">
                <span>{t("当前余额")}</span>
                <span className="mono">{usage.balance.toFixed(2)} CU</span>
              </div>
              <div className="pop-row">
                <span>{t("每小时消耗")}</span>
                <span className="mono">{t("{n} CU/小时", { n: usage.current_burn_rate })}</span>
              </div>
              {usage.remaining_hours_active !== null && (
                <div className="pop-row">
                  <span>{t("按当前速率可用")}</span>
                  <span className="mono">{fmtHours(usage.remaining_hours_active)}</span>
                </div>
              )}
              <div className="pop-row">
                <span>{t("本次会话已用")}</span>
                <span className="mono">{usage.session_used.toFixed(2)} CU</span>
              </div>
              <div className="pop-row">
                <span>{t("今日已用")}</span>
                <span className="mono">{usage.today_used.toFixed(2)} CU</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
