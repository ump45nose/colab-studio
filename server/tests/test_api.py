"""FastAPI REST endpoint and parameter validation tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server import app as app_mod, studio

client = TestClient(app_mod.app)


def _touch_media(name: str, content: bytes = b"x") -> str:
    studio.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (studio.MEDIA_DIR / name).write_bytes(content)
    return name


def test_get_state_initial():
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert body["runtime"]["state"] == "off"
    assert isinstance(body["chats"], list)
    assert isinstance(body["jobs"], list)


def test_csrf_same_origin_check():
    r = client.post("/api/chats", json={"mode": "image"}, headers={"Origin": "https://evil.example.com", "Host": "localhost:8765"})
    assert r.status_code == 403
    assert "跨站" in r.json()["detail"]


def test_chat_lifecycle():
    r = client.post("/api/chats", json={"mode": "image", "title": "测试对话"})
    assert r.status_code == 200
    cid = r.json()["id"]
    assert r.json()["mode"] == "image"

    r_bad = client.post("/api/chats", json={"mode": "model3d"})
    assert r_bad.status_code == 400

    r_del = client.delete(f"/api/chats/{cid}")
    assert r_del.status_code == 200
    assert client.delete(f"/api/chats/{cid}").status_code == 404


def test_upload_image_and_video_and_reject_audio():
    r_img = client.post("/api/upload", files={"file": ("face.png", b"\x89PNG\r\n", "image/png")})
    assert r_img.status_code == 200
    assert r_img.json()["kind"] == "image"

    r_vid = client.post("/api/upload", files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")})
    assert r_vid.status_code == 200
    assert r_vid.json()["kind"] == "video"

    r_aud = client.post("/api/upload", files={"file": ("voice.mp3", b"ID3", "audio/mpeg")})
    assert r_aud.status_code == 400


def test_create_image_and_video_jobs_with_profiles():
    r1 = client.post(
        "/api/jobs",
        json={
            "kind": "image",
            "prompt": "a cyberpunk street",
            "params": {"profile": "z_image_turbo_nsfw", "steps": 8, "cfg": 1.0, "sampler": "res_multistep"},
        },
    )
    assert r1.status_code == 200
    assert r1.json()["params"]["profile"] == "z_image_turbo_nsfw"

    r2 = client.post(
        "/api/jobs",
        json={
            "kind": "video",
            "prompt": "a boat on the water",
            "params": {"profile": "wan22_remix", "resolution": "480p", "seconds": 5},
        },
    )
    assert r2.status_code == 200
    assert r2.json()["params"]["profile"] == "wan22_remix"


def test_create_faceswap_job_and_validation():
    src = _touch_media("up_0000000001.png")
    tgt = _touch_media("up_0000000002.mp4")

    # Missing target file (only 1 input) should fail
    r_one = client.post("/api/jobs", json={"kind": "faceswap", "inputs": [src], "params": {}})
    assert r_one.status_code == 400

    # Valid compare_all benchmark job
    r_ok = client.post(
        "/api/jobs",
        json={
            "kind": "faceswap",
            "inputs": [src, tgt],
            "params": {
                "engine": "facefusion_cli",
                "swapper_model": "hyperswap_1a_256",
                "compare_all": True,
                "pixel_boost": "512x512",
                "enhancer_model": "codeformer",
                "enhancer_blend": 50,
            },
        },
    )
    assert r_ok.status_code == 200
    j = r_ok.json()
    assert j["kind"] == "faceswap"
    assert j["params"]["compare_all"] is True
    assert j["params"]["enhancer_blend"] == 50

    # Invalid swapper model
    r_bad = client.post(
        "/api/jobs",
        json={"kind": "faceswap", "inputs": [src, tgt], "params": {"swapper_model": "invalid"}},
    )
    assert r_bad.status_code == 400


def test_presets_save_and_delete():
    r = client.put(
        "/api/presets/faceswap",
        json={
            "name": "主力对比预设",
            "params": {"compare_all": True, "enhancer_model": "none", "enhancer_blend": 50},
        },
    )
    assert r.status_code == 200
    assert "主力对比预设" in r.json()

    r_del = client.delete("/api/presets/faceswap/主力对比预设")
    assert r_del.status_code == 200
    assert "主力对比预设" not in r_del.json()


def test_pwa_routes_served():
    r_man = client.get("/manifest.webmanifest")
    assert r_man.status_code == 200
    assert "application/manifest+json" in r_man.headers["content-type"]
    assert r_man.json()["display"] == "standalone"

    r_sw = client.get("/sw.js")
    assert r_sw.status_code == 200
    assert "javascript" in r_sw.headers["content-type"]

    r_icon = client.get("/icon.svg")
    assert r_icon.status_code == 200
    assert "image/svg+xml" in r_icon.headers["content-type"]
