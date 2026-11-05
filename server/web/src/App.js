import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { DEFAULT_FACESWAP, DEFAULT_IMAGE, DEFAULT_VIDEO, } from "./Chips";
import Composer from "./Composer";
import Feed from "./Feed";
import { t, translateServerText, useLang } from "./i18n";
import Settings from "./Settings";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
const INITIAL = {
    runtime: {
        state: "off",
        step: "GPU 已关闭",
        error: null,
        gpu_tier: "l4",
        gpu_name: null,
        vram_used_mb: 0,
        vram_total_mb: 0,
        disk_free_gb: 0,
        disk_total_gb: 0,
        models: {},
        setup_step: null,
        uptime_s: 0,
        idle_s: 0,
        idle_timeout_s: 1800,
        active_jobs: 0,
        warm: [],
        log: [],
    },
    chats: [],
    jobs: [],
    presets: {},
    estimates: {},
};
function loadSaved(key, defaults) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? { ...defaults, ...JSON.parse(raw) } : defaults;
    }
    catch {
        return defaults;
    }
}
export default function App() {
    useLang();
    const [state, setState] = useState(INITIAL);
    const [usage, setUsage] = useState(null);
    const [usageError, setUsageError] = useState(null);
    const [mode, setMode] = useState("image");
    const [activeChat, setActiveChat] = useState(null);
    const [prompt, setPrompt] = useState("");
    const [attachments, setAttachments] = useState([]);
    const [img, setImg] = useState(() => loadSaved("studio.img.v2", DEFAULT_IMAGE));
    const [vid, setVid] = useState(() => loadSaved("studio.vid.v2", DEFAULT_VIDEO));
    const [fswap, setFswap] = useState(() => loadSaved("studio.fswap.v2", DEFAULT_FACESWAP));
    const [showLogs, setShowLogs] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [navOpen, setNavOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [banner, setBanner] = useState(null);
    const [theme, setTheme] = useState(() => localStorage.getItem("studio.theme") || "dark");
    useEffect(() => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem("studio.theme", theme);
    }, [theme]);
    useEffect(() => localStorage.setItem("studio.img.v2", JSON.stringify(img)), [img]);
    useEffect(() => localStorage.setItem("studio.vid.v2", JSON.stringify(vid)), [vid]);
    useEffect(() => localStorage.setItem("studio.fswap.v2", JSON.stringify(fswap)), [fswap]);
    const refresh = useCallback(async () => {
        try {
            const s = await api.state();
            setState(s);
        }
        catch {
            /* transient poll errors ignored */
        }
    }, []);
    useEffect(() => {
        refresh();
        const busy = state.runtime.state === "starting" ||
            state.runtime.state === "stopping" ||
            state.jobs.some((j) => j.status === "queued" || j.status === "running");
        const id = setInterval(refresh, busy ? 1500 : 4000);
        return () => clearInterval(id);
    }, [refresh, state.runtime.state, state.jobs]);
    useEffect(() => {
        const loadUsage = () => api
            .usage()
            .then((u) => {
            setUsage(u);
            setUsageError(null);
        })
            .catch((e) => setUsageError(e instanceof Error ? e.message : String(e)));
        loadUsage();
        const ms = state.runtime.state === "ready" ? 60_000 : 180_000;
        const id = setInterval(loadUsage, ms);
        return () => clearInterval(id);
    }, [state.runtime.state]);
    const switchMode = (m) => {
        setMode(m);
        setAttachments([]);
        const latest = state.chats.find((c) => c.mode === m);
        setActiveChat(latest ? latest.id : null);
    };
    const selectChat = (c) => {
        setMode(c.mode);
        setActiveChat(c.id);
    };
    const newChat = async () => {
        try {
            const c = await api.newChat(mode);
            setActiveChat(c.id);
            await refresh();
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
    };
    const deleteChat = async (id) => {
        try {
            await api.deleteChat(id);
            if (activeChat === id)
                setActiveChat(null);
            await refresh();
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
    };
    const parseSeed = (s) => (s.trim() ? Number(s) : null);
    const currentParams = () => {
        if (mode === "image")
            return { ...img, seed: parseSeed(img.seed) };
        if (mode === "video")
            return { ...vid, seed: parseSeed(vid.seed) };
        return { ...fswap };
    };
    const applyPreset = (p, targetMode = mode) => {
        const seedStr = p.seed ? String(p.seed) : "";
        if (targetMode === "image")
            setImg({ ...DEFAULT_IMAGE, ...p, seed: seedStr });
        else if (targetMode === "video")
            setVid({ ...DEFAULT_VIDEO, ...p, seed: seedStr });
        else
            setFswap({ ...DEFAULT_FACESWAP, ...p });
    };
    const savePreset = async (name) => {
        try {
            const updated = await api.savePreset(mode, name, currentParams());
            setState((s) => ({ ...s, presets: { ...s.presets, [mode]: updated } }));
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
    };
    const deletePreset = async (name) => {
        try {
            const updated = await api.deletePreset(mode, name);
            setState((s) => ({ ...s, presets: { ...s.presets, [mode]: updated } }));
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
    };
    const submit = async () => {
        setSubmitting(true);
        setBanner(null);
        try {
            const j = await api.createJob({
                chat_id: activeChat,
                kind: mode,
                prompt,
                params: currentParams(),
                inputs: attachments.map((a) => a.file),
            });
            setActiveChat(j.chat_id);
            setPrompt("");
            setAttachments([]);
            await refresh();
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
        finally {
            setSubmitting(false);
        }
    };
    const reuseImage = (file, url) => {
        setMode("image");
        setAttachments([{ file, url, name: file, kind: "image" }]);
    };
    const sendToFaceSwap = (file, url) => {
        setMode("faceswap");
        const latest = state.chats.find((c) => c.mode === "faceswap");
        setActiveChat(latest ? latest.id : null);
        setAttachments((prev) => [...prev, { file, url, name: file, kind: "image" }]);
    };
    const rerun = async (job, sameSeed) => {
        setBanner(null);
        const params = { ...(job.params || {}), seed: sameSeed ? job.params?.seed ?? null : null };
        try {
            const j = await api.createJob({
                chat_id: job.chat_id,
                kind: job.kind,
                prompt: job.prompt,
                params,
                inputs: job.inputs,
            });
            setActiveChat(j.chat_id);
            await refresh();
        }
        catch (e) {
            setBanner(e instanceof Error ? e.message : String(e));
        }
    };
    const lockSeed = (job) => {
        applyPreset(job.params || {}, job.kind);
        if (job.prompt)
            setPrompt(job.prompt);
    };
    const visibleJobs = state.jobs.filter((j) => activeChat ? j.chat_id === activeChat : j.kind === mode && !j.chat_id);
    return (_jsxs("div", { className: "layout", children: [navOpen && _jsx("div", { className: "drawer-backdrop", onClick: () => setNavOpen(false) }), _jsx(Sidebar, { mode: mode, onMode: switchMode, chats: state.chats, activeChat: activeChat, onSelectChat: selectChat, onNewChat: newChat, onDeleteChat: deleteChat, open: navOpen, onClose: () => setNavOpen(false) }), _jsxs("div", { className: "main", children: [_jsx(TopBar, { rt: state.runtime, usage: usage, usageError: usageError, startupEstimates: state.startup_estimates, onStart: () => api
                            .startGpu()
                            .then(refresh)
                            .catch((e) => setBanner(e instanceof Error ? e.message : String(e))), onStop: () => {
                            if (!window.confirm(t("确定关闭 GPU 吗？正在运行的任务将被中止。")))
                                return;
                            api
                                .stopGpu()
                                .then(refresh)
                                .catch((e) => setBanner(e instanceof Error ? e.message : String(e)));
                        }, showLogs: showLogs, onToggleLogs: () => setShowLogs((v) => !v), showSettings: showSettings, onToggleSettings: () => setShowSettings((v) => !v), onToggleNav: () => setNavOpen((v) => !v), theme: theme, onTheme: setTheme }), (banner || state.runtime.error) && (_jsxs("div", { className: "banner", children: [_jsx("span", { children: banner || t("GPU 错误: {detail}", { detail: translateServerText(state.runtime.error || "") }) }), _jsx("button", { onClick: () => setBanner(null), children: "\u00D7" })] })), _jsxs("div", { className: "workspace", children: [_jsxs("div", { className: "center", children: [_jsx("div", { className: "scroll-area", children: _jsx(Feed, { mode: mode, jobs: visibleJobs, allJobs: state.jobs, runtime: state.runtime, estimates: state.estimates, startupEstimates: state.startup_estimates, onSelectPrompt: setPrompt, onReuseImage: reuseImage, onSendToFaceSwap: sendToFaceSwap, onCancel: (id) => {
                                                if (!window.confirm(t("确定取消该任务吗？")))
                                                    return;
                                                api
                                                    .cancelJob(id)
                                                    .then(refresh)
                                                    .catch((e) => setBanner(e instanceof Error ? e.message : String(e)));
                                            }, onRerun: rerun, onLockSeed: lockSeed }) }), _jsx("div", { className: "composer-dock", children: _jsx(Composer, { mode: mode, prompt: prompt, onPrompt: setPrompt, attachments: attachments, onAttachments: setAttachments, img: img, onImg: setImg, vid: vid, onVid: setVid, fswap: fswap, onFswap: setFswap, estimates: state.estimates, warm: state.runtime.warm, presets: state.presets[mode] || {}, onApplyPreset: (p) => applyPreset(p, mode), onOpenSettings: () => setShowSettings(true), onSubmit: submit, onError: setBanner, submitting: submitting }) })] }), showSettings && (_jsx(Settings, { mode: mode, img: img, onImg: setImg, vid: vid, onVid: setVid, fswap: fswap, onFswap: setFswap, presets: state.presets[mode] || {}, onSavePreset: savePreset, onDeletePreset: deletePreset, onApplyPreset: (p) => applyPreset(p, mode), onClose: () => setShowSettings(false) }))] }), showLogs && (_jsxs("div", { className: "log-drawer", children: [_jsxs("div", { className: "log-head", children: [_jsx("span", { children: t("日志") }), _jsx("button", { className: "icon-btn", onClick: () => setShowLogs(false), "aria-label": t("关闭"), children: "\u00D7" })] }), _jsx("pre", { className: "log-body", children: state.runtime.log.length ? state.runtime.log.join("\n") : t("暂无日志。") })] }))] })] }));
}
