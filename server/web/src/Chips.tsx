import { Bookmark, Clock, Layers, SlidersHorizontal, Zap } from "lucide-react";
import {
  EnhancerModel,
  FaceSwapEngine,
  ImageProfile,
  Mode,
  PixelBoost,
  StageEstimates,
  SwapperModel,
  VideoProfile,
} from "./api";
import { fmtDuration } from "./format";
import { t, useLang } from "./i18n";

export interface ImageSettings {
  profile: ImageProfile;
  ratio: string;
  size: string;
  edit_resolution: number;
  steps: number;
  cfg: number;
  sampler: string;
  scheduler: string;
  turbo: boolean;
  negative: string;
  count: number;
  seed: string;
}

export interface VideoSettings {
  profile: VideoProfile;
  ratio: string;
  resolution: string;
  seconds: number;
  quality: string;
  seed: string;
}

export interface FaceSwapSettings {
  engine: FaceSwapEngine;
  swapper_model: SwapperModel;
  compare_all: boolean;
  pixel_boost: PixelBoost;
  enhancer_model: EnhancerModel;
  enhancer_blend: number;
}

export const DEFAULT_IMAGE: ImageSettings = {
  profile: "krea2_noct",
  ratio: "1:1",
  size: "1536",
  edit_resolution: 1080,
  steps: 25,
  cfg: 3.0,
  sampler: "euler",
  scheduler: "simple",
  turbo: false,
  negative: "",
  count: 1,
  seed: "",
};

export const DEFAULT_VIDEO: VideoSettings = {
  profile: "minimax_h3",
  ratio: "16:9",
  resolution: "480p",
  seconds: 5,
  quality: "turbo",
  seed: "",
};

export const DEFAULT_FACESWAP: FaceSwapSettings = {
  engine: "facefusion_cli",
  swapper_model: "hyperswap_1a_256",
  compare_all: false,
  pixel_boost: "256x256",
  enhancer_model: "none",
  enhancer_blend: 50,
};

export const IMAGE_RATIOS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"];
export const VIDEO_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"];

export const IMAGE_SIZE_INFO: Record<string, { label: string; mpx: string; mult: number; secPerStep: string }> = {
  "1024": { label: "1K (1024)", mpx: "1.0 MP", mult: 0.45, secPerStep: "~1 秒/步" },
  "1536": { label: "1.5K (1536)", mpx: "2.4 MP", mult: 1.0, secPerStep: "~2.2 秒/步" },
  "2048": { label: "2K (2048)", mpx: "4.2 MP", mult: 2.1, secPerStep: "~4.6 秒/步" },
};

export const EDIT_RES_INFO: Record<number, { label: string; mult: number; secPerStep: string }> = {
  1080: { label: "1080p", mult: 3.6, secPerStep: "~8 秒/步" },
  1440: { label: "1440p", mult: 8.5, secPerStep: "~19 秒/步" },
  2160: { label: "2160p (4K)", mult: 35.0, secPerStep: "~78 秒/步 (CFG 1: ~16 秒)" },
};

export const SWAPPER_MODEL_INFO: { id: SwapperModel; label: string; note: string }[] = [
  { id: "hyperswap_1a_256", label: "HyperSwap 1A 256", note: "推荐主力 · 256原生分辨率，肤色光影过渡自然" },
  { id: "alphaface_256", label: "AlphaFace 256", note: "大侧脸与夸张表情增强对照" },
  { id: "inswapper_128_fp16", label: "InSwapper 128 FP16", note: "经典极速基线 · 128基础分辨率" },
];

export const PIXEL_BOOST_OPTIONS: PixelBoost[] = ["256x256", "512x512", "768x768", "1024x1024"];

export const ENHANCER_OPTIONS: { id: EnhancerModel; label: string }[] = [
  { id: "none", label: "关闭增强（底模直出）" },
  { id: "codeformer", label: "CodeFormer" },
  { id: "gfpgan_1.4", label: "GFPGAN 1.4" },
];

interface Props {
  mode: Mode;
  img: ImageSettings;
  onImg: (s: ImageSettings) => void;
  vid: VideoSettings;
  onVid: (s: VideoSettings) => void;
  fswap: FaceSwapSettings;
  onFswap: (s: FaceSwapSettings) => void;
  attachmentCount: number;
  estimates: StageEstimates;
  warm: string[];
  presets: Record<string, Record<string, unknown>>;
  onApplyPreset: (p: Record<string, unknown>) => void;
  onOpenSettings: () => void;
}

export function estimateCurrent(
  mode: Mode,
  img: ImageSettings,
  vid: VideoSettings,
  fswap: FaceSwapSettings,
  attachmentCount: number,
  estimates: StageEstimates,
  warm: string[]
): { sec: number; warn?: string } {
  const isWarm = warm.includes(mode);
  const pick = (stage: string, fallback: number) => {
    const e = estimates[`${mode}:${stage}`];
    if (!e) return fallback;
    return isWarm ? e.warm : e.cold;
  };

  if (mode === "image") {
    const load = pick("正在加载模型", isWarm ? 2 : 28);
    const enc = pick("正在编码提示词", 5) + (attachmentCount > 0 ? pick("正在读取参考图", 3) : 0);
    const baseGen = pick("正在生成", 55);
    const isZTurbo = img.profile === "z_image_turbo_nsfw" && attachmentCount === 0;
    const stepRatio = (isZTurbo ? 8 : img.steps) / 25;
    const cfgRatio = isZTurbo || img.cfg <= 1 ? 0.5 : 1.0;
    const sizeMult =
      attachmentCount > 0
        ? EDIT_RES_INFO[img.edit_resolution]?.mult ?? 3.6
        : IMAGE_SIZE_INFO[img.size]?.mult ?? 1.0;
    const single = enc + baseGen * stepRatio * cfgRatio * sizeMult + pick("正在保存", 3);
    const total = load + single * img.count;
    const warn =
      attachmentCount > 0 && img.edit_resolution === 2160 && img.cfg > 1 && img.steps >= 20
        ? t("2160p 编辑在 CFG > 1 时耗时约 33 分钟，超出 30 分钟上限：请选择 Turbo (CFG 1) 或降低分辨率。")
        : undefined;
    return { sec: total, warn };
  }

  if (mode === "video") {
    const load = pick("正在加载模型", isWarm ? 3 : 50);
    const enc = pick("正在编码提示词", 12);
    const resMult = vid.resolution === "768p" ? 2.7 : 1.0;
    const qualMult = vid.quality === "quality" ? 2.5 : 1.0;
    const lenMult = vid.seconds / 5;
    const profMult = vid.profile === "wan22_remix" ? 1.15 : 1.0;
    const gen = 180 * resMult * qualMult * lenMult * profMult;
    const warn =
      vid.resolution === "768p" && vid.quality === "quality" && vid.seconds > 8
        ? t("768p 高画质视频超过 8 秒会超出 30 分钟上限：请选择 Turbo 或将时长缩短至 8 秒以内。")
        : undefined;
    return { sec: load + enc + gen + 12, warn };
  }

  const baseSwap = fswap.engine === "dreamid_v_faster" ? 160 : 35;
  const modelMult = fswap.compare_all && fswap.engine === "facefusion_cli" ? 2.8 : 1.0;
  const boostMult = fswap.pixel_boost === "1024x1024" ? 2.2 : fswap.pixel_boost === "768x768" ? 1.7 : fswap.pixel_boost === "512x512" ? 1.3 : 1.0;
  const enhMult = fswap.enhancer_model !== "none" ? 1.35 : 1.0;
  return { sec: 6 + baseSwap * modelMult * boostMult * enhMult };
}

export default function Chips({
  mode,
  img,
  onImg,
  vid,
  onVid,
  fswap,
  onFswap,
  attachmentCount,
  estimates,
  warm,
  presets,
  onApplyPreset,
  onOpenSettings,
}: Props) {
  useLang();
  const isEditing = mode === "image" && attachmentCount > 0;
  const est = estimateCurrent(mode, img, vid, fswap, attachmentCount, estimates, warm);
  const presetNames = Object.keys(presets);

  const toggleImageTurbo = () => {
    const next = !img.turbo;
    onImg(
      next
        ? { ...img, turbo: true, steps: 8, cfg: 1.0, sampler: "euler", scheduler: "simple" }
        : { ...img, turbo: false, steps: 25, cfg: 3.0 }
    );
  };

  return (
    <>
      <div className="chips-row">
        {mode === "image" && (
          <>
            <Select
              label={t("工作流")}
              value={isEditing ? "krea2_noct" : img.profile}
              options={["krea2_noct", "z_image_turbo_nsfw"]}
              display={(v) => (v === "z_image_turbo_nsfw" ? "Z-Image-Turbo (8步)" : "Krea2-Noct V4 (全能)")}
              onChange={(v) => {
                const prof = v as ImageProfile;
                if (prof === "z_image_turbo_nsfw") {
                  onImg({ ...img, profile: prof, steps: 8, cfg: 1.0, sampler: "res_multistep", scheduler: "simple", turbo: false });
                } else {
                  onImg({ ...img, profile: prof, steps: 25, cfg: 3.0, sampler: "euler", scheduler: "simple" });
                }
              }}
            />
            {img.profile === "krea2_noct" && (
              <button
                type="button"
                className={`chip chip-toggle ${img.turbo ? "on" : ""}`}
                onClick={toggleImageTurbo}
                title={t("Turbo LoRA：8 步极速生成（约快 5 倍）")}
              >
                <Zap size={12} /> Turbo
              </button>
            )}
            {!isEditing ? (
              <>
                <Select
                  label={t("比例")}
                  value={img.ratio}
                  options={IMAGE_RATIOS}
                  onChange={(v) => onImg({ ...img, ratio: v })}
                />
                <Select
                  label={t("分辨率")}
                  value={img.size}
                  options={["1024", "1536", "2048"]}
                  display={(v) => IMAGE_SIZE_INFO[v]?.label ?? v}
                  onChange={(v) => onImg({ ...img, size: v })}
                />
              </>
            ) : (
              <Select
                label={t("编辑分辨率")}
                value={String(img.edit_resolution)}
                options={["1080", "1440", "2160"]}
                display={(v) => `${v}p`}
                onChange={(v) => onImg({ ...img, edit_resolution: Number(v) })}
              />
            )}
            <Select
              label={t("张数")}
              value={String(img.count)}
              options={["1", "2", "3", "4"]}
              display={(v) => `${v} ${t("张")}`}
              onChange={(v) => onImg({ ...img, count: Number(v) })}
            />
          </>
        )}

        {mode === "video" && (
          <>
            <Select
              label={t("工作流")}
              value={vid.profile}
              options={["minimax_h3", "wan22_remix"]}
              display={(v) => (v === "wan22_remix" ? "Wan2.2-Remix (双阶段FP8)" : "MiniMax-H3 (音画同步)")}
              onChange={(v) => onVid({ ...vid, profile: v as VideoProfile })}
            />
            <Select
              label={t("比例")}
              value={vid.ratio}
              options={VIDEO_RATIOS}
              onChange={(v) => onVid({ ...vid, ratio: v })}
            />
            <Select
              label={t("分辨率")}
              value={vid.resolution}
              options={["480p", "768p"]}
              onChange={(v) => onVid({ ...vid, resolution: v })}
            />
            <Select
              label={t("时长")}
              value={String(vid.seconds)}
              options={["3", "5", "8", "10"]}
              display={(v) => `${v}s`}
              onChange={(v) => onVid({ ...vid, seconds: Number(v) })}
            />
            <button
              type="button"
              className={`chip chip-toggle ${vid.quality === "turbo" ? "on" : ""}`}
              onClick={() => onVid({ ...vid, quality: vid.quality === "turbo" ? "quality" : "turbo" })}
              title={t("Turbo：8 步快速生成；精细：20 步高连贯度")}
            >
              <Zap size={12} /> {vid.quality === "turbo" ? "Turbo" : t("精细")}
            </button>
          </>
        )}

        {mode === "faceswap" && (
          <>
            <Select
              label={t("换脸引擎")}
              value={fswap.engine}
              options={["facefusion_cli", "dreamid_v_faster"]}
              display={(v) => (v === "dreamid_v_faster" ? "DreamID-V Faster (81帧切片)" : "FaceFusion CLI (主力)")}
              onChange={(v) => onFswap({ ...fswap, engine: v as FaceSwapEngine })}
            />
            {fswap.engine === "facefusion_cli" && (
              <>
                <button
                  type="button"
                  className={`chip chip-toggle ${fswap.compare_all ? "on" : ""}`}
                  onClick={() => onFswap({ ...fswap, compare_all: !fswap.compare_all })}
                  title={t("同一管道依次运行 HyperSwap 1A / AlphaFace / InSwapper 三个底模并排对比")}
                >
                  <Layers size={12} /> {t("三底模对比")}
                </button>
                {!fswap.compare_all && (
                  <Select
                    label={t("换脸底模")}
                    value={fswap.swapper_model}
                    options={SWAPPER_MODEL_INFO.map((m) => m.id)}
                    display={(v) => SWAPPER_MODEL_INFO.find((m) => m.id === v)?.label ?? v}
                    onChange={(v) => onFswap({ ...fswap, swapper_model: v as SwapperModel })}
                  />
                )}
                <Select
                  label={t("超分倍率")}
                  value={fswap.pixel_boost}
                  options={PIXEL_BOOST_OPTIONS}
                  display={(v) => `Boost ${v}`}
                  onChange={(v) => onFswap({ ...fswap, pixel_boost: v as PixelBoost })}
                />
                <Select
                  label={t("后处理增强")}
                  value={fswap.enhancer_model}
                  options={ENHANCER_OPTIONS.map((e) => e.id)}
                  display={(v) => {
                    const found = ENHANCER_OPTIONS.find((e) => e.id === v);
                    if (!found) return v;
                    return v === "none" ? t(found.label) : `${found.label} (${fswap.enhancer_blend}%)`;
                  }}
                  onChange={(v) => onFswap({ ...fswap, enhancer_model: v as EnhancerModel })}
                />
              </>
            )}
          </>
        )}

        {presetNames.length > 0 && (
          <label className="chip" title={t("应用已保存的预设")}>
            <Bookmark size={11} />
            <select
              value=""
              aria-label={t("预设")}
              onChange={(e) => {
                const p = presets[e.target.value];
                if (p) onApplyPreset(p);
              }}
            >
              <option value="" disabled>
                {t("预设")}
              </option>
              {presetNames.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}

        <span className="chip-eta" title={t("基于历史阶段耗时的预计总时长")}>
          <Clock size={11} /> ~{fmtDuration(est.sec)}
        </span>

        <button
          type="button"
          className="chip chip-btn"
          onClick={onOpenSettings}
          title={t("打开详细参数设置")}
        >
          <SlidersHorizontal size={12} /> {t("参数")}
        </button>
      </div>
      {est.warn && <div className="chips-warn">{est.warn}</div>}
    </>
  );
}

function Select({
  value,
  options,
  display,
  onChange,
  label,
}: {
  value: string;
  options: string[];
  display?: (v: string) => string;
  onChange: (v: string) => void;
  label?: string;
}) {
  return (
    <label className="chip" title={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map((o) => (
          <option key={o} value={o}>
            {display ? display(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}
