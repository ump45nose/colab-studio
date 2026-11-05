import { Bookmark, HelpCircle, RotateCcw, Shuffle, Trash2, X, Zap } from "lucide-react";
import { ReactNode, useState } from "react";
import {
  EnhancerModel,
  FaceSwapEngine,
  ImageProfile,
  Mode,
  PixelBoost,
  SwapperModel,
  VideoProfile,
} from "./api";
import {
  DEFAULT_FACESWAP,
  DEFAULT_IMAGE,
  DEFAULT_VIDEO,
  EDIT_RES_INFO,
  ENHANCER_OPTIONS,
  FaceSwapSettings,
  IMAGE_SIZE_INFO,
  ImageSettings,
  PIXEL_BOOST_OPTIONS,
  SWAPPER_MODEL_INFO,
  VideoSettings,
} from "./Chips";
import { t, useLang } from "./i18n";

interface Props {
  mode: Mode;
  img: ImageSettings;
  onImg: (s: ImageSettings) => void;
  vid: VideoSettings;
  onVid: (s: VideoSettings) => void;
  fswap: FaceSwapSettings;
  onFswap: (s: FaceSwapSettings) => void;
  presets: Record<string, Record<string, unknown>>;
  onSavePreset: (name: string) => void;
  onDeletePreset: (name: string) => void;
  onApplyPreset: (params: Record<string, unknown>) => void;
  onClose: () => void;
}

const SAMPLER_INFO: { id: string; label: string; note: string }[] = [
  { id: "euler", label: "Euler", note: "推荐默认，稳定且可预测" },
  { id: "euler_ancestral", label: "Euler A", note: "每步注入少量噪声，细节更生动" },
  { id: "res_multistep", label: "RES multistep", note: "Z-Image-Turbo 推荐，低步数锐度高" },
  { id: "dpmpp_2m", label: "DPM++ 2M", note: "细节扎实干净，通用性好" },
  { id: "dpmpp_2m_sde", label: "DPM++ 2M SDE", note: "纹理丰富，适合写实人像" },
  { id: "er_sde", label: "ER SDE", note: "过渡柔和，适合特写肖像" },
  { id: "uni_pc", label: "UniPC", note: "适合 10-15 步快速预览" },
];

const SCHEDULER_INFO: { id: string; label: string; note: string }[] = [
  { id: "simple", label: "Simple", note: "推荐默认" },
  { id: "beta", label: "Beta", note: "首尾步数更密集，可增强细节" },
  { id: "normal", label: "Normal", note: "均匀步长分布" },
  { id: "karras", label: "Karras", note: "尾段精细采样" },
  { id: "sgm_uniform", label: "SGM uniform", note: "Flow 模型常用均匀调度" },
];

const IMAGE_PRESETS: { name: string; apply: Partial<ImageSettings> }[] = [
  { name: "Turbo", apply: { turbo: true, steps: 8, cfg: 1.0, sampler: "euler", scheduler: "simple" } },
  { name: "快速", apply: { turbo: false, steps: 20, cfg: 1.0, sampler: "euler", scheduler: "simple" } },
  { name: "精细", apply: { turbo: false, steps: 28, cfg: 3.0, sampler: "euler", scheduler: "simple" } },
  { name: "草稿", apply: { turbo: false, steps: 12, cfg: 1.0, sampler: "uni_pc", scheduler: "simple" } },
];

function Field({ label, help, children }: { label: ReactNode; help?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="field">
      <div className="field-head">
        <span>{label}</span>
        {help && (
          <button
            type="button"
            className={`help-btn ${open ? "active" : ""}`}
            onClick={() => setOpen((v) => !v)}
            aria-label={t("查看说明")}
          >
            <HelpCircle size={12} />
          </button>
        )}
      </div>
      {open && help && <p className="field-help">{help}</p>}
      {children}
    </div>
  );
}

function SeedField({
  value,
  onChange,
  help,
}: {
  value: string;
  onChange: (v: string) => void;
  help: string;
}) {
  const roll = () => onChange(String(Math.floor(1 + Math.random() * 4294967294)));
  return (
    <Field label="Seed" help={help}>
      <div className="seed-row">
        <input
          type="text"
          inputMode="numeric"
          placeholder={t("随机")}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))}
        />
        <button type="button" className="btn-ghost" onClick={roll} title={t("随机生成 Seed")}>
          <Shuffle size={12} /> {t("随机")}
        </button>
        {value && (
          <button type="button" className="btn-ghost" onClick={() => onChange("")}>
            ×
          </button>
        )}
      </div>
    </Field>
  );
}

export default function Settings({
  mode,
  img,
  onImg,
  vid,
  onVid,
  fswap,
  onFswap,
  presets,
  onSavePreset,
  onDeletePreset,
  onApplyPreset,
  onClose,
}: Props) {
  useLang();
  const [presetName, setPresetName] = useState("");
  const title =
    mode === "image" ? "图片参数设置" : mode === "video" ? "视频参数设置" : "换脸流水线设置";

  const reset = () => {
    if (mode === "image") onImg(DEFAULT_IMAGE);
    else if (mode === "video") onVid(DEFAULT_VIDEO);
    else onFswap(DEFAULT_FACESWAP);
  };

  return (
    <aside className="settings">
      <div className="settings-head">
        <span>{t(title)}</span>
        <button className="icon-btn" onClick={onClose} aria-label={t("关闭")}>
          <X size={15} />
        </button>
      </div>

      {mode === "image" && (
        <div className="settings-body">
          <Field
            label={t("工作流")}
            help={t(
              "Krea2-Noct / Noct-Q V4 支持文生图与多参考图编辑；Z-Image-Turbo NSFW 为 8 步 CFG=1.0 极速文生图工作流。"
            )}
          >
            <select
              value={img.profile}
              onChange={(e) => {
                const prof = e.target.value as ImageProfile;
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
                } else {
                  onImg({ ...img, profile: prof, steps: 25, cfg: 3.0, sampler: "euler", scheduler: "simple" });
                }
              }}
            >
              <option value="krea2_noct">Krea2-Noct / Noct-Q V4（全能文生图+修图）</option>
              <option value="z_image_turbo_nsfw">Z-Image-Turbo NSFW（8步极速生图）</option>
            </select>
          </Field>

          {img.profile === "krea2_noct" && (
            <Field
              label={t("速度 / 画质档位")}
              help={t("Turbo 使用 8 步加速 LoRA（约快 5 倍）；快速模式 CFG=1；精细模式 CFG=3 并启用负面提示词。")}
            >
              <div className="preset-row">
                {IMAGE_PRESETS.map((p) => {
                  const active =
                    Boolean(img.turbo) === Boolean(p.apply.turbo) &&
                    img.steps === p.apply.steps &&
                    img.cfg === p.apply.cfg &&
                    img.sampler === p.apply.sampler;
                  return (
                    <button
                      key={p.name}
                      type="button"
                      className={`preset-btn ${active ? "active" : ""}`}
                      onClick={() => onImg({ ...img, ...p.apply })}
                    >
                      {p.name === "Turbo" && <Zap size={11} />} {t(p.name)}
                    </button>
                  );
                })}
              </div>
            </Field>
          )}

          <Field label={t("分辨率")}>
            <select value={img.size} onChange={(e) => onImg({ ...img, size: e.target.value })}>
              {Object.entries(IMAGE_SIZE_INFO).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label} · {v.mpx} ({t(v.secPerStep)})
                </option>
              ))}
            </select>
          </Field>

          <Field label={t("编辑分辨率")}>
            <select
              value={img.edit_resolution}
              onChange={(e) => onImg({ ...img, edit_resolution: Number(e.target.value) })}
            >
              {Object.entries(EDIT_RES_INFO).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label} ({t(v.secPerStep)})
                </option>
              ))}
            </select>
          </Field>

          <Field
            label={
              <>
                {t("步数")} <b>{img.steps}</b>
              </>
            }
          >
            <input
              type="range"
              min={4}
              max={50}
              value={img.steps}
              onChange={(e) => onImg({ ...img, steps: Number(e.target.value) })}
            />
          </Field>

          <Field
            label={
              <>
                CFG <b>{img.cfg.toFixed(1)}</b>
              </>
            }
          >
            <input
              type="range"
              min={1}
              max={7}
              step={0.5}
              value={img.cfg}
              onChange={(e) => onImg({ ...img, cfg: Number(e.target.value) })}
            />
          </Field>

          <Field label="Sampler">
            <select value={img.sampler} onChange={(e) => onImg({ ...img, sampler: e.target.value })}>
              {SAMPLER_INFO.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} — {t(s.note)}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Scheduler">
            <select value={img.scheduler} onChange={(e) => onImg({ ...img, scheduler: e.target.value })}>
              {SCHEDULER_INFO.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} — {t(s.note)}
                </option>
              ))}
            </select>
          </Field>

          <SeedField
            value={img.seed}
            onChange={(seed) => onImg({ ...img, seed })}
            help={t("固定相同的 Seed 与参数可复现画面，便于微调提示词。")}
          />

          <Field
            label={
              <>
                {t("负面提示词")} {img.cfg <= 1 && <em className="muted">({t("CFG 1 时不生效")})</em>}
              </>
            }
          >
            <textarea
              rows={2}
              value={img.negative}
              disabled={img.cfg <= 1}
              placeholder="blurry, low quality, watermark, deformed"
              onChange={(e) => onImg({ ...img, negative: e.target.value })}
            />
          </Field>
        </div>
      )}

      {mode === "video" && (
        <div className="settings-body">
          <Field
            label={t("工作流")}
            help={t(
              "MiniMax-H3 支持音视频同步生成与首尾帧控制；Wan2.2-Remix A14B 采用高低噪双阶段 FP8 模型接力采样。"
            )}
          >
            <select
              value={vid.profile}
              onChange={(e) => onVid({ ...vid, profile: e.target.value as VideoProfile })}
            >
              <option value="minimax_h3">MiniMax-H3（音画同步 · 首尾帧）</option>
              <option value="wan22_remix">Wan2.2-Remix A14B（双阶段 FP8 图生视频/文生视频）</option>
            </select>
          </Field>

          <Field label={t("模式")}>
            <div className="preset-row">
              {(["turbo", "quality"] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  className={`preset-btn ${vid.quality === q ? "active" : ""}`}
                  onClick={() => onVid({ ...vid, quality: q })}
                >
                  {q === "turbo" ? (
                    <>
                      <Zap size={11} /> {t("Turbo (8 步)")}
                    </>
                  ) : (
                    t("精细 (20 步)")
                  )}
                </button>
              ))}
            </div>
          </Field>

          <Field label={t("分辨率")}>
            <select value={vid.resolution} onChange={(e) => onVid({ ...vid, resolution: e.target.value })}>
              <option value="480p">480p (~3.5m Turbo / ~9m {t("精细")})</option>
              <option value="768p">768p (~9m Turbo / ~22m {t("精细")})</option>
            </select>
          </Field>

          <Field
            label={
              <>
                {t("时长")} <b>{vid.seconds}s</b>
              </>
            }
          >
            <input
              type="range"
              min={2}
              max={10}
              value={vid.seconds}
              onChange={(e) => onVid({ ...vid, seconds: Number(e.target.value) })}
            />
          </Field>

          <SeedField
            value={vid.seed}
            onChange={(seed) => onVid({ ...vid, seed })}
            help={t("固定 Seed 可在相同参数下复现镜头轨迹。")}
          />
        </div>
      )}

      {mode === "faceswap" && (
        <div className="settings-body">
          <Field
            label={t("换脸引擎")}
            help={t(
              "阶段一主力使用远端 FaceFusion CLI 全自动无头流水线（已内置 NSFW 拦截短路与哈希校验绕过双补丁）；阶段二实验提供 DreamID-V Faster 外层 81 帧自动切片与拼接流水线。"
            )}
          >
            <select
              value={fswap.engine}
              onChange={(e) => onFswap({ ...fswap, engine: e.target.value as FaceSwapEngine })}
            >
              <option value="facefusion_cli">FaceFusion CLI（远端全自动批处理主力）</option>
              <option value="dreamid_v_faster">DreamID-V Faster（81帧自动切片扩散换脸）</option>
            </select>
          </Field>

          {fswap.engine === "facefusion_cli" && (
            <>
              <Field
                label={t("同管道三底模基准对比")}
                help={t(
                  "开启后，单次任务会在同一管道内依次运行 hyperswap_1a_256、alphaface_256 与 inswapper_128_fp16 三个底模并排输出，直观对比侧脸保持度、肤色融合与耗时。"
                )}
              >
                <div className="preset-row">
                  <button
                    type="button"
                    className={`preset-btn ${!fswap.compare_all ? "active" : ""}`}
                    onClick={() => onFswap({ ...fswap, compare_all: false })}
                  >
                    {t("单底模运行")}
                  </button>
                  <button
                    type="button"
                    className={`preset-btn ${fswap.compare_all ? "active" : ""}`}
                    onClick={() => onFswap({ ...fswap, compare_all: true })}
                  >
                    {t("三底模同管道对比")}
                  </button>
                </div>
              </Field>

              {!fswap.compare_all && (
                <Field
                  label={t("换脸底模")}
                  help={t(
                    "HyperSwap 1A 256 为原生 256×256 主力底模，光影与肤色过渡更自然；AlphaFace 256 针对大侧脸优化；InSwapper 128 FP16 为经典速度基线。"
                  )}
                >
                  <select
                    value={fswap.swapper_model}
                    onChange={(e) => onFswap({ ...fswap, swapper_model: e.target.value as SwapperModel })}
                  >
                    {SWAPPER_MODEL_INFO.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label} — {t(m.note)}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              <Field
                label={t("超分像素倍率 (Pixel Boost)")}
                help={t("将人脸区域拆分为子块推理后再拼接回原图，512x512 及以上在大特写镜头下细节更清晰。")}
              >
                <select
                  value={fswap.pixel_boost}
                  onChange={(e) => onFswap({ ...fswap, pixel_boost: e.target.value as PixelBoost })}
                >
                  {PIXEL_BOOST_OPTIONS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                label={t("画质增强后处理 (Face Enhancer)")}
                help={t(
                  "基准测试建议先选「关闭增强」观察底模真实表现；目标视频压缩模糊时可按需开启 CodeFormer 或 GFPGAN 1.4。"
                )}
              >
                <select
                  value={fswap.enhancer_model}
                  onChange={(e) => onFswap({ ...fswap, enhancer_model: e.target.value as EnhancerModel })}
                >
                  {ENHANCER_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {t(opt.label)}
                    </option>
                  ))}
                </select>
              </Field>

              {fswap.enhancer_model !== "none" && (
                <Field
                  label={
                    <>
                      {t("增强混合比 (Blend)")} <b>{fswap.enhancer_blend}%</b>
                    </>
                  }
                  help={t("推荐维持在 40%–60% 区间，避免 80%+ 导致的五官轻微变形与塑料假皮感。")}
                >
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={fswap.enhancer_blend}
                    onChange={(e) => onFswap({ ...fswap, enhancer_blend: Number(e.target.value) })}
                  />
                </Field>
              )}
            </>
          )}

          <p className="settings-note">
            {t(
              "精修升级边界：若遇到手部挡脸、刘海遮挡、眼镜边框等复杂镜头，点击结果卡片上的下载按钮，在本地桌面使用 VisoMaster-Fusion 手工画 XSeg 遮罩精修。"
            )}
          </p>
        </div>
      )}

      <div className="presets-box">
        <div className="field-head">
          <span>
            <Bookmark size={11} style={{ verticalAlign: "-1px" }} /> {t("预设列表")}
          </span>
        </div>
        {Object.keys(presets).length > 0 && (
          <div className="saved-presets">
            {Object.entries(presets).map(([name, params]) => (
              <div key={name} className="saved-preset">
                <button
                  type="button"
                  className="saved-preset-name"
                  onClick={() => onApplyPreset(params)}
                  title={t("应用")}
                >
                  {name}
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => onDeletePreset(name)}
                  title={t("删除")}
                  aria-label={t("删除")}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        )}
        <form
          className="seed-row"
          onSubmit={(e) => {
            e.preventDefault();
            const n = presetName.trim();
            if (!n) return;
            onSavePreset(n);
            setPresetName("");
          }}
        >
          <input
            type="text"
            placeholder={t("预设名称")}
            maxLength={40}
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
          />
          <button type="submit" className="btn-ghost" disabled={!presetName.trim()}>
            {t("保存")}
          </button>
        </form>
      </div>

      <button type="button" className="btn-ghost settings-reset" onClick={reset}>
        <RotateCcw size={12} /> {t("恢复默认参数")}
      </button>
    </aside>
  );
}
