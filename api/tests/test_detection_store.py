"""Unit tests for services/detection_store.py — fully pure, no model/network I/O."""
import pytest
from services import detection_store as ds


@pytest.fixture(autouse=True)
def _clear_store():
    ds._store.clear()
    yield
    ds._store.clear()


def _det(cls="casualty", confidence=0.9, det_id="d1"):
    return {"id": det_id, "class": cls, "confidence": confidence, "bbox": {"x": 1, "y": 2, "w": 3, "h": 4}}


def test_add_and_get_recent_round_trip():
    ds.add_detections([_det()], inference_time_ms=42.0)
    recent = ds.get_recent(limit=10)
    assert len(recent) == 1
    assert recent[0]["class"] == "casualty"
    assert recent[0]["inference_time_ms"] == 42.0


def test_get_recent_returns_most_recent_first():
    ds.add_detections([_det(det_id="first")], inference_time_ms=1.0)
    ds.add_detections([_det(det_id="second")], inference_time_ms=1.0)
    recent = ds.get_recent(limit=10)
    assert [d["id"] for d in recent] == ["second", "first"]


def test_get_recent_respects_limit():
    for i in range(5):
        ds.add_detections([_det(det_id=f"d{i}")], inference_time_ms=1.0)
    recent = ds.get_recent(limit=2)
    assert len(recent) == 2
    # most recent two, most-recent-first
    assert [d["id"] for d in recent] == ["d4", "d3"]


def test_ring_buffer_evicts_oldest_beyond_max_stored():
    for i in range(ds.MAX_STORED + 10):
        ds.add_detections([_det(det_id=f"d{i}")], inference_time_ms=1.0)
    all_items = ds.get_recent(limit=ds.MAX_STORED)
    assert len(all_items) == ds.MAX_STORED
    ids = {d["id"] for d in all_items}
    # the earliest 10 should have been evicted
    assert "d0" not in ids
    assert "d9" not in ids
    assert f"d{ds.MAX_STORED + 9}" in ids


def test_detection_keeps_the_position_it_was_stamped_with():
    ds.add_detections([{**_det(), "lat": 10.3797, "lng": 123.9339,
                        "location_source": "drone_gps", "location_accuracy_m": 4.0, "drone_id": "alpha"}],
                      inference_time_ms=1.0)
    d = ds.get_recent(limit=1)[0]
    assert (d["lat"], d["lng"]) == (10.3797, 123.9339)
    assert (d["location_source"], d["location_accuracy_m"], d["drone_id"]) == ("drone_gps", 4.0, "alpha")


def test_detection_with_no_position_is_not_given_a_made_up_one():
    ds.add_detections([_det()], inference_time_ms=1.0)
    d = ds.get_recent(limit=1)[0]
    assert d["lat"] is None and d["lng"] is None
    assert d["location_source"] is None


# ── Per-detection snapshots ───────────────────────────────────────────────────

def _frame(w=640, h=480):
    import numpy as np
    return np.full((h, w, 3), 128, dtype=np.uint8)


def test_snapshot_is_cropped_and_retrievable():
    from PIL import Image
    import io
    det = _det()
    det["bbox"] = {"x": 100, "y": 80, "w": 60, "h": 90}
    ds.add_detections([det], 10.0, 640, 480, frame=_frame())

    jpeg = ds.get_snapshot(det["id"])
    assert jpeg is not None
    img = Image.open(io.BytesIO(jpeg))
    # padding widens the crop beyond the raw box, and it is capped on the long edge
    assert img.width > 60 and img.height > 90
    assert max(img.size) <= ds.SNAPSHOT_MAX_EDGE


def test_snapshot_is_optional_when_no_frame_is_passed():
    det = _det()
    ds.add_detections([det], 10.0, 640, 480)
    assert ds.get_snapshot(det["id"]) is None
    assert ds.get_recent(1)[0]["has_snapshot"] is False


def test_recent_reports_whether_a_snapshot_exists():
    det = _det()
    ds.add_detections([det], 10.0, 640, 480, frame=_frame())
    assert ds.get_recent(1)[0]["has_snapshot"] is True


def test_snapshot_of_unknown_detection_is_none():
    assert ds.get_snapshot("nope") is None


def test_crop_survives_a_box_outside_the_frame():
    """A clamped box must not produce a zero-area crop or raise."""
    det = _det()
    det["bbox"] = {"x": 600, "y": 460, "w": 200, "h": 200}
    ds.add_detections([det], 10.0, 640, 480, frame=_frame())
    assert ds.get_snapshot(det["id"]) is not None


def test_snapshot_is_evicted_with_its_detection():
    """Crops ride the bounded deque, so memory cannot grow without limit."""
    first = _det(det_id="oldest")
    ds.add_detections([first], 10.0, 640, 480, frame=_frame())
    for i in range(ds.MAX_STORED):
        ds.add_detections([_det(det_id=f"d{i}")], 10.0, 640, 480)
    assert ds.get_snapshot("oldest") is None


def test_track_id_is_kept_so_one_casualty_collapses_to_one_record():
    det = _det(det_id="t1")
    det["track_id"] = 7
    ds.add_detections([det], 10.0, 640, 480)
    assert ds.get_recent(1)[0]["track_id"] == 7


def test_track_id_is_none_when_the_tracker_did_not_supply_one():
    ds.add_detections([_det()], 10.0, 640, 480)
    assert ds.get_recent(1)[0]["track_id"] is None


def test_recent_carries_the_casualty_verdict():
    """
    The review screen asks a commander to act on the gate's verdict, so the
    reasoning has to survive the store. It previously did not: StoredDetection
    projected a fixed set of fields and silently dropped casualty_score, so the
    card could only ever show detector confidence.
    """
    ds._store.clear()
    ds.add_detections(
        [{
            "id": "d1", "class": "casualty", "confidence": 0.9,
            "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
            "lat": 10.3, "lng": 123.9,
            "casualty_score": 0.93,
            "casualty_reasons": ["posture_from_pose_nadir", "stillness_measured"],
        }],
        inference_time_ms=120.0,
    )
    row = ds.get_recent()[0]
    assert row["casualty_score"] == 0.93
    assert row["casualty_reasons"] == ["posture_from_pose_nadir", "stillness_measured"]
    ds._store.clear()


def test_scene_label_is_stamped_on_every_detection_in_the_frame():
    scene = {"label": "fire_damage", "confidence": 0.97, "severity": "CRITICAL",
             "suggested_action": "Deploy fire suppression", "timestamp": "t", "model_version": "custom_v1"}
    ds.add_detections([_det(det_id="a"), _det(det_id="b")], inference_time_ms=1.0, scene=scene)
    recent = ds.get_recent(limit=10)
    # Only what an incident needs travels with the detection.
    assert [d["scene"] for d in recent] == [{"label": "fire_damage", "confidence": 0.97, "severity": "CRITICAL"}] * 2


def test_scene_is_none_when_the_frame_was_not_classified():
    ds.add_detections([_det()], inference_time_ms=1.0)
    assert ds.get_recent(limit=1)[0]["scene"] is None
