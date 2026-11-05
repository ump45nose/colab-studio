import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Coins, Cpu, HardDrive, Loader2, Package, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fmtDuration, fmtHours } from "./format";
import { t, translateServerText, useLang } from "./i18n";
const PACK_NAMES = {
    image: "图片 (Krea2-Noct)",
    image_turbo: "极速图片 (Z-Image-Turbo)",
    video: "视频 (MiniMax-H3)",
    video_wan22: "视频 (Wan2.2-Remix)",
};
const PACK_ORDER = ["image", "image_turbo", "video", "video_wan22"];
function usePopover() {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        if (!open)
            return;
        const onDoc = (e) => {
            if (ref.current && !ref.current.contains(e.target))
                setOpen(false);
        };
        const onKey = (e) => {
            if (e.key === "Escape")
                setOpen(false);
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
export function startupRemaining(rt, startupEstimates) {
    if (rt.state !== "starting")
        return null;
    const bootExp = startupEstimates?.boot?.expected ?? 180;
    return Math.max(5, bootExp - rt.uptime_s);
}
export function StartupPill({ rt, startupEstimates, }) {
    useLang();
    const { open, setOpen, ref } = usePopover();
    if (rt.state !== "starting")
        return null;
    const rem = startupRemaining(rt, startupEstimates) ?? 60;
    const bootExp = startupEstimates?.boot?.expected ?? 180;
    const pct = Math.min(95, Math.round((rt.uptime_s / bootExp) * 100));
    const stepText = translateServerText(rt.setup_step || rt.step);
    return (_jsxs("div", { className: "pop-anchor", ref: ref, children: [_jsxs("button", { type: "button", className: "meta-pill meta-pill-btn startup-pill", onClick: () => setOpen(!open), title: t("启动详情"), children: [_jsx(Loader2, { size: 12, className: "spin" }), _jsx("span", { children: stepText }), _jsxs("span", { className: "pill-dim", children: ["\u00B7 ~", fmtDuration(rem)] })] }), open && (_jsxs("div", { className: "popover", children: [_jsxs("div", { className: "pop-head", children: [_jsx("span", { children: t("正在启动 GPU") }), _jsx("button", { className: "icon-btn", onClick: () => setOpen(false), "aria-label": t("关闭详情"), children: _jsx(X, { size: 13 }) })] }), _jsxs("div", { className: "pop-row", children: [_jsx("span", { children: stepText }), _jsxs("span", { className: "mono", children: [pct, "%"] })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${Math.max(6, pct)}%` } }) }), _jsx("div", { className: "pop-sub", children: t("预计剩余 ~{left} · 已耗时 {elapsed}", {
                            left: fmtDuration(rem),
                            elapsed: fmtDuration(rt.uptime_s),
                        }) })] }))] }));
}
export function GpuStatsPill({ rt }) {
    useLang();
    const { open, setOpen, ref } = usePopover();
    if (rt.state !== "ready")
        return null;
    const vramGb = (rt.vram_used_mb / 1024).toFixed(1);
    const vramTotGb = (rt.vram_total_mb / 1024).toFixed(0);
    const vramPct = rt.vram_total_mb > 0 ? Math.round((rt.vram_used_mb / rt.vram_total_mb) * 100) : 0;
    const diskUsedGb = Math.max(0, rt.disk_total_gb - rt.disk_free_gb);
    const diskPct = rt.disk_total_gb > 0 ? Math.round((diskUsedGb / rt.disk_total_gb) * 100) : 0;
    return (_jsxs("div", { className: "pop-anchor", ref: ref, children: [_jsxs("button", { type: "button", className: "meta-pill meta-pill-btn", onClick: () => setOpen(!open), title: t("GPU 与系统详情"), children: [_jsx(Cpu, { size: 12 }), _jsxs("span", { children: ["VRAM ", vramGb, "/", vramTotGb, " GB"] })] }), open && (_jsxs("div", { className: "popover", children: [_jsxs("div", { className: "pop-head", children: [_jsx("span", { children: t("GPU 与系统") }), _jsx("button", { className: "icon-btn", onClick: () => setOpen(false), "aria-label": t("关闭详情"), children: _jsx(X, { size: 13 }) })] }), _jsxs("div", { className: "pop-row", children: [_jsx("span", { children: "VRAM" }), _jsxs("span", { className: "mono", children: [vramGb, " / ", vramTotGb, " GB (", vramPct, "%)"] })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${vramPct}%` } }) }), rt.disk_total_gb > 0 && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "pop-row", style: { marginTop: 8 }, children: [_jsxs("span", { children: [_jsx(HardDrive, { size: 12, style: { verticalAlign: "-2px" } }), " ", t("磁盘")] }), _jsxs("span", { className: "mono", children: [diskUsedGb.toFixed(1), " / ", rt.disk_total_gb.toFixed(0), " GB (", diskPct, "%)"] })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${diskPct}%` } }) })] }))] }))] }));
}
export function ModelPackPill({ rt, }) {
    useLang();
    const { open, setOpen, ref } = usePopover();
    const packs = rt.models?.packs || {};
    const entries = PACK_ORDER.filter((k) => k in packs).map((k) => [k, packs[k]]);
    if (entries.length === 0)
        return null;
    const readyCount = entries.filter(([, p]) => p.ready).length;
    const activeEntry = entries.find(([, p]) => p.current && !p.ready);
    return (_jsxs("div", { className: "pop-anchor", ref: ref, children: [_jsxs("button", { type: "button", className: "meta-pill meta-pill-btn", onClick: () => setOpen(!open), title: t("模型详情"), children: [_jsx(Package, { size: 12 }), activeEntry ? (_jsxs("span", { children: [t(PACK_NAMES[activeEntry[0]] || activeEntry[0]), ": ", activeEntry[1].done_gb, "/", activeEntry[1].total_gb, " GB"] })) : (_jsxs("span", { children: [t("模型"), " ", t("{n}/{total} 已就绪", { n: readyCount, total: entries.length })] }))] }), open && (_jsxs("div", { className: "popover", children: [_jsxs("div", { className: "pop-head", children: [_jsx("span", { children: t("模型包") }), _jsx("button", { className: "icon-btn", onClick: () => setOpen(false), "aria-label": t("关闭详情"), children: _jsx(X, { size: 13 }) })] }), entries.map(([k, p]) => {
                        const pct = p.total_gb > 0 ? Math.min(100, Math.round((p.done_gb / p.total_gb) * 100)) : 0;
                        return (_jsxs("div", { className: "pack-item", children: [_jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t(PACK_NAMES[k] || k) }), _jsx("span", { className: "mono", children: p.ready ? t("已就绪 ✓") : `${p.done_gb}/${p.total_gb} GB (${pct}%)` })] }), !p.ready && (_jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${pct}%` } }) }))] }, k));
                    })] }))] }));
}
export function CreditPill({ usage, error, }) {
    useLang();
    const { open, setOpen, ref } = usePopover();
    if (!usage && !error)
        return null;
    return (_jsxs("div", { className: "pop-anchor", ref: ref, children: [_jsxs("button", { type: "button", className: "meta-pill meta-pill-btn", onClick: () => setOpen(!open), title: t("算力单元详情"), children: [_jsx(Coins, { size: 12 }), usage ? (_jsxs("span", { children: [usage.balance.toFixed(1), " CU", usage.remaining_hours_active !== null && (_jsxs("span", { className: "pill-dim", children: [" \u00B7 ", t("可用 {d}", { d: fmtHours(usage.remaining_hours_active) })] }))] })) : (_jsx("span", { children: t("无法读取算力余额") }))] }), open && (_jsxs("div", { className: "popover", children: [_jsxs("div", { className: "pop-head", children: [_jsx("span", { children: t("算力余额") }), _jsx("button", { className: "icon-btn", onClick: () => setOpen(false), "aria-label": t("关闭详情"), children: _jsx(X, { size: 13 }) })] }), error && _jsx("div", { className: "pop-err", children: translateServerText(error) }), usage && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t("当前余额") }), _jsxs("span", { className: "mono", children: [usage.balance.toFixed(2), " CU"] })] }), _jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t("每小时消耗") }), _jsx("span", { className: "mono", children: t("{n} CU/小时", { n: usage.current_burn_rate }) })] }), usage.remaining_hours_active !== null && (_jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t("按当前速率可用") }), _jsx("span", { className: "mono", children: fmtHours(usage.remaining_hours_active) })] })), _jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t("本次会话已用") }), _jsxs("span", { className: "mono", children: [usage.session_used.toFixed(2), " CU"] })] }), _jsxs("div", { className: "pop-row", children: [_jsx("span", { children: t("今日已用") }), _jsxs("span", { className: "mono", children: [usage.today_used.toFixed(2), " CU"] })] })] }))] }))] }));
}
