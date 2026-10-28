"""
Tests for the multi-feed registry.

The behaviour that matters: feeds are independent (adding one must not disturb
another — the single-feed build *replaced* the running source), the cap is
enforced rather than silently evicting, and removal frees a slot.
"""
import pytest
from fastapi.testclient import TestClient

from auth_helpers import AUTH_HEADERS

from main import app
from services import feed_registry as registry
from services import supabase_db

SOURCE = "d:/RescueEye/api/data/demo_feed8_trim.mp4"


@pytest.fixture
def client():
    # Start from an empty registry so tests don't inherit the feed opened at
    # application startup.
    registry.shutdown_all()
    with TestClient(app, headers=AUTH_HEADERS) as c:
        yield c
    registry.shutdown_all()


@pytest.fixture
def empty_registry():
    registry.shutdown_all()
    yield
    registry.shutdown_all()


class TestRegistry:
    def test_add_returns_distinct_ids(self, empty_registry):
        a = registry.add_feed(source="", label="A")
        b = registry.add_feed(source="", label="B")
        assert a.id != b.id
        assert registry.count() == 2

    def test_feeds_are_independent(self, empty_registry):
        """Adding a feed must not stop or replace an existing one."""
        a = registry.add_feed(source="", label="A")
        registry.add_feed(source="", label="B")
        assert registry.get_feed(a.id).label == "A"
        assert a.stop_event.is_set() is False

    @pytest.mark.parametrize("source, kind", [
        (SOURCE, "upload"),                                   # file on disk, whatever the caller said
        ("rtsp://192.168.1.10:554/live", "live"),             # pulled from a camera
        ("rtmp://0.0.0.0:1935/live/dji", "live"),             # aircraft pushes to us
        ("", "synthetic"),
    ])
    def test_kind_follows_the_source(self, empty_registry, monkeypatch, source, kind):
        monkeypatch.setattr(registry, "_start_producer", lambda feed: None)
        assert registry.add_feed(source=source, kind="live").kind == kind

    def test_cap_is_enforced(self, empty_registry):
        for i in range(registry.MAX_FEEDS):
            registry.add_feed(source="", label=f"F{i}")
        with pytest.raises(registry.FeedLimitReached):
            registry.add_feed(source="", label="one too many")
        assert registry.count() == registry.MAX_FEEDS

    def test_remove_frees_a_slot(self, empty_registry):
        made = [registry.add_feed(source="", label=f"F{i}") for i in range(registry.MAX_FEEDS)]
        registry.remove_feed(made[0].id)
        assert registry.count() == registry.MAX_FEEDS - 1
        registry.add_feed(source="", label="replacement")
        assert registry.count() == registry.MAX_FEEDS

    def test_remove_unknown_raises(self, empty_registry):
        with pytest.raises(registry.FeedNotFound):
            registry.remove_feed("nope")

    def test_primary_is_the_oldest(self, empty_registry):
        first = registry.add_feed(source="", label="first")
        registry.add_feed(source="", label="second")
        assert registry.primary_feed().id == first.id

    def test_detect_interval_widens_with_feed_count(self, empty_registry):
        """Every feed detects, so cadence stretches to hold total load steady."""
        registry.add_feed(source="", label="one")
        one = registry.detect_interval_ms()
        registry.add_feed(source="", label="two")
        two = registry.detect_interval_ms()
        assert two > one
        # And is capped so it never becomes uselessly slow.
        for i in range(registry.MAX_FEEDS - 2):
            registry.add_feed(source="", label=f"more{i}")
        assert registry.detect_interval_ms() <= registry.MAX_DETECT_INTERVAL_MS


class TestFeedEndpoints:
    def test_list_reports_capacity_and_cadence(self, client):
        res = client.get("/stream/feeds")
        assert res.status_code == 200
        body = res.json()
        assert body["max"] == registry.MAX_FEEDS
        assert "suggestedDetectIntervalMs" in body

    def test_add_feed_from_a_file_is_a_recording(self, client):
        # A file on disk is never "live", however it was added — the panel
        # would otherwise badge a looping clip LIVE.
        res = client.post("/stream/feeds", json={"source": SOURCE, "label": "Cam A"})
        assert res.status_code == 201
        assert res.json()["label"] == "Cam A"
        assert res.json()["kind"] == "upload"

    def test_add_requires_a_source(self, client):
        assert client.post("/stream/feeds", json={}).status_code == 400

    def test_fifth_feed_is_refused_with_a_clear_message(self, client):
        for i in range(registry.MAX_FEEDS):
            client.post("/stream/feeds", json={"source": SOURCE, "label": f"F{i}"})
        res = client.post("/stream/feeds", json={"source": SOURCE, "label": "fifth"})
        assert res.status_code == 409
        assert "Maximum" in res.json()["detail"]
        # Nothing was evicted to make room.
        assert client.get("/stream/feeds").json()["count"] == registry.MAX_FEEDS

    def test_delete_frees_a_slot(self, client):
        added = client.post("/stream/feeds", json={"source": SOURCE}).json()
        res = client.delete(f"/stream/feeds/{added['id']}")
        assert res.status_code == 200
        assert res.json()["removed"] == added["id"]

    def test_a_live_url_needs_a_registered_drone(self, client):
        res = client.post("/stream/feeds", json={"source": "rtsp://10.0.0.5/live"})
        assert res.status_code == 400
        assert "registered drone" in res.json()["detail"]

    def test_an_unknown_drone_is_refused(self, client, monkeypatch):
        async def no_rows(table, **filters):
            return []
        monkeypatch.setattr(supabase_db, "select", no_rows)
        res = client.post("/stream/feeds", json={"source": "rtsp://10.0.0.5/live", "droneId": "99"})
        assert res.status_code == 404

    def test_another_agencys_drone_is_refused(self, client, monkeypatch):
        async def foreign(table, **filters):
            return [{"id": 3, "callsign": "Other", "agencyId": 42}]
        monkeypatch.setattr(supabase_db, "select", foreign)
        res = client.post("/stream/feeds", json={"source": "rtsp://10.0.0.5/live", "droneId": "3"})
        assert res.status_code == 403

    def test_delete_unknown_is_404(self, client):
        assert client.delete("/stream/feeds/ghost").status_code == 404

    def test_mjpeg_for_unknown_feed_is_404(self, client):
        assert client.get("/stream/feeds/ghost/mjpeg").status_code == 404

    def test_snapshot_for_unknown_feed_is_404(self, client):
        assert client.get("/stream/feeds/ghost/snapshot").status_code == 404


class TestLegacyEndpoints:
    """The mobile app's STREAM_URL and existing docs point at these."""

    def test_status_still_reports_the_primary_feed(self, client):
        client.post("/stream/feeds", json={"source": SOURCE})
        body = client.get("/stream/status").json()
        assert "active" in body and "source" in body
        assert body["maxFeeds"] == registry.MAX_FEEDS

    def test_health_exposes_feed_count(self, client):
        body = client.get("/health").json()
        assert "feed_count" in body
        assert body["max_feeds"] == registry.MAX_FEEDS


def test_ffmpeg_cmd_caps_frame_width():
    """4K frames cost ~3x more to process per detection pass for no accuracy gain."""
    cmd = registry._build_ffmpeg_cmd("clip.mp4", 8.0)
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=8.0" in vf
    assert f"scale='min({registry.FEED_MAX_WIDTH},iw)':-1" in vf


def test_ffmpeg_cmd_keeps_network_source_flags_with_the_scale_filter():
    cmd = registry._build_ffmpeg_cmd("rtsp://cam/1", 4.0)
    assert "-rtsp_transport" in cmd
    assert "-re" not in cmd            # never pace a live source
    assert "scale='min(" in cmd[cmd.index("-vf") + 1]


def test_ffmpeg_actually_accepts_the_generated_filter():
    """
    Regression: the filter string was once built with scale=...:-2, which some
    FFmpeg builds reject ("Size values less than -1 are not acceptable"). The
    string-level assertions above still passed while every feed produced zero
    frames, so this runs the real binary against a synthetic source.
    """
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")

    vf = registry._build_ffmpeg_cmd("x", 8.0)[registry._build_ffmpeg_cmd("x", 8.0).index("-vf") + 1]
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=size=3840x2160:rate=8", "-vf", vf, "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
        capture_output=True, timeout=60,
    )
    assert proc.stdout, f"ffmpeg produced no frame: {proc.stderr.decode('utf8', 'ignore')[:300]}"

    from PIL import Image
    import io
    assert Image.open(io.BytesIO(proc.stdout)).size[0] == registry.FEED_MAX_WIDTH


def test_detect_interval_scales_with_feed_count_and_is_capped():
    base, cap = registry.BASE_DETECT_INTERVAL_MS, registry.MAX_DETECT_INTERVAL_MS
    assert base < cap
    # The cadence is a floor for a back-to-back client loop, so it has to stay
    # near a single pass (~190ms) or the overlay visibly trails the video.
    assert base <= 500, "base cadence too slow — the box will lag the casualty"
    assert registry.detect_interval_ms() <= cap
