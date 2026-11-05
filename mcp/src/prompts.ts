/**
 * MCP Prompt templates for image, video, and face-swap workflows.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function registerPrompts(server: McpServer): void {
  server.registerPrompt(
    "craft_image_prompt",
    {
      title: "Craft Image Generation Prompt",
      description: "Expands a short concept into a rich visual prompt for Krea2-Noct V4 or Z-Image-Turbo.",
      argsSchema: {
        idea: z.string().describe("Brief image idea."),
        ratio: z.string().optional().describe("Target aspect ratio (e.g. 16:9, 3:4)."),
      },
    },
    ({ idea, ratio }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text:
              `Expand the following image concept into a detailed photography/illustration prompt for Colab Studio ` +
              `(subject, lighting, lens, atmosphere, composition), then call generate_image` +
              `${ratio ? ` with ratio="${ratio}"` : ""}:\n\nConcept: ${idea}`,
          },
        },
      ],
    })
  );

  server.registerPrompt(
    "direct_video_scene",
    {
      title: "Direct Video Scene",
      description: "Prepares a structured video prompt for MiniMax-H3 or Wan2.2-Remix.",
      argsSchema: {
        scene: z.string().describe("Scene description."),
        seconds: z.string().optional().describe("Duration in seconds (2-10)."),
      },
    },
    ({ scene, seconds }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text:
              `Write a cinematic video prompt describing subject motion, camera trajectory, lighting, and sound, ` +
              `then call generate_video${seconds ? ` (seconds=${seconds})` : ""}:\n\nScene: ${scene}`,
          },
        },
      ],
    })
  );

  server.registerPrompt(
    "benchmark_faceswap",
    {
      title: "Benchmark 3 FaceSwap Models in One Pipeline",
      description: "Runs HyperSwap 1A 256, AlphaFace 256, and InSwapper 128 FP16 side by side on the same source & target.",
      argsSchema: {
        source_image: z.string().describe("Path to source face image."),
        target_media: z.string().describe("Path to target image or video."),
      },
    },
    ({ source_image, target_media }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text:
              `Call swap_face with source_images=["${source_image}"], target_media="${target_media}", ` +
              `compare_all=true, enhancer_model="none" to benchmark all 3 base swapper models in the same pipeline.`,
          },
        },
      ],
    })
  );
}
