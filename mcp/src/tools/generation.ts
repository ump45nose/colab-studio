/**
 * Generation & FaceSwap MCP tools: image, video, and face-swapping pipelines.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult, ContentBlock } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { DEFAULT_OUTPUT_DIR, Job, STUDIO_URL, studioApi, waitForJob } from "../api.js";

export async function formatJobResult(
  job: Job,
  options: { outputDir?: string; returnBase64Images?: boolean } = {}
): Promise<CallToolResult> {
  const outDir = options.outputDir || DEFAULT_OUTPUT_DIR;
  const includeImg = options.returnBase64Images ?? true;

  if (job.status === "error" || job.status === "cancelled") {
    return {
      isError: true,
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              job_id: job.id,
              kind: job.kind,
              status: job.status,
              error: job.error,
              params: job.params,
            },
            null,
            2
          ),
        },
      ],
    };
  }

  if (job.status !== "done") {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              job_id: job.id,
              chat_id: job.chat_id,
              kind: job.kind,
              status: job.status,
              stage: job.stage,
              progress: job.progress,
              note: "Job queued/running in background. Use wait_for_job or get_job to check completion.",
            },
            null,
            2
          ),
        },
      ],
    };
  }

  const savedFiles: Array<{
    file: string;
    kind: string;
    model?: string;
    label?: string;
    url: string;
    local_path: string;
    size_bytes: number;
  }> = [];
  const imageBlocks: ContentBlock[] = [];

  for (const out of job.outputs) {
    const dl = await studioApi.downloadMedia(out.file, outDir, includeImg ? 4 * 1024 * 1024 : 0);
    savedFiles.push({
      file: out.file,
      kind: out.kind,
      model: out.model,
      label: out.label,
      url: `${STUDIO_URL}${out.url}`,
      local_path: dl.localPath,
      size_bytes: dl.sizeBytes,
    });
    if (includeImg && out.kind === "image" && dl.base64) {
      imageBlocks.push({
        type: "image",
        data: dl.base64,
        mimeType: dl.mimeType,
      });
    }
  }

  const durationSec =
    job.started_at && job.finished_at ? Math.round((job.finished_at - job.started_at) * 10) / 10 : null;

  const summary: ContentBlock = {
    type: "text",
    text: JSON.stringify(
      {
        job_id: job.id,
        chat_id: job.chat_id,
        kind: job.kind,
        status: job.status,
        duration_sec: durationSec,
        prompt: job.prompt,
        params: job.params,
        outputs: savedFiles,
      },
      null,
      2
    ),
  };

  return { content: [summary, ...imageBlocks] };
}

export function registerGenerationTools(server: McpServer): void {
  // 1. IMAGE GENERATION & MULTI-REFERENCE EDITING
  server.registerTool(
    "generate_image",
    {
      title: "Generate or Edit Image (Krea2-Noct V4 / Z-Image-Turbo NSFW)",
      description:
        "Generates images from text or edits up to 10 reference images. " +
        "Supports 'krea2_noct' (default, text-to-image + multi-reference editing) and 'z_image_turbo_nsfw' (8-step fast generation).",
      inputSchema: {
        prompt: z.string().min(1).describe("Detailed scene description or image editing instruction."),
        profile: z
          .enum(["krea2_noct", "z_image_turbo_nsfw"])
          .default("krea2_noct")
          .describe("Workflow profile: 'krea2_noct' (all-rounder + editing) or 'z_image_turbo_nsfw' (8-step fast)."),
        reference_images: z
          .array(z.string())
          .max(10)
          .optional()
          .describe("Local file paths or uploaded 'up_xxx.png' filenames for image editing."),
        ratio: z.enum(["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"]).default("1:1"),
        size: z.enum(["1024", "1536", "2048"]).default("1536"),
        edit_resolution: z.union([z.literal(1080), z.literal(1440), z.literal(2160)]).default(1080),
        turbo: z.boolean().default(false).describe("Enable 8-step Turbo LoRA (Krea2-Noct only)."),
        steps: z.number().int().min(4).max(50).optional(),
        cfg: z.number().min(1).max(10).optional(),
        sampler: z
          .enum(["euler", "euler_ancestral", "res_multistep", "dpmpp_2m", "dpmpp_2m_sde", "er_sde", "uni_pc"])
          .default("euler"),
        scheduler: z.enum(["simple", "beta", "normal", "karras", "sgm_uniform"]).default("simple"),
        negative: z.string().default(""),
        count: z.number().int().min(1).max(4).default(1),
        seed: z.number().int().min(0).optional(),
        chat_id: z.string().optional(),
        wait: z.boolean().default(true),
        output_dir: z.string().optional(),
      },
    },
    async (args) => {
      const inputs: string[] = [];
      for (const ref of args.reference_images ?? []) {
        const up = await studioApi.uploadFile(ref);
        inputs.push(up.file);
      }
      const isZTurbo = args.profile === "z_image_turbo_nsfw" && inputs.length === 0;
      const steps = args.steps ?? (isZTurbo || args.turbo ? 8 : 25);
      const cfg = args.cfg ?? (isZTurbo || args.turbo ? 1.0 : 3.0);
      const sampler = isZTurbo && args.sampler === "euler" ? "res_multistep" : args.sampler;
      const job = await studioApi.createJob({
        chat_id: args.chat_id ?? null,
        kind: "image",
        prompt: args.prompt,
        inputs,
        params: {
          profile: args.profile,
          ratio: args.ratio,
          size: args.size,
          edit_resolution: args.edit_resolution,
          steps,
          cfg,
          sampler,
          scheduler: args.scheduler,
          turbo: args.turbo,
          negative: args.negative,
          count: args.count,
          seed: args.seed ?? null,
        },
      });
      if (!args.wait) return formatJobResult(job);
      const done = await waitForJob(job.id);
      return formatJobResult(done, { outputDir: args.output_dir });
    }
  );

  // 2. VIDEO GENERATION (MiniMax-H3 & Wan2.2-Remix)
  server.registerTool(
    "generate_video",
    {
      title: "Generate Video (MiniMax-H3 / Wan2.2-Remix)",
      description:
        "Generates video using 'minimax_h3' (synchronized video+audio, first/last frame control) " +
        "or 'wan22_remix' (Wan2.2-Remix A14B High/Low Noise dual-stage FP8 image-to-video / text-to-video).",
      inputSchema: {
        prompt: z.string().min(1).describe("Scene, camera motion, and audio description."),
        profile: z
          .enum(["minimax_h3", "wan22_remix"])
          .default("minimax_h3")
          .describe("Workflow profile: 'minimax_h3' or 'wan22_remix'."),
        first_frame: z.string().optional().describe("Optional first frame image path or server filename."),
        last_frame: z.string().optional().describe("Optional last frame image path or server filename."),
        ratio: z.enum(["16:9", "9:16", "1:1", "4:3", "3:4"]).default("16:9"),
        resolution: z.enum(["480p", "768p"]).default("480p"),
        seconds: z.number().int().min(2).max(10).default(5),
        quality: z.enum(["turbo", "quality"]).default("turbo"),
        seed: z.number().int().min(0).optional(),
        chat_id: z.string().optional(),
        wait: z.boolean().default(true),
        output_dir: z.string().optional(),
      },
    },
    async (args) => {
      const inputs: string[] = [];
      if (args.first_frame) inputs.push((await studioApi.uploadFile(args.first_frame)).file);
      if (args.last_frame) inputs.push((await studioApi.uploadFile(args.last_frame)).file);
      const job = await studioApi.createJob({
        chat_id: args.chat_id ?? null,
        kind: "video",
        prompt: args.prompt,
        inputs,
        params: {
          profile: args.profile,
          ratio: args.ratio,
          resolution: args.resolution,
          seconds: args.seconds,
          quality: args.quality,
          seed: args.seed ?? null,
        },
      });
      if (!args.wait) return formatJobResult(job);
      const done = await waitForJob(job.id);
      return formatJobResult(done, { outputDir: args.output_dir });
    }
  );

  // 3. AUTOMATED FACE-SWAPPING PIPELINE (FaceFusion CLI + DreamID-V Faster 81-frame slicer)
  server.registerTool(
    "swap_face",
    {
      title: "Automated Face-Swap Pipeline (FaceFusion CLI / DreamID-V Faster)",
      description:
        "Runs remote GPU face-swapping on a target image or video. " +
        "Supports single swapper model ('hyperswap_1a_256' default main, 'alphaface_256' side-profile, 'inswapper_128_fp16' baseline) " +
        "or same-pipeline 3-model benchmark comparison (compare_all=true), plus controlled face enhancer post-processing.",
      inputSchema: {
        source_images: z
          .array(z.string())
          .min(1)
          .max(9)
          .describe("1 to 9 source face image paths or uploaded server filenames."),
        target_media: z
          .string()
          .describe("Target image (.png/.jpg/.webp) or video (.mp4/.webm/.mov) path or server filename."),
        engine: z
          .enum(["facefusion_cli", "dreamid_v_faster"])
          .default("facefusion_cli")
          .describe("Engine: 'facefusion_cli' (main headless batch pipeline) or 'dreamid_v_faster' (81-frame sliced diffusion)."),
        swapper_model: z
          .enum(["hyperswap_1a_256", "alphaface_256", "inswapper_128_fp16"])
          .default("hyperswap_1a_256")
          .describe("Base swapper model when compare_all is false."),
        compare_all: z
          .boolean()
          .default(false)
          .describe("Run all 3 swapper models (hyperswap_1a_256, alphaface_256, inswapper_128_fp16) in the same pipeline for comparison."),
        pixel_boost: z
          .enum(["256x256", "512x512", "768x768", "1024x1024"])
          .default("256x256")
          .describe("Face swapper pixel boost resolution."),
        enhancer_model: z
          .enum(["none", "codeformer", "gfpgan_1.4"])
          .default("none")
          .describe("Post-processing face enhancer ('none' default for clean base-model benchmarking)."),
        enhancer_blend: z
          .number()
          .int()
          .min(0)
          .max(100)
          .default(50)
          .describe("Enhancer blend percentage (recommended 40-60 to avoid plastic skin texture)."),
        prompt: z.string().default("").describe("Optional label or note for this face-swap job."),
        chat_id: z.string().optional(),
        wait: z.boolean().default(true),
        output_dir: z.string().optional(),
      },
    },
    async (args) => {
      const inputs: string[] = [];
      for (const src of args.source_images) {
        inputs.push((await studioApi.uploadFile(src)).file);
      }
      inputs.push((await studioApi.uploadFile(args.target_media)).file);

      const job = await studioApi.createJob({
        chat_id: args.chat_id ?? null,
        kind: "faceswap",
        prompt: args.prompt,
        inputs,
        params: {
          engine: args.engine,
          swapper_model: args.swapper_model,
          compare_all: args.compare_all,
          pixel_boost: args.pixel_boost,
          enhancer_model: args.enhancer_model,
          enhancer_blend: args.enhancer_blend,
        },
      });
      if (!args.wait) return formatJobResult(job);
      const done = await waitForJob(job.id);
      return formatJobResult(done, { outputDir: args.output_dir });
    }
  );
}
