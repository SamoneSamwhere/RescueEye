"""
HTTP contract tests for /media against a minimal app, with the store redirected
at a tmp_path so the real library is untouched.

Range handling gets its own tests because browser <video> seeking depends on a
correct 206 + Content-Range, and a plain 200 silently disables the scrubber.
"""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from routers import media as media_router
from services import media_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    media = tmp_path / "media"
    monkeypatch.setattr(media_store, "MEDIA_DIR", media)
    monkeypatch.setattr(media_store, "FRAMES_DIR", media / "frames")
    monkeypatch.setattr(media_store, "INDEX_FILE", media / "index.json")
    monkeypatch.setattr(media_store, "_probe", lambda _p: (10.0, 1280, 720))
    monkeypatch.setattr(media_store, "_extract_frame",
                        lambda v, t, dest: (dest.write_bytes(b"jpgbytes"), True)[1])
    app = FastAPI()
    app.include_router(media_router.router, prefix="/media")
    return TestClient(app, headers=AUTH_HEADERS)


def _upload(client, name="clip.mp4", data=b"0123456789" * 100, **form):
    return client.post("/media/upload",
                       files={"file": (name, io.BytesIO(data), "video/mp4")},
                       data=form)


def test_upload_returns_201_and_record(client):
    r = _upload(client, agencyId="agency-1", uploadedByName="Dana")
    assert r.status_code == 201
    body = r.json()
    assert body["original_name"] == "clip.mp4"
    assert body["agency_id"] == "agency-1"
    assert body["uploaded_by_name"] == "Dana"
    assert body["duration_sec"] == 10.0
    assert body["frame_count"] == 0


def test_upload_rejects_non_video(client):
    r = _upload(client, name="report.pdf")
    assert r.status_code == 422


def test_list_media_returns_uploaded_items(client):
    _upload(client, name="a.mp4", agencyId="agency-1")
    _upload(client, name="b.mp4", agencyId="agency-2")

    all_items = client.get("/media").json()
    assert all_items["count"] == 2

    scoped = client.get("/media", params={"agencyId": "agency-2"}).json()
    assert scoped["count"] == 1
    assert scoped["items"][0]["original_name"] == "b.mp4"


def test_get_media_404_for_unknown(client):
    assert client.get("/media/nope").status_code == 404


def test_file_download_full_body(client):
    data = b"abcdefghij" * 50
    mid = _upload(client, data=data).json()["id"]
    r = client.get(f"/media/{mid}/file")
    assert r.status_code == 200
    assert r.content == data
    assert r.headers["accept-ranges"] == "bytes"


def test_file_download_honours_range(client):
    data = bytes(range(256)) * 4          # 1024 bytes, index-addressable
    mid = _upload(client, data=data).json()["id"]

    r = client.get(f"/media/{mid}/file", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == data[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(data)}"
    assert r.headers["content-length"] == "10"


def test_open_ended_range_runs_to_eof(client):
    data = b"x" * 500
    mid = _upload(client, data=data).json()["id"]
    r = client.get(f"/media/{mid}/file", headers={"Range": "bytes=400-"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert r.headers["content-range"] == "bytes 400-499/500"


def test_unsatisfiable_range_falls_back_to_full_body(client):
    data = b"y" * 50
    mid = _upload(client, data=data).json()["id"]
    r = client.get(f"/media/{mid}/file", headers={"Range": "bytes=999-1200"})
    assert r.status_code == 200
    assert r.content == data


def test_capture_frame_then_list_and_fetch(client):
    mid = _upload(client).json()["id"]

    created = client.post(f"/media/{mid}/frames", json={"tSec": 2.5, "note": "victim?"})
    assert created.status_code == 201
    fid = created.json()["id"]
    assert created.json()["t_sec"] == 2.5

    listed = client.get(f"/media/{mid}/frames").json()
    assert listed["count"] == 1
    assert listed["items"][0]["id"] == fid

    img = client.get(f"/media/{mid}/frames/{fid}")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"

    assert client.get(f"/media/{mid}").json()["frame_count"] == 1


def test_capture_frame_rejects_bad_tsec(client):
    mid = _upload(client).json()["id"]
    r = client.post(f"/media/{mid}/frames", json={"tSec": "halfway"})
    assert r.status_code == 400


def test_capture_frame_404_for_unknown_media(client):
    assert client.post("/media/nope/frames", json={"tSec": 1}).status_code == 404


def test_thumbnail_is_served(client):
    mid = _upload(client).json()["id"]
    r = client.get(f"/media/{mid}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_delete_removes_from_listing(client):
    mid = _upload(client).json()["id"]
    assert client.delete(f"/media/{mid}").status_code == 200
    assert client.get("/media").json()["count"] == 0
    assert client.get(f"/media/{mid}").status_code == 404
    assert client.delete(f"/media/{mid}").status_code == 404


def test_stats_reports_totals(client):
    _upload(client, data=b"z" * 300)
    mid = client.get("/media").json()["items"][0]["id"]
    client.post(f"/media/{mid}/frames", json={"tSec": 1})
    s = client.get("/media/stats").json()
    assert s["count"] == 1
    assert s["bytes"] == 300
    assert s["frame_count"] == 1


# ── Live Monitoring hand-off ──────────────────────────────────────────────────

@pytest.fixture()
def registry_stub(monkeypatch):
    """Stands in for the feed registry so no FFmpeg process is started."""
    from routers import media as media_router

    class _Feed:
        def __init__(self, fid, source, label):
            self.id, self.source, self.label = fid, source, label

        def to_dict(self):
            return {"id": self.id, "source": self.source, "label": self.label}

    class _Registry:
        def __init__(self):
            self.feeds: list[_Feed] = []
            self.limit = 4

        def list_feeds(self):
            return list(self.feeds)

        def add_feed(self, source, label=None, kind="upload"):
            if len(self.feeds) >= self.limit:
                from services.feed_registry import FeedLimitReached
                raise FeedLimitReached("Maximum of 4 feeds reached")
            feed = _Feed(f"feed{len(self.feeds) + 1}", source, label)
            self.feeds.append(feed)
            return feed

        def remove_feed(self, feed_id):
            self.feeds = [f for f in self.feeds if f.id != feed_id]

    stub = _Registry()
    monkeypatch.setattr(media_router, "registry", stub)
    return stub


def test_monitor_opens_a_feed_for_the_clip(client, registry_stub):
    mid = _upload(client, name="patrol.mp4").json()["id"]
    r = client.post(f"/media/{mid}/monitor")
    assert r.status_code == 201
    body = r.json()
    assert body["reused"] is False
    assert body["mediaId"] == mid
    assert body["feed"]["label"] == "patrol.mp4"
    assert len(registry_stub.feeds) == 1


def test_monitor_is_idempotent_for_the_same_clip(client, registry_stub):
    mid = _upload(client).json()["id"]
    first = client.post(f"/media/{mid}/monitor").json()
    second = client.post(f"/media/{mid}/monitor").json()
    assert second["reused"] is True
    assert second["feed"]["id"] == first["feed"]["id"]
    assert len(registry_stub.feeds) == 1


def test_monitor_404_for_unknown_media(client, registry_stub):
    assert client.post("/media/nope/monitor").status_code == 404


def test_monitor_409_when_feed_limit_reached(client, registry_stub):
    registry_stub.limit = 0
    mid = _upload(client).json()["id"]
    assert client.post(f"/media/{mid}/monitor").status_code == 409


def test_delete_releases_a_monitoring_feed_first(client, registry_stub):
    mid = _upload(client).json()["id"]
    client.post(f"/media/{mid}/monitor")
    assert len(registry_stub.feeds) == 1

    assert client.delete(f"/media/{mid}").status_code == 200
    # the feed must be closed, or the file would still be held open on Windows
    assert registry_stub.feeds == []
    assert client.get("/media").json()["count"] == 0
