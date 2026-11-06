"""
Multi-feed behaviour of /detect: per-stream state, the worker hand-off, and the
latency fixes that go with them.

Track ids, camera motion and stillness history only mean something within one
video. With one shared tracker, feed 1's boxes were matched against feed 2's
and egomotion compared frames of different videos — these tests pin that each
stream now keeps its own.
"""
import numpy as np
import pytest

from routers import detect


@pytest.fixture(autouse=True)
def _fresh_streams():
    detect._streams.clear()
    yield
    detect._streams.clear()


def test_each_stream_keeps_its_own_tracks(client, prone_victim, bright_frame_b64):
    client.post("/detect", json={"frame": bright_frame_b64, "stream": "feedA"})
    a, b = detect.stream_state("feedA"), detect.stream_state("feedB")
    assert a is not b
    assert a.tracker._tracks and not b.tracker._tracks
    assert a.stillness._tracks and not b.stillness._tracks
    # The keyless default stream is untouched by a keyed one.
    assert not detect._default_stream.tracker._tracks


def test_a_stream_keeps_its_track_id_across_passes(client, prone_victim, bright_frame_b64):
    ids = []
    for key in ("feedA", "feedB", "feedA"):
        body = client.post("/detect", json={"frame": bright_frame_b64, "stream": key}).json()
        ids.append(body["detections"][0]["track_id"])
    assert ids[0] == ids[2]


def test_closing_a_feed_forgets_its_state(client, prone_victim, bright_frame_b64):
    client.post("/detect", json={"frame": bright_frame_b64, "stream": "feedA"})
    detect.drop_stream("feedA")
    assert not detect.stream_state("feedA").tracker._tracks


def test_response_carries_the_analysed_frame_size(client, bright_frame_b64):
    body = client.post("/detect", json={"frame": bright_frame_b64}).json()
    assert body["frameWidth"] > 0 and body["frameHeight"] > 0


def test_scene_is_reclassified_at_most_once_per_interval(client, bright_frame_b64, monkeypatch):
    calls = []
    monkeypatch.setattr(detect, "classify_scene",
                        lambda f, prev: (calls.append(1) or {"label": "no_damage", "confidence": 0.9,
                                                             "severity": "CLEAR", "suggested_action": ""}, None))
    monkeypatch.setattr(detect, "SCENE_INTERVAL_S", 3600.0)
    for _ in range(3):
        body = client.post("/detect", json={"frame": bright_frame_b64, "stream": "feedA"}).json()
        assert body["scene"]["label"] == "no_damage"     # cached answer still returned
    assert len(calls) == 1


# ── Latency fixes in the person pipeline ─────────────────────────────────────

@pytest.fixture()
def frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def test_coco_pass_is_skipped_when_pose_is_loaded_but_sees_nobody(frame, monkeypatch):
    """Pose and COCO find the same class; a second look at an empty frame was ~95ms for nothing."""
    coco_calls = []
    monkeypatch.setattr(detect, "_run_victim_primary", lambda f: ([], 10.0))
    monkeypatch.setattr(detect, "_run_pose_assist", lambda f: [])
    monkeypatch.setattr(detect, "get_pose_ort_session", lambda: object())
    monkeypatch.setattr(detect, "_run_coco_assist", lambda f: coco_calls.append(1) or [])
    detect._run_victim(frame)
    assert coco_calls == []


def test_coco_pass_still_covers_a_missing_pose_model(frame, monkeypatch):
    coco_calls = []
    monkeypatch.setattr(detect, "_run_victim_primary", lambda f: ([], 10.0))
    monkeypatch.setattr(detect, "_run_pose_assist", lambda f: [])
    monkeypatch.setattr(detect, "get_pose_ort_session", lambda: None)
    monkeypatch.setattr(detect, "get_pose_assist", lambda: None)
    monkeypatch.setattr(detect, "_run_coco_assist", lambda f: coco_calls.append(1) or [])
    detect._run_victim(frame)
    assert coco_calls == [1]


class _ConfidentVictimSession:
    """Victim graph [1, 5, N] with one confident box, so SAHI takes its early exit."""
    def get_inputs(self):
        class _I:
            name = "images"
            shape = [1, 3, 640, 640]
        return [_I()]

    def run(self, _out, _feed):
        raw = np.zeros((1, 5, 1), dtype=np.float32)
        raw[0, :, 0] = (320, 320, 40, 80, 0.95)
        return [raw]


def test_sahi_early_exit_does_not_crash(frame, monkeypatch):
    """Regression: the log line after the early exit read a variable only the tile branch set."""
    monkeypatch.setattr(detect, "get_victim_ort_session", lambda: _ConfidentVictimSession())
    detections, _ms = detect._run_victim_ort_sahi(frame)
    assert len(detections) == 1


def test_blob_matches_the_letterbox_geometry(frame):
    blob, scale, pad_x, pad_y = detect._blob(frame, 640)
    _padded, l_scale, l_pad_x, l_pad_y = detect._letterbox(frame, 640)
    assert blob.shape == (1, 3, 640, 640) and blob.dtype == np.float32
    assert (scale, pad_x, pad_y) == (l_scale, l_pad_x, l_pad_y)
    # Padding is Ultralytics' grey 114, scaled like the image.
    assert abs(float(blob[0, 0, 0, 0]) - 114 / 255) < 1e-6
    assert float(blob.max()) <= 1.0


def test_stored_casualty_carries_the_scene_it_was_seen_in(client, prone_victim, bright_frame_b64, monkeypatch):
    monkeypatch.setattr(detect, "classify_scene",
                        lambda f, prev: ({"label": "flood_damage", "confidence": 0.9, "severity": "CRITICAL",
                                          "suggested_action": ""}, None))
    client.post("/detect", json={"frame": bright_frame_b64, "stream": "feedA"})
    stored = client.get("/detections/recent?limit=5").json()["detections"]
    assert stored and stored[0]["scene"]["label"] == "flood_damage"


def test_scene_finds_damage_at_the_edge_and_smooths_it(monkeypatch):
    """A flood only at the edges of the frame still labels the scene, and one odd reading doesn't flip it."""
    import numpy as np
    from routers import classify
    names = ["fire_damage", "flood_damage", "no_damage", "structural_damage"]
    monkeypatch.setattr(classify, "get_damage_ort_session", lambda: object())
    monkeypatch.setattr(classify, "get_damage_ort_names", lambda: names)
    monkeypatch.setattr(classify, "damage_state", lambda: type("S", (), {"is_custom": True, "version": "t"})())
    # whole frame, left, centre, right: only the right square shows the flood
    readings = iter([[0, .05, .95, 0], [0, .05, .95, 0], [0, .02, .98, 0], [0, .9, .1, 0]] * 3)
    monkeypatch.setattr(classify, "_run_damage_ort", lambda s, c: np.array(next(readings), float))
    frame = np.zeros((90, 160, 3), np.uint8)
    result, avg = classify.classify_scene(frame, None)
    assert result["label"] == "flood_damage"
    # A clear reading next lowers the average but does not erase it at once.
    readings = iter([[0, 0, 1, 0]] * 4)
    result, avg = classify.classify_scene(frame, avg)
    assert avg[1] > 0.4


def test_scene_stays_clear_when_every_part_is_clear(monkeypatch):
    import numpy as np
    from routers import classify
    names = ["fire_damage", "flood_damage", "no_damage", "structural_damage"]
    monkeypatch.setattr(classify, "get_damage_ort_session", lambda: object())
    monkeypatch.setattr(classify, "get_damage_ort_names", lambda: names)
    monkeypatch.setattr(classify, "damage_state", lambda: type("S", (), {"is_custom": True, "version": "t"})())
    monkeypatch.setattr(classify, "_run_damage_ort", lambda s, c: np.array([.02, .05, .9, .03]))
    result, _ = classify.classify_scene(np.zeros((90, 160, 3), np.uint8), None)
    assert result["label"] == "no_damage"
