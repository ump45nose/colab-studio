import { t } from "./i18n";

export type Mode = "image" | "video" | "faceswap";

export type ImageProfile = "krea2_noct" | "z_image_turbo_nsfw";
export type VideoProfile = "minimax_h3" | "wan22_remix";
export type FaceSwapEngine = "facefusion_cli" | "dreamid_v_faster";
export type SwapperModel = "hyperswap_1a_256" | "alphaface_256" | "inswapper_128_fp16";
export type PixelBoost = "256x256" | "512x512" | "768x768" | "1024x1024";
export type EnhancerModel = "none" | "codeformer" | "gfpgan_1.4";

export interface PackStatus {
  ready: boolean;
  total_gb: number;
  done_gb: number;
  current: string | null;
  writing?: boolean;
  error?: string;
}

export interface RuntimeStatus {
  state: "off" | "starting" | "ready" | "stopping" | "error";
  step: string;
  error: string | null;
  gpu_tier: string;
  gpu_name: string | null;
  vram_used_mb: number;
  vram_total_mb: number;
  disk_free_gb: number;
  disk_total_mb?: number;
  disk_total_gb: number;
  models: { packs?: Record<string, PackStatus> };
  setup_step: string | null;
  uptime_s: number;
  idle_s: number;
  idle_timeout_s: number;
  active_jobs: number;
  warm: string[];
  log: string[];
}

export interface Chat {
  id: string;
  mode: Mode;
  title: string;
  created_at: number;
  updated_at: number;
}

export interface JobOutput {
  file: string;
  url: string;
  kind: "image" | "video";
  model?: string;
  label?: string;
}

export interface Job {
  id: string;
  chat_id: string | null;
  kind: Mode;
  prompt: string;
  params: Record<string, unknown>;
  inputs: string[];
  status: "queued" | "running" | "done" | "error" | "cancelled";
  stage: string | null;
  stage_started_at?: number;
  stages?: string[];
  warm?: boolean;
  progress: number;
  outputs: JobOutput[];
  error: string | null;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
}

export type StageEstimates = Record<string, { cold: number; warm: number; samples: number }>;
export type StartupEstimates = Record<string, { expected: number; samples: number }>;

export interface AppState {
  runtime: RuntimeStatus;
  chats: Chat[];
  jobs: Job[];
  presets: Partial<Record<Mode, Record<string, Record<string, unknown>>>>;
  estimates: StageEstimates;
  startup_estimates?: StartupEstimates;
}

export interface UsageInfo {
  subscription_tier: string;
  paid_balance: number;
  free_balance: number;
  balance: number;
  burn_rates_hourly: Record<string, number>;
  eligible_gpus: string[];
  gpu_tier: string;
  current_burn_rate: number;
  remaining_hours_active: number | null;
  session_used: number;
  today_used: number;
  daily_avg_7d: number | null;
  days_Observed: number;
  projected_days_left: number | null;
  daily_history: { date: string; used: number }[];
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, init);
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    throw new Error(t("无法连接到服务器；请检查网络连接后重试。({detail})", { detail }));
  }
  if (!r.ok) {
    const text = await r.text();
    let detail: string | null = null;
    try {
      const j = JSON.parse(text);
      if (j && typeof j.detail === "string") detail = j.detail;
    } catch {
      /* non-JSON body */
    }
    if (detail) throw new Error(t(detail));
    if (r.status === 413) throw new Error(t("文件过大（上限 200 MB）。"));
    if (r.status === 502 || r.status === 503 || r.status === 504) {
      throw new Error(t("服务器暂时不可达 ({status})；服务可能正在重启，请稍后重试。", { status: r.status }));
    }
    throw new Error(t("服务器未能处理请求 ({status})；请稍后重试。", { status: r.status }));
  }
  return r.json();
}

export const api = {
  state: () => req<AppState>("/api/state"),
  startGpu: () => req<RuntimeStatus>("/api/runtime/start", { method: "POST" }),
  stopGpu: () => req<RuntimeStatus>("/api/runtime/stop", { method: "POST" }),
  usage: () => req<UsageInfo>("/api/usage"),
  newChat: (mode: Mode, title = "") =>
    req<Chat>("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, title }),
    }),
  deleteChat: (id: string) => req<{ ok: boolean }>(`/api/chats/${id}`, { method: "DELETE" }),
  createJob: (body: {
    chat_id?: string | null;
    kind: Mode;
    prompt: string;
    params?: Record<string, unknown>;
    inputs?: string[];
  }) =>
    req<Job>("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelJob: (id: string) => req<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  savePreset: (mode: Mode, name: string, params: Record<string, unknown>) =>
    req<Record<string, Record<string, unknown>>>(`/api/presets/${mode}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, params }),
    }),
  deletePreset: (mode: Mode, name: string) =>
    req<Record<string, Record<string, unknown>>>(
      `/api/presets/${mode}/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    ),
  upload: async (file: File): Promise<{ file: string; url: string; kind: "image" | "video" }> => {
    const fd = new FormData();
    fd.append("file", file);
    return req("/api/upload", { method: "POST", body: fd });
  },
};
