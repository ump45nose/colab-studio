#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Running Colab Studio MCP Protocol Verification ==="

node -e '
import { spawn } from "node:child_process";

const child = spawn("node", ["dist/index.js"], {
  stdio: ["pipe", "pipe", "inherit"]
});

// Araç sayısı değil, isim listesi doğrulanır: yeni araç eklemek testi kırmaz, silinen/yeniden
// adlandırılan araç yakalanır.
const EXPECTED_TOOLS = [
  "get_studio_status", "start_gpu", "stop_gpu", "get_compute_usage",
  "generate_image", "generate_video", "swap_face", "get_job", "wait_for_job",
  "cancel_job", "upload_media", "list_chats", "delete_chat", "save_preset", "delete_preset"
];

let buffer = "";
let currentStep = 0;

const timer = setTimeout(() => {
  console.error("MCP protocol check timed out after 60s");
  child.kill();
  process.exit(1);
}, 60000);

function fail(message) {
  console.error("✘", message);
  clearTimeout(timer);
  child.kill();
  process.exit(1);
}

function send(obj) {
  child.stdin.write(JSON.stringify(obj) + "\n");
}

child.stdout.on("data", (chunk) => {
  buffer += chunk.toString();
  const lines = buffer.split("\n");
  buffer = lines.pop() || "";

  for (const line of lines) {
    if (!line.trim()) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch (err) {
      fail(`Invalid JSON on stdout: ${line.slice(0, 200)}`);
    }

    if (msg.error) {
      fail(`JSON-RPC error on id ${msg.id}: ${JSON.stringify(msg.error)}`);
    }

    if (msg.id === 1) {
      console.log("✔ Step 1: Initialize handshake passed! Server:", msg.result.serverInfo.name, "v" + msg.result.serverInfo.version);
      send({ jsonrpc: "2.0", method: "notifications/initialized" });
      send({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    } else if (msg.id === 2) {
      const tools = msg.result.tools.map((t) => t.name);
      const missing = EXPECTED_TOOLS.filter((name) => !tools.includes(name));
      const duplicates = tools.filter((name, i) => tools.indexOf(name) !== i);
      if (missing.length > 0) {
        fail(`Missing tools: ${missing.join(", ")}`);
      }
      if (duplicates.length > 0) {
        fail(`Duplicate tool registrations: ${duplicates.join(", ")}`);
      }
      console.log(`✔ Step 2: Tools list passed! Registered ${tools.length} tools, all ${EXPECTED_TOOLS.length} expected tools present.`);
      send({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "get_studio_status", arguments: {} } });
    } else if (msg.id === 3) {
      if (msg.result?.isError) {
        fail(`get_studio_status returned an error: ${JSON.stringify(msg.result.content).slice(0, 300)}`);
      }
      console.log("✔ Step 3: Tool call get_studio_status passed!");
      send({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "list_chats", arguments: {} } });
    } else if (msg.id === 4) {
      if (msg.result?.isError) {
        fail(`list_chats returned an error: ${JSON.stringify(msg.result.content).slice(0, 300)}`);
      }
      console.log("✔ Step 4: Tool call list_chats passed!");
      send({ jsonrpc: "2.0", id: 5, method: "resources/list", params: {} });
    } else if (msg.id === 5) {
      console.log(`✔ Step 5: Resources list passed! (${msg.result.resources.length} resources)`);
      console.log("\n=========================================");
      console.log("🎉 ALL MCP PROTOCOL CHECKS PASSED!");
      console.log("=========================================");
      clearTimeout(timer);
      child.kill();
      process.exit(0);
    }
  }
});

child.on("exit", (code, signal) => {
  if (code !== 0 && code !== null) {
    console.error(`MCP server exited unexpectedly (code ${code}, signal ${signal})`);
    clearTimeout(timer);
    process.exit(1);
  }
});

send({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "test-runner", version: "1.0.0" }
  }
});
'
