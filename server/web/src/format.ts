import { t } from "./i18n";

export function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return t("{n} 秒", { n: s });
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem > 0 ? t("{m} 分 {s} 秒", { m, s: rem }) : t("{n} 分钟", { n: m });
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return t("{h} 小时 {m} 分", { h, m: rm });
}

export function fmtHours(hours: number): string {
  if (hours >= 48) return t("{d} 天", { d: (hours / 24).toFixed(1) });
  return fmtDuration(hours * 3600);
}
