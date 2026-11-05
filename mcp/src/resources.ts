/**
 * MCP Resources: live GPU status, model catalog, and recent jobs.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { studioApi } from "./api.js";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

export function registerResources(server: McpServer): void {
  server.registerResource(
    "studio-status",
    "studio://status",
    {
      title: "Colab Studio Runtime Status",
      description: "Live GPU state, VRAM/disk usage, model pack readiness, and stage timing estimates.",
      mimeType: "application/json",
    },
    async (uri) => {
      const state = await studioApi.getState();
      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify(
              {
                runtime: state.runtime,
                estimates: state.estimates,
                startup_estimates: state.startup_estimates,
                presets: state.presets,
              },
              null,
              2
            ),
          },
        ],
      };
    }
  );

  server.registerResource(
    "studio-recent-jobs",
    "studio://jobs/recent",
    {
      title: "Recent Jobs",
      description: "The 25 most recent image, video, and faceswap jobs.",
      mimeType: "application/json",
    },
    async (uri) => {
      const state = await studioApi.getState();
      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify(state.jobs.slice(-25).reverse(), null, 2),
          },
        ],
      };
    }
  );

  server.registerResource(
    "studio-models-catalog",
    "studio://models/catalog",
    {
      title: "Model Catalog (models.default.toml)",
      description: "HuggingFace repositories and filenames for image, image_turbo, video, and video_wan22 packs.",
      mimeType: "application/toml",
    },
    async (uri) => {
      const tomlPath = resolve(REPO_ROOT, "station", "models.default.toml");
      const text = await readFile(tomlPath, "utf8");
      return {
        contents: [{ uri: uri.href, mimeType: "application/toml", text }],
      };
    }
  );
}
