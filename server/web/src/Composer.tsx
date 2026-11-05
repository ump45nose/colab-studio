import { ArrowUp, Film, Paperclip, X } from "lucide-react";
import { DragEvent, FormEvent, KeyboardEvent, useRef, useState } from "react";
import { api, Mode } from "./api";
import Chips, { FaceSwapSettings, ImageSettings, VideoSettings } from "./Chips";
import { t, useLang } from "./i18n";

export interface Attachment {
  file: string;
  url: string;
  name: string;
  kind: "image" | "video";
}

interface Props {
  mode: Mode;
  prompt: string;
  onPrompt: (p: string) => void;
  attachments: Attachment[];
  onAttachments: (a: Attachment[]) => void;
  img: ImageSettings;
  onImg: (s: ImageSettings) => void;
  vid: VideoSettings;
  onVid: (s: VideoSettings) => void;
  fswap: FaceSwapSettings;
  onFswap: (s: FaceSwapSettings) => void;
  estimates: Record<string, { cold: number; warm: number; samples: number }>;
  warm: string[];
  presets: Record<string, Record<string, unknown>>;
  onApplyPreset: (p: Record<string, unknown>) => void;
  onOpenSettings: () => void;
  onSubmit: () => void;
  onError: (msg: string) => void;
  submitting: boolean;
}

const IMAGE_EXT_RE = /\.(png|jpe?g|webp)$/i;
const VIDEO_EXT_RE = /\.(mp4|webm|mov)$/i;

function isImageFile(f: File): boolean {
  return f.type === "image/png" || f.type === "image/jpeg" || f.type === "image/webp" || IMAGE_EXT_RE.test(f.name);
}

function isVideoFile(f: File): boolean {
  return (
    f.type === "video/mp4" ||
    f.type === "video/webm" ||
    f.type === "video/quicktime" ||
    VIDEO_EXT_RE.test(f.name)
  );
}

function acceptsFile(mode: Mode, f: File): boolean {
  if (mode === "faceswap") return isImageFile(f) || isVideoFile(f);
  return isImageFile(f);
}

export default function Composer({
  mode,
  prompt,
  onPrompt,
  attachments,
  onAttachments,
  img,
  onImg,
  vid,
  onVid,
  fswap,
  onFswap,
  estimates,
  warm,
  presets,
  onApplyPreset,
  onOpenSettings,
  onSubmit,
  onError,
  submitting,
}: Props) {
  useLang();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [previewImg, setPreviewImg] = useState<string | null>(null);

  const acceptAttr =
    mode === "faceswap"
      ? "image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime,.png,.jpg,.jpeg,.webp,.mp4,.webm,.mov"
      : "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";
  const maxAttach = mode === "video" ? 2 : 10;

  const canSend =
    !submitting &&
    !uploading &&
    (mode === "faceswap" ? attachments.length >= 2 : prompt.trim().length > 0);

  const handleFiles = async (files: FileList | File[]) => {
    const all = Array.from(files);
    if (!all.length) return;
    const valid = all.filter((f) => acceptsFile(mode, f));
    const rejected = all.filter((f) => !acceptsFile(mode, f));
    if (rejected.length > 0) {
      const names = rejected.map((f) => f.name).join(", ");
      const expected = mode === "faceswap" ? t("图片 (PNG/JPEG/WebP) 或视频 (MP4/WebM/MOV)") : t("图片 (PNG/JPEG/WebP)");
      onError(t("无法添加 {files}：当前模式仅支持 {kind}。", { files: names, kind: expected }));
    }
    const slots = Math.max(0, maxAttach - attachments.length);
    if (valid.length > slots) {
      onError(t("最多可添加 {limit} 个附件；超出部分的 {n} 个文件已忽略。", { limit: maxAttach, n: valid.length - slots }));
    }
    const list = valid.slice(0, slots);
    if (!list.length) return;
    setUploading(true);
    try {
      const uploaded: Attachment[] = [];
      for (const f of list) {
        const r = await api.upload(f);
        uploaded.push({ file: r.file, url: r.url, name: f.name, kind: r.kind });
      }
      onAttachments([...attachments, ...uploaded]);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (canSend) onSubmit();
  };

  const placeholder =
    mode === "faceswap"
      ? t("请先添加源人脸图（第 1 张起），再添加目标图片或视频（最后 1 个）。可在此填写备注说明...")
      : mode === "video"
        ? t("描述画面场景、镜头运动和声音效果（添加第 1 张图为首帧，第 2 张为尾帧）")
        : attachments.length > 0
          ? t("你想如何修改这张图片？（例如：将背景替换为夕阳海滩）")
          : t("描述你想生成的画面内容...");

  const submitLabel =
    mode === "faceswap"
      ? fswap.compare_all && fswap.engine === "facefusion_cli"
        ? t("三底模对比换脸")
        : t("开始换脸")
      : mode === "image" && attachments.length > 0
        ? t("编辑")
        : t("生成");

  const attachHint =
    mode === "faceswap"
      ? t("添加换脸素材：前 N-1 张为源人脸，最后 1 个为目标图片/视频")
      : mode === "video"
        ? t("添加参考帧：第 1 张为首帧，第 2 张为尾帧")
        : t("添加参考图片（进入修图/编辑模式）");

  return (
    <form
      className={`composer ${dragging ? "dragging" : ""}`}
      onSubmit={onFormSubmit}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      {attachments.length > 0 && (
        <div className="attachments">
          {attachments.map((a, i) => {
            const roleBadge =
              mode === "faceswap"
                ? attachments.length >= 2 && i === attachments.length - 1
                  ? t("目标媒体")
                  : t("源人脸 #{n}", { n: i + 1 })
                : mode === "video"
                  ? i === 0
                    ? t("首帧")
                    : t("尾帧")
                  : null;
            return (
              <div key={a.file} className="attachment">
                {a.kind === "video" ? (
                  <span className="att-audio">
                    <Film size={12} /> {a.name}
                  </span>
                ) : (
                  <img
                    src={a.url}
                    alt={a.name}
                    onClick={() => setPreviewImg(a.url)}
                    title={a.name}
                  />
                )}
                {roleBadge && <span className="att-role-badge">{roleBadge}</span>}
                <button
                  type="button"
                  className="att-remove"
                  aria-label={t("移除")}
                  onClick={() => onAttachments(attachments.filter((_, idx) => idx !== i))}
                >
                  <X size={11} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="composer-main">
        {attachments.length < maxAttach && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept={acceptAttr}
              multiple={maxAttach > 1}
              hidden
              onChange={(e) => {
                if (e.target.files) handleFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="icon-btn attach-btn"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              title={attachHint}
              aria-label={attachHint}
            >
              <Paperclip size={16} />
            </button>
          </>
        )}

        <textarea
          className="composer-input"
          rows={1}
          value={prompt}
          onChange={(e) => onPrompt(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData.files).filter((f) => acceptsFile(mode, f));
            if (files.length) {
              e.preventDefault();
              handleFiles(files);
            }
          }}
          placeholder={placeholder}
          aria-label={t("提示词")}
        />

        <button type="submit" className="send-btn" disabled={!canSend} title={submitLabel} aria-label={submitLabel}>
          <ArrowUp size={16} />
          <span>{submitLabel}</span>
        </button>
      </div>

      <div className="composer-foot">
        <Chips
          mode={mode}
          img={img}
          onImg={onImg}
          vid={vid}
          onVid={onVid}
          fswap={fswap}
          onFswap={onFswap}
          attachmentCount={attachments.length}
          estimates={estimates}
          warm={warm}
          presets={presets}
          onApplyPreset={onApplyPreset}
          onOpenSettings={onOpenSettings}
        />
        <span className="composer-hint">
          {mode === "faceswap"
            ? t("先上传源人脸，最后上传目标图/视频。复杂遮挡镜头可下载结果至本地 VisoMaster-Fusion 精修。")
            : t("Enter 发送，Shift+Enter 换行。若 GPU 未启动，提交首个任务会自动唤醒 GPU。")}
        </span>
      </div>

      {previewImg && (
        <div className="lightbox" onClick={() => setPreviewImg(null)}>
          <img src={previewImg} alt={t("图片预览")} />
        </div>
      )}
    </form>
  );
}
