import { t } from "./i18n";
async function req(url, init) {
    let r;
    try {
        r = await fetch(url, init);
    }
    catch (e) {
        const detail = e instanceof Error ? e.message : String(e);
        throw new Error(t("无法连接到服务器；请检查网络连接后重试。({detail})", { detail }));
    }
    if (!r.ok) {
        const text = await r.text();
        let detail = null;
        try {
            const j = JSON.parse(text);
            if (j && typeof j.detail === "string")
                detail = j.detail;
        }
        catch {
            /* non-JSON body */
        }
        if (detail)
            throw new Error(t(detail));
        if (r.status === 413)
            throw new Error(t("文件过大（上限 200 MB）。"));
        if (r.status === 502 || r.status === 503 || r.status === 504) {
            throw new Error(t("服务器暂时不可达 ({status})；服务可能正在重启，请稍后重试。", { status: r.status }));
        }
        throw new Error(t("服务器未能处理请求 ({status})；请稍后重试。", { status: r.status }));
    }
    return r.json();
}
export const api = {
    state: () => req("/api/state"),
    startGpu: () => req("/api/runtime/start", { method: "POST" }),
    stopGpu: () => req("/api/runtime/stop", { method: "POST" }),
    usage: () => req("/api/usage"),
    newChat: (mode, title = "") => req("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, title }),
    }),
    deleteChat: (id) => req(`/api/chats/${id}`, { method: "DELETE" }),
    createJob: (body) => req("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    }),
    cancelJob: (id) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),
    savePreset: (mode, name, params) => req(`/api/presets/${mode}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, params }),
    }),
    deletePreset: (mode, name) => req(`/api/presets/${mode}/${encodeURIComponent(name)}`, { method: "DELETE" }),
    upload: async (file) => {
        const fd = new FormData();
        fd.append("file", file);
        return req("/api/upload", { method: "POST", body: fd });
    },
};
