/**
 * HTTP client for the Colab Studio FastAPI server.
 */

import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, extname, join, resolve } from "node:path";
import { homedir } from "node:os";

export const STUDIO_URL = (process.env.COLAB_STUDIO_URL || "http://127.0.0.1:8765").replace(/\/+$/, "");
export const DEFAULT_OUTPUT_DIR = process.env.COLAB_STUDIO_OUTPUT_DIR || join(homedir(), "Downloads", "colab-studio");

export type Mode = "image" | "video" | "faceswap";

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

export interface AppState {
  runtime: RuntimeStatus;
  chats: Chat[];
  jobs: Job[];
  presets: Partial<Record<Mode, Record<string, Record<string, unknown>>>>;
  estimates: Record<string, { cold: number; warm: number; samples: number }>;
  startup_estimates?: Record<string, { expected: number; samples: number }>;
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

const MIME_BY_EXT: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".mov": "video/quicktime",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${STUDIO_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Cannot reach Colab Studio (${STUDIO_URL}): ${msg}`);
  }
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* raw text */
    }
    throw new Error(`Colab Studio HTTP ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const studioApi = {
  getState: () => request<AppState>("/api/state"),
  startGpu: () => request<RuntimeStatus>("/api/runtime/start", { method: "POST" }),
  stopGpu: () => request<RuntimeStatus>("/api/runtime/stop", { method: "POST" }),
  getUsage: () => request<UsageInfo>("/api/usage"),

  createChat: (mode: Mode, title = "") =>
    request<Chat>("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, title }),
    }),

  deleteChat: (id: string) => request<{ ok: boolean }>(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE" }),

  createJob: (body: {
    chat_id?: string | null;
    kind: Mode;
    prompt: string;
    params?: Record<string, unknown>;
    inputs?: string[];
  }) =>
    request<Job>("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  cancelJob: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),

  savePreset: (mode: Mode, name: string, params: Record<string, unknown>) =>
    request<Record<string, Record<string, unknown>>>(`/api/presets/${mode}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, params }),
    }),

  deletePreset: (mode: Mode, name: string) =>
    request<Record<string, Record<string, unknown>>>(
      `/api/presets/${mode}/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    ),

  async uploadFile(fileOrServerName: string): Promise<{ file: string; url: string; kind: string }> {
    if (/^up_[0-9a-f]{10}\.[a-z0-9]+$/i.test(fileOrServerName)) {
      const ext = extname(fileOrServerName).toLowerCase();
      return {
        file: fileOrServerName,
        url: `/media/${fileOrServerName}`,
        kind: [".mp4", ".webm", ".mov"].includes(ext) ? "video" : "image",
      };
    }
    const full = resolve(fileOrServerName);
    if (!existsSync(full)) {
      throw new Error(`Local file not found: ${full}`);
    }
    const ext = extname(full).toLowerCase();
    const mime = MIME_BY_EXT[ext];
    if (!mime) {
      throw new Error(`Unsupported file extension (${ext}). Supported: ${Object.keys(MIME_BY_EXT).join(", ")}`);
    }
    const buf = await readFile(full);
    const blob = new Blob([buf], { type: mime });
    const form = new FormData();
    form.append("file", blob, basename(full));
    return request<{ file: string; url: string; kind: string }>("/api/upload", {
      method: "POST",
      body: form,
    });
  },

  async downloadMedia(
    mediaFile: string,
    outputDir: string = DEFAULT_OUTPUT_DIR,
    includeBase64MaxBytes = 4 * 1024 * 1024
  ): Promise<{ localPath: string; mimeType: string; sizeBytes: number; base64?: string }> {
    const clean = basename(mediaFile);
    const res = await fetch(`${STUDIO_URL}/media/${encodeURIComponent(clean)}`);
    if (!res.ok) {
      throw new Error(`Could not download media (${clean}): HTTP ${res.status}`);
    }
    const ab = await res.arrayBuffer();
    const buf = Buffer.from(ab);
    await mkdir(outputDir, { recursive: true });
    const localPath = join(outputDir, clean);
    await writeFile(localPath, buf);
    const ext = extname(clean).toLowerCase();
    const mimeType = MIME_BY_EXT[ext] || res.headers.get("content-type") || "application/octet-stream";
    const base64 = buf.byteLength <= includeBase64MaxBytes ? buf.toString("base64") : undefined;
    return { localPath, mimeType, sizeBytes: buf.byteLength, base64 };
  },
};

export interface WaitProgress {
  job: Job;
  runtime: RuntimeStatus;
}

export async function waitForJob(
  jobId: string,
  options: {
    timeoutSec?: number;
    pollIntervalMs?: number;
    onProgress?: (p: WaitProgress) => void | Promise<void>;
  } = {}
): Promise<Job> {
  const timeoutMs = (options.timeoutSec ?? 1800) * 1000;
  const pollMs = options.pollIntervalMs ?? 2500;
  const t0 = Date.now();
  let lastStage = "";
  let lastPct = -1;

  while (Date.now() - t0 < timeoutMs) {
    const state = await studioApi.getState();
    const job = state.jobs.find((j) => j.id === jobId);
    if (!job) {
      throw new Error(`Job not found on server: ${jobId}`);
    }
    const stageKey = `${state.runtime.state}:${state.runtime.step}:${job.status}:${job.stage ?? ""}`;
    if (options.onProgress && (stageKey !== lastStage || job.progress !== lastPct)) {
      lastStage = stageKey;
      lastPct = job.progress;
      await options.onProgress({ job, runtime: state.runtime });
    }
    if (job.status === "done" || job.status === "error" || job.status === "cancelled") {
      return job;
    }
    await new Promise((r) => setTimeout(r, pollMs));
  }
  throw new Error(`Job ${jobId} did not finish within ${options.timeoutSec ?? 1800}s (still running on server).`);
}
