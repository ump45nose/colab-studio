import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { AlertTriangle, Copy, Download, Lock, Pencil, RefreshCw, RotateCcw, Sparkles, Square, ZoomIn, } from "lucide-react";
import { useEffect, useState } from "react";
import { fmtDuration } from "./format";
import { t, translateServerText, useLang } from "./i18n";
import { startupRemaining } from "./SystemPanel";
const SUGGESTIONS = {
    image: {
        title: "你想生成或编辑什么画面？",
        sub: "支持 Krea2-Noct V4（文生图 + 多参考图智能编辑）与 Z-Image-Turbo NSFW（8 步极速生图）。点击左下角回形针可上传参考图进入修图模式。",
        prompts: [
            "雨夜东京霓虹街头，电影感特写人像，柔和散景，85mm镜头",
            "清晨阳光洒在木桌上的手冲咖啡器具，商业摄影质感",
            "漫步在薄雾松林中的红衣女子，广角构图，胶片颗粒",
        ],
    },
    video: {
        title: "今天拍哪一幕镜头？",
        sub: "内置 MiniMax-H3（音画同步生成，支持首尾帧控制）与 Wan2.2-Remix A14B（高低噪双阶段 FP8 图生视频/文生视频）。",
        prompts: [
            "黄昏海面上缓慢航行的渡轮，海鸥掠过水面，镜头平稳横移",
            "雨夜小巷里撑伞独行的男子，脚步声与远处的爵士乐，电影级光影",
            "特写镜头：微风吹动窗边的白色纱帘，阳光斑驳移动",
        ],
    },
    faceswap: {
        title: "全自动远程 GPU 换脸流水线",
        sub: "请点击回形针：第 1 张（或前几张）上传【源人脸图片】，最后 1 个上传【目标图片或视频】。支持 HyperSwap 1A / AlphaFace / InSwapper 同管道三底模对比，复杂遮挡镜头可一键下载至本地 VisoMaster-Fusion 手工画遮罩精修。",
        prompts: [],
    },
};
const KIND_LABEL = {
    image: "图片",
    video: "视频",
    faceswap: "换脸",
};
function stripIndexPrefix(stage) {
    const m = stage.match(/^(\[\d+\/\d+\]\s*)(.*)$/);
    if (!m)
        return { prefix: "", clean: stage };
    return { prefix: m[1], clean: m[2] };
}
function baseStageName(clean) {
    return clean.replace(/\s*\([^)]*\)\s*$/, "").trim();
}
function estimateSingleJob(job, estimates, warm) {
    const stages = job.stages || ["正在加载模型", "正在生成", "正在保存"];
    let total = 0;
    for (const s of stages) {
        const e = estimates[`${job.kind}:${s}`];
        if (e)
            total += warm ? e.warm : e.cold;
        else
            total += s === "正在加载模型" ? (warm ? 2 : 25) : s.startsWith("正在生成") ? 60 : 5;
    }
    const count = Number(job.params?.count ?? 1);
    return total * Math.max(1, count);
}
export default function Feed({ mode, jobs, allJobs, runtime, estimates, startupEstimates, onSelectPrompt, onReuseImage, onSendToFaceSwap, onCancel, onRerun, onLockSeed, }) {
    useLang();
    const [lightbox, setLightbox] = useState(null);
    const [now, setNow] = useState(() => Date.now() / 1000);
    const hasActive = runtime.state === "starting" ||
        allJobs.some((j) => j.status === "running" || j.status === "queued");
    useEffect(() => {
        if (!hasActive)
            return;
        const id = setInterval(() => setNow(Date.now() / 1000), 1000);
        return () => clearInterval(id);
    }, [hasActive]);
    if (jobs.length === 0) {
        const s = SUGGESTIONS[mode];
        return (_jsxs("div", { className: "empty-state", children: [_jsx("h2", { children: t(s.title) }), _jsx("p", { children: t(s.sub) }), s.prompts.length > 0 && (_jsx("div", { className: "suggestions", children: s.prompts.map((p) => {
                        const tp = t(p);
                        return (_jsx("button", { className: "suggestion", onClick: () => onSelectPrompt(tp), children: tp }, p));
                    }) }))] }));
    }
    return (_jsxs("div", { className: "feed", children: [jobs.map((j) => (_jsx(JobCard, { job: j, allJobs: allJobs, runtime: runtime, estimates: estimates, startupEstimates: startupEstimates, now: now, onZoom: setLightbox, onReusePrompt: onSelectPrompt, onReuseImage: onReuseImage, onSendToFaceSwap: onSendToFaceSwap, onCancel: onCancel, onRerun: onRerun, onLockSeed: onLockSeed }, j.id))), lightbox && (_jsx("div", { className: "lightbox", onClick: () => setLightbox(null), children: _jsx("img", { src: lightbox, alt: "" }) }))] }));
}
function QueuedStatus({ job, allJobs, runtime, estimates, startupEstimates, now, }) {
    const active = allJobs
        .filter((j) => j.status === "running" || j.status === "queued")
        .sort((a, b) => a.created_at - b.created_at);
    const idx = active.findIndex((j) => j.id === job.id);
    const ahead = idx > 0 ? active.slice(0, idx) : [];
    const running = active.find((j) => j.status === "running");
    let waitSec = 0;
    const bootLeft = startupRemaining(runtime, startupEstimates);
    if (bootLeft !== null)
        waitSec += bootLeft;
    for (const a of ahead) {
        const total = estimateSingleJob(a, estimates, runtime.warm.includes(a.kind));
        if (a.status === "running" && a.started_at) {
            const elapsed = Math.max(0, now - a.started_at);
            const byPct = a.progress > 5 ? (elapsed * (100 - a.progress)) / a.progress : total - elapsed;
            waitSec += Math.max(5, byPct);
        }
        else {
            waitSec += total;
        }
    }
    const posText = ahead.length === 0 ? t("排队中") : `${t("排队中")} · ${t("前方还有 {n} 个任务", { n: ahead.length })}`;
    let blockerText = null;
    if (runtime.state === "starting") {
        blockerText = `${t("当前：正在启动 GPU")} (${translateServerText(runtime.setup_step || runtime.step)})`;
    }
    else if (running && running.id !== job.id) {
        const kindLbl = t(KIND_LABEL[running.kind] || running.kind);
        const stg = translateServerText(running.stage || t("运行中"));
        const pct = running.progress > 0 ? `${running.progress}%` : "";
        blockerText = t("当前：{kind} — {stage} {pct}", { kind: kindLbl, stage: stg, pct }).trim();
    }
    const etaText = waitSec > 3 ? t("预计 ~{d} 后开始", { d: fmtDuration(waitSec) }) : t("即将开始");
    return (_jsxs("div", { className: "job-progress", children: [_jsxs("div", { className: "progress-head", children: [_jsxs("span", { children: [posText, blockerText && _jsxs("span", { className: "progress-sub", children: [" \u00B7 ", blockerText] })] }), _jsx("span", { className: "progress-eta", children: etaText })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill indeterminate", style: { width: "25%" } }) })] }));
}
function RunningStatus({ job, runtime, estimates, startupEstimates, now, }) {
    const elapsed = job.started_at ? Math.max(0, now - job.started_at) : 0;
    const stageElapsed = job.stage_started_at ? Math.max(0, now - job.stage_started_at) : elapsed;
    const rawStage = job.stage || t("运行中");
    const { prefix, clean } = stripIndexPrefix(rawStage);
    const baseName = baseStageName(clean);
    const displayStage = prefix + translateServerText(clean);
    if (runtime.state === "starting") {
        const bootLeft = startupRemaining(runtime, startupEstimates);
        const bootExp = startupEstimates?.boot?.expected ?? 180;
        const bootPct = Math.min(95, Math.round((runtime.uptime_s / bootExp) * 100));
        const stepLbl = translateServerText(runtime.setup_step || runtime.step);
        return (_jsxs("div", { className: "job-progress", children: [_jsxs("div", { className: "progress-head", children: [_jsx("span", { children: t("正在启动 GPU：{step} · {pct}% · 剩余 ~{left}", {
                                step: stepLbl,
                                pct: bootPct,
                                left: fmtDuration(bootLeft ?? 60),
                            }) }), _jsx("span", { className: "progress-eta", children: fmtDuration(elapsed) })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${Math.max(6, bootPct)}%` } }) })] }));
    }
    const stages = job.stages || [];
    const curIdx = stages.indexOf(baseName);
    const warm = job.warm ?? runtime.warm.includes(job.kind);
    const stageEst = (s) => {
        const e = estimates[`${job.kind}:${s}`];
        if (!e)
            return { sec: 20, known: false };
        return { sec: warm ? e.warm : e.cold, known: e.samples > 0 };
    };
    const curExpected = curIdx >= 0 ? stageEst(baseName) : { sec: 30, known: false };
    let remSec = 0;
    if (job.progress > 5 && job.progress < 100 && stageElapsed > 2) {
        remSec = Math.max(1, (stageElapsed * (100 - job.progress)) / job.progress);
    }
    else if (curIdx >= 0) {
        const curLeft = Math.max(1, curExpected.sec - stageElapsed);
        let afterSec = 0;
        for (let i = curIdx + 1; i < stages.length; i++) {
            afterSec += stageEst(stages[i]).sec;
        }
        remSec = curLeft + afterSec;
    }
    const overRatio = curExpected.sec > 5 ? stageElapsed / curExpected.sec : 0;
    const vramLow = runtime.vram_total_mb > 0 && runtime.vram_used_mb < 500;
    const stallWarn = overRatio > 2.5 && stageElapsed > 90 && vramLow;
    const slowNote = !stallWarn && overRatio > 1.6 && stageElapsed > 30;
    let pct = job.progress;
    if (pct === 0 && stages.length > 0 && curIdx >= 0) {
        const totalExpected = stages.reduce((acc, s) => acc + stageEst(s).sec, 0) || 1;
        const doneBefore = stages.slice(0, curIdx).reduce((acc, s) => acc + stageEst(s).sec, 0);
        const inCur = Math.min(curExpected.sec * 0.9, stageElapsed);
        pct = Math.min(95, Math.round(((doneBefore + inCur) / totalExpected) * 100));
    }
    let rightText = fmtDuration(elapsed);
    if (remSec > 0) {
        rightText = `${remSec < 3 ? t("即将完成") : t("剩余 ~{d}", { d: fmtDuration(remSec) })} · ${fmtDuration(elapsed)}`;
    }
    const stageSub = stageElapsed >= 3 && curIdx >= 0
        ? ` · ${t("当前阶段已用 {d}", { d: fmtDuration(stageElapsed) })}${curExpected.sec >= 5 ? ` (${t("通常约 ~{d}", { d: fmtDuration(curExpected.sec) })})` : ""}`
        : "";
    return (_jsxs("div", { className: "job-progress", children: [_jsxs("div", { className: "progress-head", children: [_jsxs("span", { children: [displayStage, _jsx("span", { className: "progress-sub", children: stageSub })] }), _jsx("span", { className: "progress-eta", children: rightText })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: `progress-fill ${pct === 0 ? "indeterminate" : ""}`, style: { width: `${Math.max(pct, 6)}%` } }) }), (stallWarn || slowNote) && (_jsxs("div", { className: `progress-note ${stallWarn ? "warn" : ""}`, children: [_jsx(AlertTriangle, { size: 12 }), stallWarn
                        ? t("耗时远超预期且 GPU 显存空闲，任务可能卡住，建议取消后重试")
                        : t("耗时略长于预期，任务仍在运行中")] }))] }));
}
function JobCard({ job, allJobs, runtime, estimates, startupEstimates, now, onZoom, onReusePrompt, onReuseImage, onSendToFaceSwap, onCancel, onRerun, onLockSeed, }) {
    const active = job.status === "queued" || job.status === "running";
    const dur = job.started_at && job.finished_at ? Math.max(1, Math.round(job.finished_at - job.started_at)) : null;
    const p = job.params || {};
    const badges = [];
    if (job.kind === "image") {
        const prof = String(p.profile || "krea2_noct");
        badges.push(prof === "z_image_turbo_nsfw" ? "Z-Image-Turbo" : "Krea2-Noct V4");
        if (job.inputs.length > 0) {
            badges.push(t("修图"), `${p.edit_resolution ?? 1080}p`);
        }
        else {
            if (p.ratio)
                badges.push(String(p.ratio));
            if (p.size)
                badges.push(`${p.size}px`);
        }
        if (p.turbo)
            badges.push("Turbo");
        if (p.steps)
            badges.push(t("{n} 步", { n: Number(p.steps) }));
        if (p.cfg !== undefined)
            badges.push(`CFG ${p.cfg}`);
        if (p.seed)
            badges.push(`seed ${p.seed}`);
    }
    else if (job.kind === "video") {
        const prof = String(p.profile || "minimax_h3");
        badges.push(prof === "wan22_remix" ? "Wan2.2-Remix" : "MiniMax-H3");
        if (p.resolution)
            badges.push(String(p.resolution));
        if (p.ratio)
            badges.push(String(p.ratio));
        if (p.seconds)
            badges.push(`${p.seconds}s`);
        badges.push(p.quality === "quality" ? t("20 步") : "Turbo");
        if (p.seed)
            badges.push(`seed ${p.seed}`);
    }
    else if (job.kind === "faceswap") {
        const eng = String(p.engine || "facefusion_cli");
        badges.push(eng === "dreamid_v_faster" ? "DreamID-V Faster (81帧切片)" : "FaceFusion CLI");
        if (eng === "facefusion_cli") {
            badges.push(p.compare_all ? t("三底模同管道对比") : String(p.swapper_model || "hyperswap_1a_256"));
            if (p.pixel_boost)
                badges.push(`Boost ${p.pixel_boost}`);
            if (p.enhancer_model && p.enhancer_model !== "none") {
                badges.push(`${p.enhancer_model} (${p.enhancer_blend ?? 50}%)`);
            }
            else {
                badges.push(t("底模直出（无增强）"));
            }
        }
    }
    return (_jsxs("article", { className: "job-card", children: [_jsxs("header", { className: "job-head", children: [_jsxs("div", { className: "job-prompt-wrap", children: [job.inputs.length > 0 && (_jsx("div", { className: "job-inputs", children: job.inputs.map((f, idx) => {
                                    const isVid = /\.(mp4|webm|mov)$/i.test(f);
                                    const roleTag = job.kind === "faceswap"
                                        ? idx === job.inputs.length - 1
                                            ? t("目标")
                                            : t("源#{n}", { n: idx + 1 })
                                        : null;
                                    return (_jsxs("div", { className: "job-input-thumb-wrap", children: [isVid ? (_jsx("video", { src: `/media/${f}`, className: "job-input-thumb", muted: true, playsInline: true })) : (_jsx("img", { src: `/media/${f}`, alt: "", className: "job-input-thumb", onClick: () => onZoom(`/media/${f}`) })), roleTag && _jsx("span", { className: "job-input-tag", children: roleTag })] }, f));
                                }) })), _jsxs("div", { children: [_jsx("p", { className: "job-prompt", children: translateServerText(job.prompt) }), badges.length > 0 && (_jsx("div", { className: "job-badges", children: badges.map((b, i) => (_jsx("span", { className: "param-badge", children: b }, i))) }))] })] }), _jsxs("div", { className: "job-meta", children: [dur !== null && (_jsx("span", { className: "job-dur", title: t("耗时 {n} 秒", { n: dur }), children: fmtDuration(dur) })), _jsxs("div", { className: "job-actions", children: [!active && (_jsxs(_Fragment, { children: [_jsx("button", { className: "icon-btn", onClick: () => onRerun(job, false), title: t("重新生成"), "aria-label": t("重新生成"), children: _jsx(RefreshCw, { size: 13 }) }), job.prompt && (_jsx("button", { className: "icon-btn", onClick: () => onReusePrompt(job.prompt), title: t("复用提示词"), "aria-label": t("复用提示词"), children: _jsx(Copy, { size: 13 }) })), Boolean(p.seed) && (_jsx("button", { className: "icon-btn", onClick: () => onLockSeed(job), title: t("锁定此结果的 Seed 与参数，方便微调提示词"), "aria-label": t("锁定 Seed"), children: _jsx(Lock, { size: 13 }) }))] })), (job.status === "error" || job.status === "cancelled") && (_jsxs("button", { className: "btn-ghost", onClick: () => onRerun(job, true), children: [_jsx(RotateCcw, { size: 12 }), " ", t("重试")] })), active && (_jsxs("button", { className: "btn-ghost btn-cancel", onClick: () => onCancel(job.id), title: t("中止当前任务；GPU 保持开启"), children: [_jsx(Square, { size: 11 }), " ", t("取消")] }))] })] })] }), job.status === "queued" && (_jsx(QueuedStatus, { job: job, allJobs: allJobs, runtime: runtime, estimates: estimates, startupEstimates: startupEstimates, now: now })), job.status === "running" && (_jsx(RunningStatus, { job: job, runtime: runtime, estimates: estimates, startupEstimates: startupEstimates, now: now })), (job.status === "error" || job.status === "cancelled") && (_jsx("div", { className: `job-error ${job.status === "cancelled" ? "cancelled" : ""}`, children: translateServerText(job.error || "") })), job.outputs.length > 0 && (_jsx("div", { className: `job-outputs count-${Math.min(job.outputs.length, 4)}`, children: job.outputs.map((o) => (_jsxs("div", { className: "output-item", children: [o.label && _jsx("div", { className: "output-model-badge", children: o.label }), o.kind === "image" && (_jsxs(_Fragment, { children: [_jsx("img", { src: o.url, alt: job.prompt, loading: "lazy", onClick: () => onZoom(o.url) }), _jsxs("div", { className: "output-overlay", children: [_jsx("button", { onClick: () => onZoom(o.url), title: t("放大查看"), "aria-label": t("放大查看"), children: _jsx(ZoomIn, { size: 14 }) }), _jsx("button", { onClick: () => onReuseImage(o.file, o.url), title: t("编辑此图"), "aria-label": t("编辑此图"), children: _jsx(Pencil, { size: 14 }) }), _jsx("button", { onClick: () => onSendToFaceSwap(o.file, o.url), title: t("发送到换脸流水线"), "aria-label": t("发送到换脸流水线"), children: _jsx(Sparkles, { size: 14 }) }), _jsx("a", { href: o.url, download: o.file, title: t("下载（可用于本地 VisoMaster-Fusion 精修）"), "aria-label": t("下载"), children: _jsx(Download, { size: 14 }) })] })] })), o.kind === "video" && (_jsxs("div", { className: "video-wrap", children: [_jsx("video", { src: o.url, controls: true, playsInline: true, loop: true }), _jsx("div", { className: "video-actions-bar", children: _jsxs("a", { className: "btn-ghost", href: o.url, download: o.file, title: t("下载视频（复杂遮挡镜头可在本地 VisoMaster-Fusion 手工画遮罩精修）"), children: [_jsx(Download, { size: 13 }), " ", t("下载视频 / 本地精修")] }) })] }))] }, o.file))) }))] }));
}
