"""Tests for state persistence and media garbage collection on chat deletion."""
from __future__ import annotations

import json
from server import studio


def test_load_state_marks_unfinished_jobs_as_error():
    studio.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    studio.STATE_FILE.write_text(
        json.dumps(
            {
                "chats": {"c1": {"id": "c1", "mode": "image", "title": "测试", "created_at": 1, "updated_at": 1}},
                "jobs": {
                    "j1": {"id": "j1", "chat_id": "c1", "status": "running", "error": None},
                    "j2": {"id": "j2", "chat_id": "c1", "status": "done", "error": None},
                },
            }
        )
    )
    studio.load_state()
    assert studio.jobs["j1"]["status"] == "error"
    assert "重启" in studio.jobs["j1"]["error"]
    assert studio.jobs["j2"]["status"] == "done"


def test_delete_chat_garbage_collects_unreferenced_media():
    studio.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (studio.MEDIA_DIR / "shared.png").write_bytes(b"1")
    (studio.MEDIA_DIR / "only_c1.png").write_bytes(b"2")

    c1 = studio.create_chat("image", "c1")
    c2 = studio.create_chat("image", "c2")
    j1 = studio.enqueue(c1["id"], "image", "p1", {}, ["shared.png"])
    studio._update(j1["id"], status="done", outputs=[{"file": "only_c1.png", "url": "/media/only_c1.png", "kind": "image"}])
    studio.enqueue(c2["id"], "image", "p2", {}, ["shared.png"])

    assert studio.delete_chat(c1["id"]) is True
    assert not (studio.MEDIA_DIR / "only_c1.png").exists()
    assert (studio.MEDIA_DIR / "shared.png").exists()
