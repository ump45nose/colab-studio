import { Film, Image, Plus, Sparkles, Trash2, X } from "lucide-react";
import { Chat, Mode } from "./api";
import { t, useLang } from "./i18n";

export const MODES: { id: Mode; label: string; icon: typeof Image }[] = [
  { id: "image", label: "图片", icon: Image },
  { id: "video", label: "视频", icon: Film },
  { id: "faceswap", label: "换脸", icon: Sparkles },
];

interface Props {
  mode: Mode;
  onMode: (m: Mode) => void;
  chats: Chat[];
  activeChat: string | null;
  onSelectChat: (c: Chat) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  open?: boolean;
  onClose?: () => void;
}

export default function Sidebar({
  mode,
  onMode,
  chats,
  activeChat,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  open,
  onClose,
}: Props) {
  useLang();
  const modeChats = chats.filter((c) => c.mode === mode);
  const pick = (fn: () => void) => () => {
    fn();
    onClose?.();
  };

  return (
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">{t("Colab 工作台")}</span>
        {onClose && (
          <button className="icon-btn mobile-only" onClick={onClose} aria-label={t("关闭")}>
            <X size={15} />
          </button>
        )}
      </div>

      <nav className="mode-list">
        {MODES.map((m) => {
          const Icon = m.icon;
          const active = mode === m.id;
          return (
            <button
              key={m.id}
              className={`mode-btn ${active ? "active" : ""}`}
              onClick={pick(() => onMode(m.id))}
            >
              <Icon size={16} />
              <span>{t(m.label)}</span>
            </button>
          );
        })}
      </nav>

      <div className="chat-section">
        <div className="chat-section-head">
          <span>{t("历史记录")}</span>
          <button className="icon-btn" onClick={pick(onNewChat)} title={t("新对话")} aria-label={t("新对话")}>
            <Plus size={14} />
          </button>
        </div>
        <div className="chat-list">
          {modeChats.length === 0 && <div className="chat-empty">{t("暂无任务记录。")}</div>}
          {modeChats.map((c) => (
            <div
              key={c.id}
              className={`chat-item ${activeChat === c.id ? "active" : ""}`}
              onClick={pick(() => onSelectChat(c))}
            >
              <span className="chat-title">{t(c.title)}</span>
              <button
                className="chat-del"
                onClick={(e) => {
                  e.stopPropagation();
                  if (!window.confirm(t("确定删除该对话及其生成结果吗？"))) return;
                  onDeleteChat(c.id);
                }}
                title={t("删除")}
                aria-label={t("删除")}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
