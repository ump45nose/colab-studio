/**
 * GPU runtime, job queue, chat, preset, and file management MCP tools.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { Mode, studioApi, waitForJob } from "../api.js";
import { formatJobResult } from "./generation.js";

const MODE_ENUM = z.enum(["image", "video", "faceswap"]);

function jsonText(data: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
}

export function registerStudioTools(server: McpServer): void {
  server.registerTool(
    "get_studio_status",
    {
      title: "Get Studio & GPU Status",
      description:
        "Returns Colab GPU runtime state (off/starting/ready/stopping/error), VRAM/disk telemetry, model pack progress, and recent jobs.",
      inputSchema: {
        include_logs: z.boolean().default(false),
        job_limit: z.number().int().min(0).max(50).default(10),
      },
    },
    async ({ include_logs, job_limit }) => {
      const state = await studioApi.getState();
      const rt = { ...state.runtime };
      if (!include_logs) delete (rt as Partial<typeof rt>).log;
      return jsonText({
        runtime: rt,
        active_Or_queued_jobs: state.jobs.filter((j) => j.status === "queued" || j.status === "running"),
        recent_jobs: state.jobs.slice(-job_limit).reverse(),
        chat_count: state.chats.length,
        presets: state.presets,
      });
    }
  );

  server.registerTool(
    "start_gpu",
    {
      title: "Start Colab GPU",
      description: "Starts the remote Colab GPU runtime (allocates GPU, sets up ComfyUI + FaceFusion, opens SSH tunnel).",
      inputSchema: {
        wait_until_ready: z.boolean().default(false),
        timeout_sec: z.number().int().min(30).max(1800).default(600),
      },
    },
    async ({ wait_until_ready, timeout_sec }) => {
      let rt = await studioApi.startGpu();
      if (wait_until_ready) {
        const t0 = Date.now();
        while (Date.now() - t0 < timeout_sec * 1000) {
          if (rt.state === "ready" || rt.state === "error") break;
          await new Promise((r) => setTimeout(r, 3000));
          rt = (await studioApi.getState()).runtime;
        }
      }
      return jsonText(rt);
    }
  );

  server.registerTool(
    "stop_gpu",
    {
      title: "Stop Colab GPU",
      description: "Cancels active jobs and disconnects the Colab GPU runtime to stop compute unit burn.",
      inputSchema: {},
    },
    async () => jsonText(await studioApi.stopGpu())
  );

  server.registerTool(
    "get_compute_usage",
    {
      title: "Get Colab Compute Units (CU) Usage",
      description: "Returns remaining Colab Compute Units, hourly burn rate, and 7-day usage history.",
      inputSchema: {},
    },
    async () => jsonText(await studioApi.getUsage())
  );

  server.registerTool(
    "get_job",
    {
      title: "Get Job Status",
      description: "Fetches a job by ID and downloads outputs if completed.",
      inputSchema: {
        job_id: z.string().min(1),
        download_outputs: z.boolean().default(true),
        output_dir: z.string().optional(),
      },
    },
    async ({ job_id, download_outputs, output_dir }) => {
      const state = await studioApi.getState();
      const job = state.jobs.find((j) => j.id === job_id);
      if (!job) throw new Error(`Job not found: ${job_id}`);
      if (download_outputs && job.status === "done") {
        return formatJobResult(job, { outputDir: output_dir });
      }
      return jsonText(job);
    }
  );

  server.registerTool(
    "wait_for_job",
    {
      title: "Wait for Job Completion",
      description: "Polls a queued/running job until completion and downloads its outputs.",
      inputSchema: {
        job_id: z.string().min(1),
        timeout_sec: z.number().int().min(10).max(3600).default(1800),
        output_dir: z.string().optional(),
      },
    },
    async ({ job_id, timeout_sec, output_dir }) => {
      const job = await waitForJob(job_id, { timeoutSec: timeout_sec });
      return formatJobResult(job, { outputDir: output_dir });
    }
  );

  server.registerTool(
    "cancel_job",
    {
      title: "Cancel Job",
      description: "Cancels a queued or running job.",
      inputSchema: { job_id: z.string().min(1) },
    },
    async ({ job_id }) => jsonText(await studioApi.cancelJob(job_id))
  );

  server.registerTool(
    "upload_media",
    {
      title: "Upload Image or Video",
      description: "Uploads a local image (PNG, JPEG, WebP) or target video (MP4, WebM, MOV) to the server.",
      inputSchema: { file_path: z.string().min(1) },
    },
    async ({ file_path }) => jsonText(await studioApi.uploadFile(file_path))
  );

  server.registerTool(
    "list_chats",
    {
      title: "List Chats",
      description: "Lists chat histories optionally filtered by mode (image, video, faceswap).",
      inputSchema: { mode: MODE_ENUM.optional() },
    },
    async ({ mode }) => {
      const state = await studioApi.getState();
      const chats = mode ? state.chats.filter((c) => c.mode === mode) : state.chats;
      return jsonText(chats);
    }
  );

  server.registerTool(
    "delete_chat",
    {
      title: "Delete Chat",
      description: "Deletes a chat and cleans up its unreferenced media files.",
      inputSchema: { chat_id: z.string().min(1) },
    },
    async ({ chat_id }) => jsonText(await studioApi.deleteChat(chat_id))
  );

  server.registerTool(
    "save_preset",
    {
      title: "Save Parameter Preset",
      description: "Saves a named parameter preset for image, video, or faceswap mode.",
      inputSchema: {
        mode: MODE_ENUM,
        name: z.string().min(1).max(40),
        params: z.record(z.unknown()),
      },
    },
    async ({ mode, name, params }) =>
      jsonText(await studioApi.savePreset(mode as Mode, name, params as Record<string, unknown>))
  );

  server.registerTool(
    "delete_preset",
    {
      title: "Delete Parameter Preset",
      description: "Deletes a saved preset.",
      inputSchema: { mode: MODE_ENUM, name: z.string().min(1) },
    },
    async ({ mode, name }) => jsonText(await studioApi.deletePreset(mode as Mode, name))
  );
}
