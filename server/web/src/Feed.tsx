import {
  AlertTriangle,
  Copy,
  Download,
  Lock,
  Pencil,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Square,
  ZoomIn,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Job,
  Mode,
  RuntimeStatus,
  StageEstimates,
  StartupEstimates,
} from "./api";
import { fmtDuration } from "./format";
import { t, translateServerText, useLang } from "./i18n";
import { startupRemaining } from "./SystemPanel";

interface Props {
  mode: Mode;
  jobs: Job[];
  allJobs: Job[];
  runtime: RuntimeStatus;
  estimates: StageEstimates;
  startupEstimates?: StartupEstimates;
  onSelectPrompt: (text: string) => void;
  onReuseImage: (file: string, url: string) => void;
  onSendToFaceSwap: (file: string, url: string) => void;
  onCancel: (id: string) => void;
  onRerun: (job: Job, sameSeed: boolean) => void;
  onLockSeed: (job: Job) => void;
}

const SUGGESTIONS: Record<Mode, { title: string; sub: string; prompts: string[] }> = {
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

const KIND_LABEL: Record<Mode, string> = {
  image: "图片",
  video: "视频",
  faceswap: "换脸",
};

function stripIndexPrefix(stage: string): { prefix: string; clean: string } {
  const m = stage.match(/^(\[\d+\/\d+\]\s*)(.*)$/);
  if (!m) return { prefix: "", clean: stage };
  return { prefix: m[1], clean: m[2] };
}

function baseStageName(clean: string): string {
  return clean.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

function estimateSingleJob(job: Job, estimates: StageEstimates, warm: boolean): number {
  const stages = job.stages || ["正在加载模型", "正在生成", "正在保存"];
  let total = 0;
  for (const s of stages) {
    const e = estimates[`${job.kind}:${s}`];
    if (e) total += warm ? e.warm : e.cold;
    else total += s === "正在加载模型" ? (warm ? 2 : 25) : s.startsWith("正在生成") ? 60 : 5;
  }
  const count = Number(job.params?.count ?? 1);
  return total * Math.max(1, count);
}

export default function Feed({
  mode,
  jobs,
  allJobs,
  runtime,
  estimates,
  startupEstimates,
  onSelectPrompt,
  onReuseImage,
  onSendToFaceSwap,
  onCancel,
  onRerun,
  onLockSeed,
}: Props) {
  useLang();
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);

  const hasActive =
    runtime.state === "starting" ||
    allJobs.some((j) => j.status === "running" || j.status === "queued");
  useEffect(() => {
    if (!hasActive) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [hasActive]);

  if (jobs.length === 0) {
    const s = SUGGESTIONS[mode];
    return (
      <div className="empty-state">
        <h2>{t(s.title)}</h2>
        <p>{t(s.sub)}</p>
        {s.prompts.length > 0 && (
          <div className="suggestions">
            {s.prompts.map((p) => {
              const tp = t(p);
              return (
                <button key={p} className="suggestion" onClick={() => onSelectPrompt(tp)}>
                  {tp}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="feed">
      {jobs.map((j) => (
        <JobCard
          key={j.id}
          job={j}
          allJobs={allJobs}
          runtime={runtime}
          estimates={estimates}
          startupEstimates={startupEstimates}
          now={now}
          onZoom={setLightbox}
          onReusePrompt={onSelectPrompt}
          onReuseImage={onReuseImage}
          onSendToFaceSwap={onSendToFaceSwap}
          onCancel={onCancel}
          onRerun={onRerun}
          onLockSeed={onLockSeed}
        />
      ))}
      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <img src={lightbox} alt="" />
        </div>
      )}
    </div>
  );
}

function QueuedStatus({
  job,
  allJobs,
  runtime,
  estimates,
  startupEstimates,
  now,
}: {
  job: Job;
  allJobs: Job[];
  runtime: RuntimeStatus;
  estimates: StageEstimates;
  startupEstimates?: StartupEstimates;
  now: number;
}) {
  const active = allJobs
    .filter((j) => j.status === "running" || j.status === "queued")
    .sort((a, b) => a.created_at - b.created_at);
  const idx = active.findIndex((j) => j.id === job.id);
  const ahead = idx > 0 ? active.slice(0, idx) : [];
  const running = active.find((j) => j.status === "running");

  let waitSec = 0;
  const bootLeft = startupRemaining(runtime, startupEstimates);
  if (bootLeft !== null) waitSec += bootLeft;
  for (const a of ahead) {
    const total = estimateSingleJob(a, estimates, runtime.warm.includes(a.kind));
    if (a.status === "running" && a.started_at) {
      const elapsed = Math.max(0, now - a.started_at);
      const byPct = a.progress > 5 ? (elapsed * (100 - a.progress)) / a.progress : total - elapsed;
      waitSec += Math.max(5, byPct);
    } else {
      waitSec += total;
    }
  }

  const posText = ahead.length === 0 ? t("排队中") : `${t("排队中")} · ${t("前方还有 {n} 个任务", { n: ahead.length })}`;
  let blockerText: string | null = null;
  if (runtime.state === "starting") {
    blockerText = `${t("当前：正在启动 GPU")} (${translateServerText(runtime.setup_step || runtime.step)})`;
  } else if (running && running.id !== job.id) {
    const kindLbl = t(KIND_LABEL[running.kind] || running.kind);
    const stg = translateServerText(running.stage || t("运行中"));
    const pct = running.progress > 0 ? `${running.progress}%` : "";
    blockerText = t("当前：{kind} — {stage} {pct}", { kind: kindLbl, stage: stg, pct }).trim();
  }

  const etaText = waitSec > 3 ? t("预计 ~{d} 后开始", { d: fmtDuration(waitSec) }) : t("即将开始");

  return (
    <div className="job-progress">
      <div className="progress-head">
        <span>
          {posText}
          {blockerText && <span className="progress-sub"> · {blockerText}</span>}
        </span>
        <span className="progress-eta">{etaText}</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill indeterminate" style={{ width: "25%" }} />
      </div>
    </div>
  );
}

function RunningStatus({
  job,
  runtime,
  estimates,
  startupEstimates,
  now,
}: {
  job: Job;
  runtime: RuntimeStatus;
  estimates: StageEstimates;
  startupEstimates?: StartupEstimates;
  now: number;
}) {
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
    return (
      <div className="job-progress">
        <div className="progress-head">
          <span>
            {t("正在启动 GPU：{step} · {pct}% · 剩余 ~{left}", {
              step: stepLbl,
              pct: bootPct,
              left: fmtDuration(bootLeft ?? 60),
            })}
          </span>
          <span className="progress-eta">{fmtDuration(elapsed)}</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${Math.max(6, bootPct)}%` }} />
        </div>
      </div>
    );
  }

  const stages = job.stages || [];
  const curIdx = stages.indexOf(baseName);
  const warm = job.warm ?? runtime.warm.includes(job.kind);

  const stageEst = (s: string): { sec: number; known: boolean } => {
    const e = estimates[`${job.kind}:${s}`];
    if (!e) return { sec: 20, known: false };
    return { sec: warm ? e.warm : e.cold, known: e.samples > 0 };
  };

  const curExpected = curIdx >= 0 ? stageEst(baseName) : { sec: 30, known: false };
  let remSec = 0;

  if (job.progress > 5 && job.progress < 100 && stageElapsed > 2) {
    remSec = Math.max(1, (stageElapsed * (100 - job.progress)) / job.progress);
  } else if (curIdx >= 0) {
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

  const stageSub =
    stageElapsed >= 3 && curIdx >= 0
      ? ` · ${t("当前阶段已用 {d}", { d: fmtDuration(stageElapsed) })}${curExpected.sec >= 5 ? ` (${t("通常约 ~{d}", { d: fmtDuration(curExpected.sec) })})` : ""}`
      : "";

  return (
    <div className="job-progress">
      <div className="progress-head">
        <span>
          {displayStage}
          <span className="progress-sub">{stageSub}</span>
        </span>
        <span className="progress-eta">{rightText}</span>
      </div>
      <div className="progress-track">
        <div
          className={`progress-fill ${pct === 0 ? "indeterminate" : ""}`}
          style={{ width: `${Math.max(pct, 6)}%` }}
        />
      </div>
      {(stallWarn || slowNote) && (
        <div className={`progress-note ${stallWarn ? "warn" : ""}`}>
          <AlertTriangle size={12} />
          {stallWarn
            ? t("耗时远超预期且 GPU 显存空闲，任务可能卡住，建议取消后重试")
            : t("耗时略长于预期，任务仍在运行中")}
        </div>
      )}
    </div>
  );
}

function JobCard({
  job,
  allJobs,
  runtime,
  estimates,
  startupEstimates,
  now,
  onZoom,
  onReusePrompt,
  onReuseImage,
  onSendToFaceSwap,
  onCancel,
  onRerun,
  onLockSeed,
}: {
  job: Job;
  allJobs: Job[];
  runtime: RuntimeStatus;
  estimates: StageEstimates;
  startupEstimates?: StartupEstimates;
  now: number;
  onZoom: (url: string) => void;
  onReusePrompt: (p: string) => void;
  onReuseImage: (file: string, url: string) => void;
  onSendToFaceSwap: (file: string, url: string) => void;
  onCancel: (id: string) => void;
  onRerun: (job: Job, sameSeed: boolean) => void;
  onLockSeed: (job: Job) => void;
}) {
  const active = job.status === "queued" || job.status === "running";
  const dur =
    job.started_at && job.finished_at ? Math.max(1, Math.round(job.finished_at - job.started_at)) : null;
  const p = job.params || {};
  const badges: string[] = [];

  if (job.kind === "image") {
    const prof = String(p.profile || "krea2_noct");
    badges.push(prof === "z_image_turbo_nsfw" ? "Z-Image-Turbo" : "Krea2-Noct V4");
    if (job.inputs.length > 0) {
      badges.push(t("修图"), `${p.edit_resolution ?? 1080}p`);
    } else {
      if (p.ratio) badges.push(String(p.ratio));
      if (p.size) badges.push(`${p.size}px`);
    }
    if (p.turbo) badges.push("Turbo");
    if (p.steps) badges.push(t("{n} 步", { n: Number(p.steps) }));
    if (p.cfg !== undefined) badges.push(`CFG ${p.cfg}`);
    if (p.seed) badges.push(`seed ${p.seed}`);
  } else if (job.kind === "video") {
    const prof = String(p.profile || "minimax_h3");
    badges.push(prof === "wan22_remix" ? "Wan2.2-Remix" : "MiniMax-H3");
    if (p.resolution) badges.push(String(p.resolution));
    if (p.ratio) badges.push(String(p.ratio));
    if (p.seconds) badges.push(`${p.seconds}s`);
    badges.push(p.quality === "quality" ? t("20 步") : "Turbo");
    if (p.seed) badges.push(`seed ${p.seed}`);
  } else if (job.kind === "faceswap") {
    const eng = String(p.engine || "facefusion_cli");
    badges.push(eng === "dreamid_v_faster" ? "DreamID-V Faster (81帧切片)" : "FaceFusion CLI");
    if (eng === "facefusion_cli") {
      badges.push(p.compare_all ? t("三底模同管道对比") : String(p.swapper_model || "hyperswap_1a_256"));
      if (p.pixel_boost) badges.push(`Boost ${p.pixel_boost}`);
      if (p.enhancer_model && p.enhancer_model !== "none") {
        badges.push(`${p.enhancer_model} (${p.enhancer_blend ?? 50}%)`);
      } else {
        badges.push(t("底模直出（无增强）"));
      }
    }
  }

  return (
    <article className="job-card">
      <header className="job-head">
        <div className="job-prompt-wrap">
          {job.inputs.length > 0 && (
            <div className="job-inputs">
              {job.inputs.map((f, idx) => {
                const isVid = /\.(mp4|webm|mov)$/i.test(f);
                const roleTag =
                  job.kind === "faceswap"
                    ? idx === job.inputs.length - 1
                      ? t("目标")
                      : t("源#{n}", { n: idx + 1 })
                    : null;
                return (
                  <div key={f} className="job-input-thumb-wrap">
                    {isVid ? (
                      <video src={`/media/${f}`} className="job-input-thumb" muted playsInline />
                    ) : (
                      <img
                        src={`/media/${f}`}
                        alt=""
                        className="job-input-thumb"
                        onClick={() => onZoom(`/media/${f}`)}
                      />
                    )}
                    {roleTag && <span className="job-input-tag">{roleTag}</span>}
                  </div>
                );
              })}
            </div>
          )}
          <div>
            <p className="job-prompt">{translateServerText(job.prompt)}</p>
            {badges.length > 0 && (
              <div className="job-badges">
                {badges.map((b, i) => (
                  <span key={i} className="param-badge">
                    {b}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="job-meta">
          {dur !== null && (
            <span className="job-dur" title={t("耗时 {n} 秒", { n: dur })}>
              {fmtDuration(dur)}
            </span>
          )}
          <div className="job-actions">
            {!active && (
              <>
                <button
                  className="icon-btn"
                  onClick={() => onRerun(job, false)}
                  title={t("重新生成")}
                  aria-label={t("重新生成")}
                >
                  <RefreshCw size={13} />
                </button>
                {job.prompt && (
                  <button
                    className="icon-btn"
                    onClick={() => onReusePrompt(job.prompt)}
                    title={t("复用提示词")}
                    aria-label={t("复用提示词")}
                  >
                    <Copy size={13} />
                  </button>
                )}
                {Boolean(p.seed) && (
                  <button
                    className="icon-btn"
                    onClick={() => onLockSeed(job)}
                    title={t("锁定此结果的 Seed 与参数，方便微调提示词")}
                    aria-label={t("锁定 Seed")}
                  >
                    <Lock size={13} />
                  </button>
                )}
              </>
            )}
            {(job.status === "error" || job.status === "cancelled") && (
              <button className="btn-ghost" onClick={() => onRerun(job, true)}>
                <RotateCcw size={12} /> {t("重试")}
              </button>
            )}
            {active && (
              <button
                className="btn-ghost btn-cancel"
                onClick={() => onCancel(job.id)}
                title={t("中止当前任务；GPU 保持开启")}
              >
                <Square size={11} /> {t("取消")}
              </button>
            )}
          </div>
        </div>
      </header>

      {job.status === "queued" && (
        <QueuedStatus
          job={job}
          allJobs={allJobs}
          runtime={runtime}
          estimates={estimates}
          startupEstimates={startupEstimates}
          now={now}
        />
      )}

      {job.status === "running" && (
        <RunningStatus
          job={job}
          runtime={runtime}
          estimates={estimates}
          startupEstimates={startupEstimates}
          now={now}
        />
      )}

      {(job.status === "error" || job.status === "cancelled") && (
        <div className={`job-error ${job.status === "cancelled" ? "cancelled" : ""}`}>
          {translateServerText(job.error || "")}
        </div>
      )}

      {job.outputs.length > 0 && (
        <div className={`job-outputs count-${Math.min(job.outputs.length, 4)}`}>
          {job.outputs.map((o) => (
            <div key={o.file} className="output-item">
              {o.label && <div className="output-model-badge">{o.label}</div>}
              {o.kind === "image" && (
                <>
                  <img src={o.url} alt={job.prompt} loading="lazy" onClick={() => onZoom(o.url)} />
                  <div className="output-overlay">
                    <button onClick={() => onZoom(o.url)} title={t("放大查看")} aria-label={t("放大查看")}>
                      <ZoomIn size={14} />
                    </button>
                    <button
                      onClick={() => onReuseImage(o.file, o.url)}
                      title={t("编辑此图")}
                      aria-label={t("编辑此图")}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => onSendToFaceSwap(o.file, o.url)}
                      title={t("发送到换脸流水线")}
                      aria-label={t("发送到换脸流水线")}
                    >
                      <Sparkles size={14} />
                    </button>
                    <a href={o.url} download={o.file} title={t("下载（可用于本地 VisoMaster-Fusion 精修）")} aria-label={t("下载")}>
                      <Download size={14} />
                    </a>
                  </div>
                </>
              )}
              {o.kind === "video" && (
                <div className="video-wrap">
                  <video src={o.url} controls playsInline loop />
                  <div className="video-actions-bar">
                    <a
                      className="btn-ghost"
                      href={o.url}
                      download={o.file}
                      title={t("下载视频（复杂遮挡镜头可在本地 VisoMaster-Fusion 手工画遮罩精修）")}
                    >
                      <Download size={13} /> {t("下载视频 / 本地精修")}
                    </a>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
