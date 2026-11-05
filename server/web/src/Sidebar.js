import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Film, Image, Plus, Sparkles, Trash2, X } from "lucide-react";
import { t, useLang } from "./i18n";
export const MODES = [
    { id: "image", label: "图片", icon: Image },
    { id: "video", label: "视频", icon: Film },
    { id: "faceswap", label: "换脸", icon: Sparkles },
];
export default function Sidebar({ mode, onMode, chats, activeChat, onSelectChat, onNewChat, onDeleteChat, open, onClose, }) {
    useLang();
    const modeChats = chats.filter((c) => c.mode === mode);
    const pick = (fn) => () => {
        fn();
        onClose?.();
    };
    return (_jsxs("aside", { className: `sidebar ${open ? "open" : ""}`, children: [_jsxs("div", { className: "brand", children: [_jsx("span", { className: "brand-dot" }), _jsx("span", { className: "brand-name", children: t("Colab 工作台") }), onClose && (_jsx("button", { className: "icon-btn mobile-only", onClick: onClose, "aria-label": t("关闭"), children: _jsx(X, { size: 15 }) }))] }), _jsx("nav", { className: "mode-list", children: MODES.map((m) => {
                    const Icon = m.icon;
                    const active = mode === m.id;
                    return (_jsxs("button", { className: `mode-btn ${active ? "active" : ""}`, onClick: pick(() => onMode(m.id)), children: [_jsx(Icon, { size: 16 }), _jsx("span", { children: t(m.label) })] }, m.id));
                }) }), _jsxs("div", { className: "chat-section", children: [_jsxs("div", { className: "chat-section-head", children: [_jsx("span", { children: t("历史记录") }), _jsx("button", { className: "icon-btn", onClick: pick(onNewChat), title: t("新对话"), "aria-label": t("新对话"), children: _jsx(Plus, { size: 14 }) })] }), _jsxs("div", { className: "chat-list", children: [modeChats.length === 0 && _jsx("div", { className: "chat-empty", children: t("暂无任务记录。") }), modeChats.map((c) => (_jsxs("div", { className: `chat-item ${activeChat === c.id ? "active" : ""}`, onClick: pick(() => onSelectChat(c)), children: [_jsx("span", { className: "chat-title", children: t(c.title) }), _jsx("button", { className: "chat-del", onClick: (e) => {
                                            e.stopPropagation();
                                            if (!window.confirm(t("确定删除该对话及其生成结果吗？")))
                                                return;
                                            onDeleteChat(c.id);
                                        }, title: t("删除"), "aria-label": t("删除"), children: _jsx(Trash2, { size: 12 }) })] }, c.id)))] })] })] }));
}
