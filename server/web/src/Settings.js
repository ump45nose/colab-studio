import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Bookmark, HelpCircle, RotateCcw, Shuffle, Trash2, X, Zap } from "lucide-react";
import { useState } from "react";
import { DEFAULT_FACESWAP, DEFAULT_IMAGE, DEFAULT_VIDEO, EDIT_RES_INFO, ENHANCER_OPTIONS, IMAGE_SIZE_INFO, PIXEL_BOOST_OPTIONS, SWAPPER_MODEL_INFO, } from "./Chips";
import { t, useLang } from "./i18n";
const SAMPLER_INFO = [
    { id: "euler", label: "Euler", note: "推荐默认，稳定且可预测" },
    { id: "euler_ancestral", label: "Euler A", note: "每步注入少量噪声，细节更生动" },
    { id: "res_multistep", label: "RES multistep", note: "Z-Image-Turbo 推荐，低步数锐度高" },
    { id: "dpmpp_2m", label: "DPM++ 2M", note: "细节扎实干净，通用性好" },
    { id: "dpmpp_2m_sde", label: "DPM++ 2M SDE", note: "纹理丰富，适合写实人像" },
    { id: "er_sde", label: "ER SDE", note: "过渡柔和，适合特写肖像" },
    { id: "uni_pc", label: "UniPC", note: "适合 10-15 步快速预览" },
];
const SCHEDULER_INFO = [
    { id: "simple", label: "Simple", note: "推荐默认" },
    { id: "beta", label: "Beta", note: "首尾步数更密集，可增强细节" },
    { id: "normal", label: "Normal", note: "均匀步长分布" },
    { id: "karras", label: "Karras", note: "尾段精细采样" },
    { id: "sgm_uniform", label: "SGM uniform", note: "Flow 模型常用均匀调度" },
];
const IMAGE_PRESETS = [
    { name: "Turbo", apply: { turbo: true, steps: 8, cfg: 1.0, sampler: "euler", scheduler: "simple" } },
    { name: "快速", apply: { turbo: false, steps: 20, cfg: 1.0, sampler: "euler", scheduler: "simple" } },
    { name: "精细", apply: { turbo: false, steps: 28, cfg: 3.0, sampler: "euler", scheduler: "simple" } },
    { name: "草稿", apply: { turbo: false, steps: 12, cfg: 1.0, sampler: "uni_pc", scheduler: "simple" } },
];
function Field({ label, help, children }) {
    const [open, setOpen] = useState(false);
    return (_jsxs("div", { className: "field", children: [_jsxs("div", { className: "field-head", children: [_jsx("span", { children: label }), help && (_jsx("button", { type: "button", className: `help-btn ${open ? "active" : ""}`, onClick: () => setOpen((v) => !v), "aria-label": t("查看说明"), children: _jsx(HelpCircle, { size: 12 }) }))] }), open && help && _jsx("p", { className: "field-help", children: help }), children] }));
}
function SeedField({ value, onChange, help, }) {
    const roll = () => onChange(String(Math.floor(1 + Math.random() * 4294967294)));
    return (_jsx(Field, { label: "Seed", help: help, children: _jsxs("div", { className: "seed-row", children: [_jsx("input", { type: "text", inputMode: "numeric", placeholder: t("随机"), value: value, onChange: (e) => onChange(e.target.value.replace(/\D/g, "")) }), _jsxs("button", { type: "button", className: "btn-ghost", onClick: roll, title: t("随机生成 Seed"), children: [_jsx(Shuffle, { size: 12 }), " ", t("随机")] }), value && (_jsx("button", { type: "button", className: "btn-ghost", onClick: () => onChange(""), children: "\u00D7" }))] }) }));
}
export default function Settings({ mode, img, onImg, vid, onVid, fswap, onFswap, presets, onSavePreset, onDeletePreset, onApplyPreset, onClose, }) {
    useLang();
    const [presetName, setPresetName] = useState("");
    const title = mode === "image" ? "图片参数设置" : mode === "video" ? "视频参数设置" : "换脸流水线设置";
    const reset = () => {
        if (mode === "image")
            onImg(DEFAULT_IMAGE);
        else if (mode === "video")
            onVid(DEFAULT_VIDEO);
        else
            onFswap(DEFAULT_FACESWAP);
    };
    return (_jsxs("aside", { className: "settings", children: [_jsxs("div", { className: "settings-head", children: [_jsx("span", { children: t(title) }), _jsx("button", { className: "icon-btn", onClick: onClose, "aria-label": t("关闭"), children: _jsx(X, { size: 15 }) })] }), mode === "image" && (_jsxs("div", { className: "settings-body", children: [_jsx(Field, { label: t("工作流"), help: t("Krea2-Noct / Noct-Q V4 支持文生图与多参考图编辑；Z-Image-Turbo NSFW 为 8 步 CFG=1.0 极速文生图工作流。"), children: _jsxs("select", { value: img.profile, onChange: (e) => {
                                const prof = e.target.value;
                                if (prof === "z_image_turbo_nsfw") {
                                    onImg({
                                        ...img,
                                        profile: prof,
                                        steps: 8,
                                        cfg: 1.0,
                                        sampler: "res_multistep",
                                        scheduler: "simple",
                                        turbo: false,
                                    });
                                }
                                else {
                                    onImg({ ...img, profile: prof, steps: 25, cfg: 3.0, sampler: "euler", scheduler: "simple" });
                                }
                            }, children: [_jsx("option", { value: "krea2_noct", children: "Krea2-Noct / Noct-Q V4\uFF08\u5168\u80FD\u6587\u751F\u56FE+\u4FEE\u56FE\uFF09" }), _jsx("option", { value: "z_image_turbo_nsfw", children: "Z-Image-Turbo NSFW\uFF088\u6B65\u6781\u901F\u751F\u56FE\uFF09" })] }) }), img.profile === "krea2_noct" && (_jsx(Field, { label: t("速度 / 画质档位"), help: t("Turbo 使用 8 步加速 LoRA（约快 5 倍）；快速模式 CFG=1；精细模式 CFG=3 并启用负面提示词。"), children: _jsx("div", { className: "preset-row", children: IMAGE_PRESETS.map((p) => {
                                const active = Boolean(img.turbo) === Boolean(p.apply.turbo) &&
                                    img.steps === p.apply.steps &&
                                    img.cfg === p.apply.cfg &&
                                    img.sampler === p.apply.sampler;
                                return (_jsxs("button", { type: "button", className: `preset-btn ${active ? "active" : ""}`, onClick: () => onImg({ ...img, ...p.apply }), children: [p.name === "Turbo" && _jsx(Zap, { size: 11 }), " ", t(p.name)] }, p.name));
                            }) }) })), _jsx(Field, { label: t("分辨率"), children: _jsx("select", { value: img.size, onChange: (e) => onImg({ ...img, size: e.target.value }), children: Object.entries(IMAGE_SIZE_INFO).map(([k, v]) => (_jsxs("option", { value: k, children: [v.label, " \u00B7 ", v.mpx, " (", t(v.secPerStep), ")"] }, k))) }) }), _jsx(Field, { label: t("编辑分辨率"), children: _jsx("select", { value: img.edit_resolution, onChange: (e) => onImg({ ...img, edit_resolution: Number(e.target.value) }), children: Object.entries(EDIT_RES_INFO).map(([k, v]) => (_jsxs("option", { value: k, children: [v.label, " (", t(v.secPerStep), ")"] }, k))) }) }), _jsx(Field, { label: _jsxs(_Fragment, { children: [t("步数"), " ", _jsx("b", { children: img.steps })] }), children: _jsx("input", { type: "range", min: 4, max: 50, value: img.steps, onChange: (e) => onImg({ ...img, steps: Number(e.target.value) }) }) }), _jsx(Field, { label: _jsxs(_Fragment, { children: ["CFG ", _jsx("b", { children: img.cfg.toFixed(1) })] }), children: _jsx("input", { type: "range", min: 1, max: 7, step: 0.5, value: img.cfg, onChange: (e) => onImg({ ...img, cfg: Number(e.target.value) }) }) }), _jsx(Field, { label: "Sampler", children: _jsx("select", { value: img.sampler, onChange: (e) => onImg({ ...img, sampler: e.target.value }), children: SAMPLER_INFO.map((s) => (_jsxs("option", { value: s.id, children: [s.label, " \u2014 ", t(s.note)] }, s.id))) }) }), _jsx(Field, { label: "Scheduler", children: _jsx("select", { value: img.scheduler, onChange: (e) => onImg({ ...img, scheduler: e.target.value }), children: SCHEDULER_INFO.map((s) => (_jsxs("option", { value: s.id, children: [s.label, " \u2014 ", t(s.note)] }, s.id))) }) }), _jsx(SeedField, { value: img.seed, onChange: (seed) => onImg({ ...img, seed }), help: t("固定相同的 Seed 与参数可复现画面，便于微调提示词。") }), _jsx(Field, { label: _jsxs(_Fragment, { children: [t("负面提示词"), " ", img.cfg <= 1 && _jsxs("em", { className: "muted", children: ["(", t("CFG 1 时不生效"), ")"] })] }), children: _jsx("textarea", { rows: 2, value: img.negative, disabled: img.cfg <= 1, placeholder: "blurry, low quality, watermark, deformed", onChange: (e) => onImg({ ...img, negative: e.target.value }) }) })] })), mode === "video" && (_jsxs("div", { className: "settings-body", children: [_jsx(Field, { label: t("工作流"), help: t("MiniMax-H3 支持音视频同步生成与首尾帧控制；Wan2.2-Remix A14B 采用高低噪双阶段 FP8 模型接力采样。"), children: _jsxs("select", { value: vid.profile, onChange: (e) => onVid({ ...vid, profile: e.target.value }), children: [_jsx("option", { value: "minimax_h3", children: "MiniMax-H3\uFF08\u97F3\u753B\u540C\u6B65 \u00B7 \u9996\u5C3E\u5E27\uFF09" }), _jsx("option", { value: "wan22_remix", children: "Wan2.2-Remix A14B\uFF08\u53CC\u9636\u6BB5 FP8 \u56FE\u751F\u89C6\u9891/\u6587\u751F\u89C6\u9891\uFF09" })] }) }), _jsx(Field, { label: t("模式"), children: _jsx("div", { className: "preset-row", children: ["turbo", "quality"].map((q) => (_jsx("button", { type: "button", className: `preset-btn ${vid.quality === q ? "active" : ""}`, onClick: () => onVid({ ...vid, quality: q }), children: q === "turbo" ? (_jsxs(_Fragment, { children: [_jsx(Zap, { size: 11 }), " ", t("Turbo (8 步)")] })) : (t("精细 (20 步)")) }, q))) }) }), _jsx(Field, { label: t("分辨率"), children: _jsxs("select", { value: vid.resolution, onChange: (e) => onVid({ ...vid, resolution: e.target.value }), children: [_jsxs("option", { value: "480p", children: ["480p (~3.5m Turbo / ~9m ", t("精细"), ")"] }), _jsxs("option", { value: "768p", children: ["768p (~9m Turbo / ~22m ", t("精细"), ")"] })] }) }), _jsx(Field, { label: _jsxs(_Fragment, { children: [t("时长"), " ", _jsxs("b", { children: [vid.seconds, "s"] })] }), children: _jsx("input", { type: "range", min: 2, max: 10, value: vid.seconds, onChange: (e) => onVid({ ...vid, seconds: Number(e.target.value) }) }) }), _jsx(SeedField, { value: vid.seed, onChange: (seed) => onVid({ ...vid, seed }), help: t("固定 Seed 可在相同参数下复现镜头轨迹。") })] })), mode === "faceswap" && (_jsxs("div", { className: "settings-body", children: [_jsx(Field, { label: t("换脸引擎"), help: t("阶段一主力使用远端 FaceFusion CLI 全自动无头流水线（已内置 NSFW 拦截短路与哈希校验绕过双补丁）；阶段二实验提供 DreamID-V Faster 外层 81 帧自动切片与拼接流水线。"), children: _jsxs("select", { value: fswap.engine, onChange: (e) => onFswap({ ...fswap, engine: e.target.value }), children: [_jsx("option", { value: "facefusion_cli", children: "FaceFusion CLI\uFF08\u8FDC\u7AEF\u5168\u81EA\u52A8\u6279\u5904\u7406\u4E3B\u529B\uFF09" }), _jsx("option", { value: "dreamid_v_faster", children: "DreamID-V Faster\uFF0881\u5E27\u81EA\u52A8\u5207\u7247\u6269\u6563\u6362\u8138\uFF09" })] }) }), fswap.engine === "facefusion_cli" && (_jsxs(_Fragment, { children: [_jsx(Field, { label: t("同管道三底模基准对比"), help: t("开启后，单次任务会在同一管道内依次运行 hyperswap_1a_256、alphaface_256 与 inswapper_128_fp16 三个底模并排输出，直观对比侧脸保持度、肤色融合与耗时。"), children: _jsxs("div", { className: "preset-row", children: [_jsx("button", { type: "button", className: `preset-btn ${!fswap.compare_all ? "active" : ""}`, onClick: () => onFswap({ ...fswap, compare_all: false }), children: t("单底模运行") }), _jsx("button", { type: "button", className: `preset-btn ${fswap.compare_all ? "active" : ""}`, onClick: () => onFswap({ ...fswap, compare_all: true }), children: t("三底模同管道对比") })] }) }), !fswap.compare_all && (_jsx(Field, { label: t("换脸底模"), help: t("HyperSwap 1A 256 为原生 256×256 主力底模，光影与肤色过渡更自然；AlphaFace 256 针对大侧脸优化；InSwapper 128 FP16 为经典速度基线。"), children: _jsx("select", { value: fswap.swapper_model, onChange: (e) => onFswap({ ...fswap, swapper_model: e.target.value }), children: SWAPPER_MODEL_INFO.map((m) => (_jsxs("option", { value: m.id, children: [m.label, " \u2014 ", t(m.note)] }, m.id))) }) })), _jsx(Field, { label: t("超分像素倍率 (Pixel Boost)"), help: t("将人脸区域拆分为子块推理后再拼接回原图，512x512 及以上在大特写镜头下细节更清晰。"), children: _jsx("select", { value: fswap.pixel_boost, onChange: (e) => onFswap({ ...fswap, pixel_boost: e.target.value }), children: PIXEL_BOOST_OPTIONS.map((b) => (_jsx("option", { value: b, children: b }, b))) }) }), _jsx(Field, { label: t("画质增强后处理 (Face Enhancer)"), help: t("基准测试建议先选「关闭增强」观察底模真实表现；目标视频压缩模糊时可按需开启 CodeFormer 或 GFPGAN 1.4。"), children: _jsx("select", { value: fswap.enhancer_model, onChange: (e) => onFswap({ ...fswap, enhancer_model: e.target.value }), children: ENHANCER_OPTIONS.map((opt) => (_jsx("option", { value: opt.id, children: t(opt.label) }, opt.id))) }) }), fswap.enhancer_model !== "none" && (_jsx(Field, { label: _jsxs(_Fragment, { children: [t("增强混合比 (Blend)"), " ", _jsxs("b", { children: [fswap.enhancer_blend, "%"] })] }), help: t("推荐维持在 40%–60% 区间，避免 80%+ 导致的五官轻微变形与塑料假皮感。"), children: _jsx("input", { type: "range", min: 0, max: 100, step: 5, value: fswap.enhancer_blend, onChange: (e) => onFswap({ ...fswap, enhancer_blend: Number(e.target.value) }) }) }))] })), _jsx("p", { className: "settings-note", children: t("精修升级边界：若遇到手部挡脸、刘海遮挡、眼镜边框等复杂镜头，点击结果卡片上的下载按钮，在本地桌面使用 VisoMaster-Fusion 手工画 XSeg 遮罩精修。") })] })), _jsxs("div", { className: "presets-box", children: [_jsx("div", { className: "field-head", children: _jsxs("span", { children: [_jsx(Bookmark, { size: 11, style: { verticalAlign: "-1px" } }), " ", t("预设列表")] }) }), Object.keys(presets).length > 0 && (_jsx("div", { className: "saved-presets", children: Object.entries(presets).map(([name, params]) => (_jsxs("div", { className: "saved-preset", children: [_jsx("button", { type: "button", className: "saved-preset-name", onClick: () => onApplyPreset(params), title: t("应用"), children: name }), _jsx("button", { type: "button", className: "icon-btn", onClick: () => onDeletePreset(name), title: t("删除"), "aria-label": t("删除"), children: _jsx(Trash2, { size: 11 }) })] }, name))) })), _jsxs("form", { className: "seed-row", onSubmit: (e) => {
                            e.preventDefault();
                            const n = presetName.trim();
                            if (!n)
                                return;
                            onSavePreset(n);
                            setPresetName("");
                        }, children: [_jsx("input", { type: "text", placeholder: t("预设名称"), maxLength: 40, value: presetName, onChange: (e) => setPresetName(e.target.value) }), _jsx("button", { type: "submit", className: "btn-ghost", disabled: !presetName.trim(), children: t("保存") })] })] }), _jsxs("button", { type: "button", className: "btn-ghost settings-reset", onClick: reset, children: [_jsx(RotateCcw, { size: 12 }), " ", t("恢复默认参数")] })] }));
}
