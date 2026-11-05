"""Deterministic patcher for FaceFusion on remote Colab GPU.

Applies and verifies the two required patches:
1. `facefusion/content_analyser.py`:
   - `pre_check()` -> `return True` (skips NSFW model downloads and pre-checks)
   - `analyse_frame()`, `analyse_image()`, `analyse_video()`, `analyse_stream()`, `detect_nsfw()` -> `return False`
2. `facefusion/core.py`:
   - `common_pre_check()` -> `return True` (bypasses the file hash integrity check on `content_analyser.py`)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

CONTENT_ANALYSER_MARKER = "# COLAB_STUDIO_PATCHED_CONTENT_ANALYSER = True"
CORE_MARKER = "# COLAB_STUDIO_PATCHED_CORE = True"

TRUE_FUNCTIONS = {"pre_check"}
FALSE_FUNCTIONS = {
    "analyse_frame",
    "analyse_image",
    "analyse_video",
    "analyse_stream",
    "detect_nsfw",
}


def _replace_function_bodies(source: str, targets: dict[str, bool]) -> tuple[str, set[str]]:
    """Replace the body of each top-level function in `targets` with `return <bool>`."""
    tree = ast.parse(source)
    lines = source.splitlines()
    matched: list[tuple[int, int, str, str, bool]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in targets and node.body:
            start_line = node.body[0].lineno - 1
            end_line = node.end_lineno or (start_line + 1)
            first_body_line = lines[start_line]
            leading_ws = first_body_line[: len(first_body_line) - len(first_body_line.lstrip())]
            if not leading_ws:
                leading_ws = "    "
            matched.append((start_line, end_line, leading_ws, node.name, targets[node.name]))

    patched_names: set[str] = set()
    for start_line, end_line, indent, name, ret_val in sorted(matched, key=lambda x: x[0], reverse=True):
        lines[start_line:end_line] = [f"{indent}return {'True' if ret_val else 'False'}"]
        patched_names.add(name)

    return "\n".join(lines) + "\n", patched_names


def patch_content_analyser(source: str) -> str:
    """Patch `facefusion/content_analyser.py` to disable NSFW checks and skip NSFW model downloads."""
    targets: dict[str, bool] = {
        **{fn: True for fn in TRUE_FUNCTIONS},
        **{fn: False for fn in FALSE_FUNCTIONS},
    }
    patched, found = _replace_function_bodies(source, targets)
    required = {"pre_check", "analyse_frame", "analyse_image", "analyse_video"}
    missing = required - found
    if missing:
        extra_lines = []
        for fn in sorted(missing):
            val = "True" if targets[fn] else "False"
            extra_lines.append(f"\ndef {fn}(*args, **kwargs) -> bool:\n    return {val}\n")
        patched = patched.rstrip("\n") + "\n" + "".join(extra_lines)
    if CONTENT_ANALYSER_MARKER not in patched:
        patched = patched.rstrip("\n") + f"\n\n{CONTENT_ANALYSER_MARKER}\n"
    if not verify_content_analyser(patched):
        raise RuntimeError("content_analyser.py 补丁校验未通过")
    return patched


def patch_core(source: str) -> str:
    """Patch `facefusion/core.py` to bypass `common_pre_check()` hash verification."""
    patched, found = _replace_function_bodies(source, {"common_pre_check": True})
    if "common_pre_check" not in found:
        raise RuntimeError("core.py 中未找到 common_pre_check 函数")
    if CORE_MARKER not in patched:
        patched = patched.rstrip("\n") + f"\n\n{CORE_MARKER}\n"
    if not verify_core(patched):
        raise RuntimeError("core.py 补丁校验未通过")
    return patched


def _returns_constant_bool(node: ast.FunctionDef, expected: bool) -> bool:
    if len(node.body) != 1:
        return False
    stmt = node.body[0]
    return (
        isinstance(stmt, ast.Return)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is expected
    )


def verify_content_analyser(source: str) -> bool:
    """Verify patched `content_analyser.py` compiles and returns constant booleans."""
    try:
        compile(source, "content_analyser.py", "exec")
        tree = ast.parse(source)
    except SyntaxError:
        return False
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for req_true in ("pre_check",):
        if req_true not in funcs or not _returns_constant_bool(funcs[req_true], True):
            return False
    for req_false in ("analyse_frame", "analyse_image", "analyse_video"):
        if req_false not in funcs or not _returns_constant_bool(funcs[req_false], False):
            return False
    if "detect_nsfw" in funcs and not _returns_constant_bool(funcs["detect_nsfw"], False):
        return False
    return CONTENT_ANALYSER_MARKER in source


def verify_core(source: str) -> bool:
    """Verify patched `core.py` compiles and `common_pre_check` returns `True` without hash checks."""
    try:
        compile(source, "core.py", "exec")
        tree = ast.parse(source)
    except SyntaxError:
        return False
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "common_pre_check" not in funcs:
        return False
    return _returns_constant_bool(funcs["common_pre_check"], True) and CORE_MARKER in source


def apply_patches(facefusion_root: str | Path) -> None:
    """Apply and verify both patches on a FaceFusion checkout directory."""
    root = Path(facefusion_root)
    ca_path = root / "facefusion" / "content_analyser.py"
    core_path = root / "facefusion" / "core.py"
    if not ca_path.is_file():
        raise FileNotFoundError(f"未找到 {ca_path}")
    if not core_path.is_file():
        raise FileNotFoundError(f"未找到 {core_path}")

    ca_patched = patch_content_analyser(ca_path.read_text(encoding="utf-8"))
    ca_path.write_text(ca_patched, encoding="utf-8")

    core_patched = patch_core(core_path.read_text(encoding="utf-8"))
    core_path.write_text(core_patched, encoding="utf-8")


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else Path("/content/facefusion")
    apply_patches(target)
    print(f"[facefusion-patch] ✓ 已完成并校验双补丁：{target}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
