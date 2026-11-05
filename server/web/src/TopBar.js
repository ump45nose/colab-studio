import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Cpu, Menu, Power, ScrollText, SlidersHorizontal } from "lucide-react";
import { fmtDuration } from "./format";
import { LANGS, t, useLang } from "./i18n";
import { CreditPill, GpuStatsPill, ModelPackPill, StartupPill } from "./SystemPanel";
const STATE_LABEL = {
    off: "GPU 已关闭",
    starting: "正在启动 GPU",
    ready: "已就绪",
    stopping: "正在关闭",
    error: "错误",
};
const THEMES = [
    { id: "dark", label: "深色" },
    { id: "dim", label: "暗灰" },
    { id: "light", label: "浅色" },
];
export default function TopBar({ rt, usage, usageError, startupEstimates, onStart, onStop, showLogs, onToggleLogs, showSettings, onToggleSettings, onToggleNav, theme, onTheme, }) {
    const [lang, setLang] = useLang();
    const busy = rt.state === "starting" || rt.state === "stopping";
    const idleLeftMin = rt.state === "ready" && rt.active_jobs === 0 && rt.idle_timeout_s > 0
        ? Math.max(1, Math.ceil((rt.idle_timeout_s - rt.idle_s) / 60))
        : null;
    const idleMaxMin = Math.round(rt.idle_timeout_s / 60);
    const idleElapsedMin = Math.floor(rt.idle_s / 60);
    return (_jsxs("header", { className: "topbar", children: [_jsxs("div", { className: "topbar-left", children: [_jsx("button", { className: "icon-btn nav-toggle", onClick: onToggleNav, title: t("菜单"), "aria-label": t("菜单"), children: _jsx(Menu, { size: 16 }) }), _jsxs("div", { className: `gpu-badge state-${rt.state}`, children: [_jsx("span", { className: "gpu-dot" }), _jsx(Cpu, { size: 14 }), _jsx("span", { className: "gpu-label", children: rt.state === "ready" && rt.gpu_name ? `${rt.gpu_name} · ${t("已就绪")}` : t(STATE_LABEL[rt.state]) })] }), rt.state === "off" || rt.state === "error" ? (_jsxs("button", { className: "btn-ghost", onClick: onStart, children: [_jsx(Power, { size: 13 }), " ", t("启动 {gpu}", { gpu: rt.gpu_tier.toUpperCase() })] })) : (_jsxs("button", { className: "btn-ghost", onClick: onStop, disabled: busy, children: [_jsx(Power, { size: 13 }), " ", t("关闭")] })), _jsx(StartupPill, { rt: rt, startupEstimates: startupEstimates }), _jsx(GpuStatsPill, { rt: rt }), _jsx(ModelPackPill, { rt: rt, startupEstimates: startupEstimates })] }), _jsxs("div", { className: "topbar-right", children: [idleLeftMin !== null && (_jsxs("span", { className: "meta-pill", title: `${t("空闲 {n}/{max} 分钟", { n: idleElapsedMin, max: idleMaxMin })} · ${t("空闲满 {n} 分钟自动关闭 GPU", { n: idleMaxMin })} (${t("剩余 {d}", { d: fmtDuration(rt.idle_timeout_s - rt.idle_s) })})`, children: [t("自动关闭"), " ", idleLeftMin, "m"] })), _jsx(CreditPill, { usage: usage, error: usageError }), _jsx("div", { className: "theme-seg", role: "group", "aria-label": "Language", children: LANGS.map((l) => (_jsx("button", { className: `theme-btn ${lang === l ? "active" : ""}`, onClick: () => setLang(l), title: l === "zh" ? "中文" : "English", children: l.toUpperCase() }, l))) }), _jsx("div", { className: "theme-seg", role: "group", children: THEMES.map((th) => (_jsx("button", { className: `theme-btn ${theme === th.id ? "active" : ""}`, onClick: () => onTheme(th.id), title: t(th.label), children: t(th.label) }, th.id))) }), _jsx("button", { className: `icon-btn ${showLogs ? "active" : ""}`, onClick: onToggleLogs, title: t("日志"), "aria-label": t("日志"), children: _jsx(ScrollText, { size: 15 }) }), _jsx("button", { className: `icon-btn ${showSettings ? "active" : ""}`, onClick: onToggleSettings, title: t("设置"), "aria-label": t("设置"), children: _jsx(SlidersHorizontal, { size: 15 }) })] })] }));
}
