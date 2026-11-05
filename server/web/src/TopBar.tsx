import { Cpu, Menu, Power, ScrollText, SlidersHorizontal } from "lucide-react";
import { RuntimeStatus, StartupEstimates, UsageInfo } from "./api";
import { fmtDuration } from "./format";
import { LANGS, t, useLang } from "./i18n";
import { CreditPill, GpuStatsPill, ModelPackPill, StartupPill } from "./SystemPanel";

interface Props {
  rt: RuntimeStatus;
  usage: UsageInfo | null;
  usageError?: string | null;
  startupEstimates?: StartupEstimates;
  onStart: () => void;
  onStop: () => void;
  showLogs: boolean;
  onToggleLogs: () => void;
  showSettings: boolean;
  onToggleSettings: () => void;
  onToggleNav: () => void;
  theme: "dark" | "dim" | "light";
  onTheme: (t: "dark" | "dim" | "light") => void;
}

const STATE_LABEL: Record<RuntimeStatus["state"], string> = {
  off: "GPU 已关闭",
  starting: "正在启动 GPU",
  ready: "已就绪",
  stopping: "正在关闭",
  error: "错误",
};

const THEMES: { id: "dark" | "dim" | "light"; label: string }[] = [
  { id: "dark", label: "深色" },
  { id: "dim", label: "暗灰" },
  { id: "light", label: "浅色" },
];

export default function TopBar({
  rt,
  usage,
  usageError,
  startupEstimates,
  onStart,
  onStop,
  showLogs,
  onToggleLogs,
  showSettings,
  onToggleSettings,
  onToggleNav,
  theme,
  onTheme,
}: Props) {
  const [lang, setLang] = useLang();
  const busy = rt.state === "starting" || rt.state === "stopping";
  const idleLeftMin =
    rt.state === "ready" && rt.active_jobs === 0 && rt.idle_timeout_s > 0
      ? Math.max(1, Math.ceil((rt.idle_timeout_s - rt.idle_s) / 60))
      : null;
  const idleMaxMin = Math.round(rt.idle_timeout_s / 60);
  const idleElapsedMin = Math.floor(rt.idle_s / 60);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="icon-btn nav-toggle" onClick={onToggleNav} title={t("菜单")} aria-label={t("菜单")}>
          <Menu size={16} />
        </button>

        <div className={`gpu-badge state-${rt.state}`}>
          <span className="gpu-dot" />
          <Cpu size={14} />
          <span className="gpu-label">
            {rt.state === "ready" && rt.gpu_name ? `${rt.gpu_name} · ${t("已就绪")}` : t(STATE_LABEL[rt.state])}
          </span>
        </div>

        {rt.state === "off" || rt.state === "error" ? (
          <button className="btn-ghost" onClick={onStart}>
            <Power size={13} /> {t("启动 {gpu}", { gpu: rt.gpu_tier.toUpperCase() })}
          </button>
        ) : (
          <button className="btn-ghost" onClick={onStop} disabled={busy}>
            <Power size={13} /> {t("关闭")}
          </button>
        )}

        <StartupPill rt={rt} startupEstimates={startupEstimates} />
        <GpuStatsPill rt={rt} />
        <ModelPackPill rt={rt} startupEstimates={startupEstimates} />
      </div>

      <div className="topbar-right">
        {idleLeftMin !== null && (
          <span
            className="meta-pill"
            title={`${t("空闲 {n}/{max} 分钟", { n: idleElapsedMin, max: idleMaxMin })} · ${t("空闲满 {n} 分钟自动关闭 GPU", { n: idleMaxMin })} (${t("剩余 {d}", { d: fmtDuration(rt.idle_timeout_s - rt.idle_s) })})`}
          >
            {t("自动关闭")} {idleLeftMin}m
          </span>
        )}
        <CreditPill usage={usage} error={usageError} />
        <div className="theme-seg" role="group" aria-label="Language">
          {LANGS.map((l) => (
            <button
              key={l}
              className={`theme-btn ${lang === l ? "active" : ""}`}
              onClick={() => setLang(l)}
              title={l === "zh" ? "中文" : "English"}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="theme-seg" role="group">
          {THEMES.map((th) => (
            <button
              key={th.id}
              className={`theme-btn ${theme === th.id ? "active" : ""}`}
              onClick={() => onTheme(th.id)}
              title={t(th.label)}
            >
              {t(th.label)}
            </button>
          ))}
        </div>
        <button
          className={`icon-btn ${showLogs ? "active" : ""}`}
          onClick={onToggleLogs}
          title={t("日志")}
          aria-label={t("日志")}
        >
          <ScrollText size={15} />
        </button>
        <button
          className={`icon-btn ${showSettings ? "active" : ""}`}
          onClick={onToggleSettings}
          title={t("设置")}
          aria-label={t("设置")}
        >
          <SlidersHorizontal size={15} />
        </button>
      </div>
    </header>
  );
}
