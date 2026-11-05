"""ComfyUI workflow graph validation tests against `fixtures/object_info.json`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import studio, workflows

FIXTURE = Path(__file__).parent / "fixtures" / "object_info.json"
OBJECT_INFO: dict[str, dict] = json.loads(FIXTURE.read_text())


def _is_link(val) -> bool:
    return isinstance(val, list) and len(val) == 2 and isinstance(val[0], str) and isinstance(val[1], int)


def assert_valid_workflow(wf: dict[str, dict], kind: str) -> None:
    assert wf, "workflow graph cannot be empty"
    allowed_stages = set(studio.STAGES[kind])

    for nid, node in wf.items():
        ct = node["class_type"]
        assert ct in OBJECT_INFO, f"node {nid}: unknown class_type '{ct}'"
        schema = OBJECT_INFO[ct]
        req = schema["input"].get("required", {})
        opt = schema["input"].get("optional", {})
        all_specs = {**req, **opt}
        inputs = node["inputs"]

        title = node.get("_meta", {}).get("title")
        assert title in allowed_stages, (
            f"node {nid} ({ct}) title {title!r} is not in studio.STAGES[{kind!r}] ({allowed_stages})"
        )

        for rname in req:
            assert rname in inputs, f"node {nid} ({ct}): missing required input '{rname}'"

        for iname, ival in inputs.items():
            assert iname in all_specs, f"node {nid} ({ct}): unknown input '{iname}'"
            spec = all_specs[iname]
            if _is_link(ival):
                src_id, slot = ival
                assert src_id in wf, f"node {nid}.{iname}: dangling link to '{src_id}'"
                src_ct = wf[src_id]["class_type"]
                src_outs = OBJECT_INFO[src_ct]["output"]
                assert 0 <= slot < len(src_outs), f"node {nid}.{iname}: invalid output index {slot} on {src_ct}"
                out_type = src_outs[slot]
                expected_type = spec[0]
                if isinstance(expected_type, str) and expected_type != "COMBO":
                    assert out_type == expected_type, (
                        f"node {nid}.{iname}: type mismatch {src_ct}[{slot}]={out_type} != {expected_type}"
                    )
            else:
                choices = spec[0]
                if isinstance(choices, list):
                    assert ival in choices, f"node {nid}.{iname}: {ival!r} not in {choices}"


@pytest.mark.parametrize("ratio", list(workflows.RATIOS))
@pytest.mark.parametrize("size", list(workflows.IMAGE_SIZES))
def test_resolve_dims_multiples_of_32(ratio, size):
    w, h = workflows.resolve_dims(ratio, size)
    assert w >= 512 and h >= 512
    assert w % 32 == 0 and h % 32 == 0


@pytest.mark.parametrize("profile", ["krea2_noct", "z_image_turbo_nsfw"])
@pytest.mark.parametrize("turbo", [False, True])
def test_image_t2i_workflows(profile, turbo):
    wf = workflows.image_generate("a neon street in Tokyo", profile=profile, turbo=turbo, seed=42)
    assert_valid_workflow(wf, "image")


@pytest.mark.parametrize("n_refs", [1, 3])
def test_image_edit_workflows(n_refs):
    refs = [f"ref_{i}.png" for i in range(n_refs)]
    wf = workflows.image_generate("change background to sunset", images=refs, edit_resolution=1440, seed=7)
    assert_valid_workflow(wf, "image")


@pytest.mark.parametrize("profile", ["minimax_h3", "wan22_remix"])
@pytest.mark.parametrize("quality", ["turbo", "quality"])
@pytest.mark.parametrize("frames", [[], ["first.png"], ["first.png", "last.png"]])
def test_video_workflows(profile, quality, frames):
    wf = workflows.video_generate(
        "ocean waves at sunset",
        profile=profile,
        quality=quality,
        first_frame=frames[0] if len(frames) >= 1 else None,
        last_frame=frames[1] if len(frames) >= 2 else None,
        seed=99,
    )
    assert_valid_workflow(wf, "video")
