export const TINY_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0ioAAAAASUVORK5CYII=", "base64");
export async function installMocks(page, overrides = {}) {
    const state = {
        runtime: {
            state: "off",
            step: "GPU 已关闭",
            error: null,
            gpu_tier: "l4",
            gpu_name: null,
            vram_used_mb: 0,
            vram_total_mb: 0,
            disk_free_gb: 0,
            disk_total_gb: 0,
            models: { packs: {} },
            setup_step: null,
            uptime_s: 0,
            idle_s: 0,
            idle_timeout_s: 1800,
            active_jobs: 0,
            warm: [],
            log: [],
            ...(overrides.runtime || {}),
        },
        chats: overrides.chats || [],
        jobs: overrides.jobs || [],
        presets: overrides.presets || {},
        estimates: overrides.estimates || {},
        startup_estimates: overrides.startup_estimates || {},
    };
    const usage = {
        subscription_tier: "SUBSCRIPTION_TIER_PRO",
        paid_balance: 85.4,
        free_balance: 0,
        balance: 85.4,
        burn_rates_hourly: { l4: 1.67, "g2-standard-12": 1.67, a100: 5.36, t4: 1.19 },
        eligible_gpus: ["T4", "L4", "A100"],
        gpu_tier: "l4",
        current_burn_rate: 1.67,
        remaining_hours_active: 51.1,
        session_used: 0.8,
        today_used: 2.4,
        daily_avg_7d: 3.1,
        days_Observed: 5,
        projected_days_left: 27.5,
        daily_history: [
            { date: "2026-11-01", used: 2.0 },
            { date: "2026-11-02", used: 4.1 },
            { date: "2026-11-03", used: 2.4 },
        ],
        ...(overrides.usage || {}),
    };
    const calls = [];
    let seq = 1;
    await page.route("**/media/**", async (route) => {
        await route.fulfill({ status: 200, contentType: "image/png", body: TINY_PNG });
    });
    await page.route("**/api/**", async (route) => {
        const req = route.request();
        const url = new URL(req.url()).pathname;
        const method = req.method();
        let body = null;
        try {
            body = req.postDataJSON();
        }
        catch {
            body = req.postData();
        }
        calls.push({ method, url, body });
        if (url === "/api/state" && method === "GET") {
            return route.fulfill({ json: state });
        }
        if (url === "/api/usage" && method === "GET") {
            return route.fulfill({ json: usage });
        }
        if (url === "/api/runtime/start" && method === "POST") {
            state.runtime.state = "starting";
            state.runtime.step = "正在分配 GPU";
            return route.fulfill({ json: state.runtime });
        }
        if (url === "/api/runtime/stop" && method === "POST") {
            state.runtime.state = "off";
            state.runtime.step = "GPU 已关闭";
            return route.fulfill({ json: state.runtime });
        }
        if (url === "/api/chats" && method === "POST") {
            const chat = {
                id: `chat${seq++}`,
                mode: body?.mode || "image",
                title: body?.title || "新对话",
                created_at: Date.now() / 1000,
                updated_at: Date.now() / 1000,
            };
            state.chats.unshift(chat);
            return route.fulfill({ json: chat });
        }
        if (url.startsWith("/api/chats/") && method === "DELETE") {
            const cid = url.split("/").pop();
            state.chats = state.chats.filter((c) => c.id !== cid);
            state.jobs = state.jobs.filter((j) => j.chat_id !== cid);
            return route.fulfill({ json: { ok: true } });
        }
        if (url === "/api/upload" && method === "POST") {
            const f = `up_${String(seq++).padStart(10, "0")}.png`;
            return route.fulfill({ json: { file: f, url: `/media/${f}`, kind: "image" } });
        }
        if (url === "/api/jobs" && method === "POST") {
            let cid = body.chat_id;
            if (!cid) {
                const chat = {
                    id: `chat${seq++}`,
                    mode: body.kind,
                    title: (body.prompt || "换脸流水线").slice(0, 48),
                    created_at: Date.now() / 1000,
                    updated_at: Date.now() / 1000,
                };
                state.chats.unshift(chat);
                cid = chat.id;
            }
            const job = {
                id: `job${seq++}`,
                chat_id: cid,
                kind: body.kind,
                prompt: body.prompt,
                params: body.params || {},
                inputs: body.inputs || [],
                status: "queued",
                stage: "排队中",
                progress: 0,
                outputs: [],
                error: null,
                created_at: Date.now() / 1000,
                started_at: null,
                finished_at: null,
            };
            state.jobs.push(job);
            return route.fulfill({ json: job });
        }
        if (url.endsWith("/cancel") && method === "POST") {
            const jid = url.split("/")[3];
            const job = state.jobs.find((j) => j.id === jid);
            if (job) {
                job.status = "cancelled";
                job.error = "已取消";
            }
            return route.fulfill({ json: job || {} });
        }
        if (url.startsWith("/api/presets/") && method === "PUT") {
            const mode = url.split("/")[3];
            state.presets[mode] = state.presets[mode] || {};
            state.presets[mode][body.name] = body.params;
            return route.fulfill({ json: state.presets[mode] });
        }
        if (url.startsWith("/api/presets/") && method === "DELETE") {
            const [, , , mode, name] = url.split("/");
            delete state.presets[mode]?.[decodeURIComponent(name)];
            return route.fulfill({ json: state.presets[mode] || {} });
        }
        return route.fulfill({ status: 404, json: { detail: "not mocked" } });
    });
    return { state, usage, calls };
}
