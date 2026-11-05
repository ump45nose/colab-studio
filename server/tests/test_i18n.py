"""Tests that every `t("literal")` in `server/web/src` and every stage in `studio.STAGES` has an English mapping."""
from __future__ import annotations

import re
from pathlib import Path

from server import studio
from server.runtime import PACK_LABELS

WEB_SRC = Path(__file__).resolve().parent.parent / "web" / "src"
EN_TS = WEB_SRC / "en.ts"


def _parse_en_ts() -> tuple[set[str], list[re.Pattern]]:
    text = EN_TS.read_text(encoding="utf-8")
    keys = set(re.findall(r'^\s*"((?:[^"\\]|\\.)*)"\s*:', text, flags=re.MULTILINE))
    keys = {k.encode("utf-8").decode("unicode_escape") if "\\n" in k else k for k in keys}

    pat_block = text.split("export const EN")[0]
    raw_pats = re.findall(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,', pat_block)
    compiled: list[re.Pattern] = []
    for p in raw_pats:
        p = p.replace("\\n", "\n")
        parts = re.split(r"(\{\w+\})", p)
        rx = "".join(".+" if re.fullmatch(r"\{\w+\}", part) else re.escape(part) for part in parts)
        compiled.append(re.compile(f"^{rx}$", re.DOTALL))
    return keys, compiled


def _covered(s: str, keys: set[str], patterns: list[re.Pattern]) -> bool:
    if s in keys:
        return True
    return any(rx.match(s) for rx in patterns)


def test_all_ui_t_calls_are_in_en_ts():
    keys, patterns = _parse_en_ts()
    missing: list[str] = []
    t_re = re.compile(r'\bt\(\s*"((?:[^"\\]|\\.)*)"')
    for tsx in sorted(WEB_SRC.glob("*.ts*")):
        if tsx.name in ("en.ts", "i18n.ts"):
            continue
        src = tsx.read_text(encoding="utf-8")
        for m in t_re.finditer(src):
            lit = m.group(1)
            if not _covered(lit, keys, patterns):
                missing.append(f"{tsx.name}: {lit!r}")
    assert not missing, "Missing English translations in en.ts:\n" + "\n".join(missing)


def test_all_server_stages_and_pack_labels_are_in_en_ts():
    keys, patterns = _parse_en_ts()
    for kind, stages in studio.STAGES.items():
        for stg in stages:
            assert _covered(stg, keys, patterns), f"Stage {kind}:{stg!r} missing from en.ts"
    for pack, label in PACK_LABELS.items():
        assert _covered(label, keys, patterns), f"Pack label {pack}:{label!r} missing from en.ts"
