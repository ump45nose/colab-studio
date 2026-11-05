import { useSyncExternalStore } from "react";
import { EN, SERVER_PATTERNS } from "./en";
export const LANGS = ["zh", "en"];
const STORAGE_KEY = "studio.lang";
function detectLang() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === "zh" || saved === "en")
            return saved;
    }
    catch {
        /* ignore */
    }
    return "zh";
}
let currentLang = detectLang();
const listeners = new Set();
export function getLang() {
    return currentLang;
}
export function setLang(lang) {
    if (lang === currentLang)
        return;
    currentLang = lang;
    try {
        localStorage.setItem(STORAGE_KEY, lang);
    }
    catch {
        /* ignore */
    }
    if (typeof document !== "undefined") {
        document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    }
    listeners.forEach((fn) => fn());
}
export function useLang() {
    const lang = useSyncExternalStore((cb) => {
        listeners.add(cb);
        return () => listeners.delete(cb);
    }, () => currentLang, () => "zh");
    return [lang, setLang];
}
function interpolate(tpl, vars) {
    if (!vars)
        return tpl;
    return tpl.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}
export function t(key, vars) {
    if (currentLang === "zh")
        return interpolate(key, vars);
    const exact = EN[key];
    if (exact)
        return interpolate(exact, vars);
    return interpolate(translateServerText(key), vars);
}
let compiled = null;
function getCompiled() {
    if (compiled)
        return compiled;
    compiled = SERVER_PATTERNS.map(([src, dst]) => {
        const names = [];
        const parts = src.split(/(\{\w+\})/g);
        const rx = parts
            .map((p) => {
            const m = /^\{(\w+)\}$/.exec(p);
            if (m) {
                names.push(m[1]);
                return "([\\s\\S]+?)";
            }
            return p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        })
            .join("");
        return { re: new RegExp(`^${rx}$`), names, target: dst };
    });
    return compiled;
}
export function translateServerText(raw) {
    if (!raw || currentLang === "zh")
        return raw;
    if (EN[raw])
        return EN[raw];
    const prefixMatch = /^(\[\d+\/\d+\]\s+)([\s\S]+)$/.exec(raw);
    if (prefixMatch) {
        return prefixMatch[1] + translateServerText(prefixMatch[2]);
    }
    for (const pat of getCompiled()) {
        const m = pat.re.exec(raw);
        if (m) {
            const vars = {};
            pat.names.forEach((name, idx) => {
                vars[name] = translateServerText(m[idx + 1]);
            });
            return interpolate(pat.target, vars);
        }
    }
    return raw;
}
