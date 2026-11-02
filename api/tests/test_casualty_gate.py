"""
Unit tests for the casualty gate.

The thing being pinned here is the distinction the system exists to make:
detectors find *people*, and only some people are casualties. Before this gate
existed every person box was relabelled "casualty", so a bystander or one of
our own rescuers raised VICTIM_DETECTED and queued for human review.

Each signal is tested in the regime where it is supposed to work, and — just
as importantly — in the regime where it is supposed to admit it cannot tell.
"""
import time

import numpy as np
import pytest

from services import casualty, responder_registry
from services.egomotion import CameraMotion


FRAME = (720, 1280, 3)


def _kps(shoulder, hip, conf=0.9):
    """A 17x3 COCO-pose array with only the shoulder/hip joints filled in."""
    kp = np.zeros((17, 3), dtype=np.float32)
    for idx in (casualty.KP_L_SHOULDER, casualty.KP_R_SHOULDER):
        kp[idx] = (shoulder[0], shoulder[1], conf)
    for idx in (casualty.KP_L_HIP, casualty.KP_R_HIP):
        kp[idx] = (hip[0], hip[1], conf)
    return kp


def _bbox(x=100, y=100, w=60, h=180):
    return {"x": x, "y": y, "w": w, "h": h}


def _box_for(*points, pad=40):
    """
    Box enclosing the given joints.

    Fixtures have to be geometrically coherent now: the gate rejects keypoints
    that fall outside their own detection box, because in a crowded frame the
    pose model pairs joints across neighbouring people.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {"x": min(xs) - pad, "y": min(ys) - pad,
            "w": (max(xs) - min(xs)) + 2 * pad, "h": (max(ys) - min(ys)) + 2 * pad}


def _judge_twice(monkeypatch, det, kps, gap=1.5):
    """
    Judge the same still body on two consecutive /detect calls. A body has to be
    seen twice before it can be confirmed, so first-frame tests go through here.
    """
    clock = [1000.0]
    monkeypatch.setattr(casualty.time, "monotonic", lambda: clock[0])
    casualty.judge(dict(det), kps, FRAME)
    clock[0] += gap
    return casualty.judge(dict(det), kps, FRAME)


@pytest.fixture(autouse=True)
def _clean():
    casualty.reset()
    responder_registry.reset()
    yield
    casualty.reset()
    responder_registry.reset()


# ── Posture ───────────────────────────────────────────────────────────────────

def test_standing_person_reads_upright():
    # Torso runs down the image: shoulders above hips.
    score, reason = casualty.posture_from_keypoints(
        _kps((200, 100), (205, 260)), _box_for((200, 100), (205, 260))
    )
    assert reason == "posture_from_pose"
    assert score == 0.0


def test_prone_body_reads_horizontal():
    # Torso runs across the image: shoulders left of hips, same height.
    score, reason = casualty.posture_from_keypoints(
        _kps((100, 200), (260, 205)), _box_for((100, 200), (260, 205))
    )
    assert reason == "posture_from_pose"
    assert score == 1.0


def test_foreshortened_torso_is_refused_not_guessed():
    """
    A near-nadir view of someone standing projects the torso to almost nothing.
    The on-screen angle is then noise, and the gate must say so rather than
    report a confident number — this is the failure mode that would otherwise
    make every standing person in an overhead shot look like a casualty.
    """
    score, reason = casualty.posture_from_keypoints(
        _kps((200, 200), (203, 204)), _bbox(w=120, h=120)
    )
    assert score is None
    assert reason == "posture_foreshortened"


def test_unseen_joints_give_no_posture():
    score, reason = casualty.posture_from_keypoints(
        _kps((200, 100), (205, 260), conf=0.05), _bbox()
    )
    assert score is None
    assert reason == "posture_no_torso"


def test_bbox_fallback_separates_tall_from_wide():
    tall, reason_tall = casualty.posture_from_bbox(_bbox(w=60, h=180))
    wide, reason_wide = casualty.posture_from_bbox(_bbox(w=180, h=60))
    assert reason_tall == reason_wide == "posture_from_bbox"
    assert tall == 0.0
    assert wide == 1.0


# ── Stillness ─────────────────────────────────────────────────────────────────

def _observe(monitor, track_id, bbox, n, motion=CameraMotion(ok=True), gap=0.0):
    result = (None, "")
    for _ in range(n):
        monitor.advance_camera(motion, FRAME)
        result = monitor.update(track_id, bbox, FRAME)
        if gap:
            time.sleep(gap)
    return result


def test_stillness_starts_unmeasured_not_zero():
    """
    None and 0.0 mean different things: "no evidence yet" must not be read as
    "this subject is moving", or every freshly acquired track would be argued
    against being a casualty.
    """
    monitor = casualty.StillnessMonitor()
    score, reason = _observe(monitor, 1, _bbox(), n=2)
    assert score is None
    assert reason == "stillness_warming_up"


def test_motionless_subject_scores_still(monkeypatch):
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.2)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    monitor = casualty.StillnessMonitor()
    score, reason = _observe(monitor, 1, _bbox(), n=6, gap=0.03)
    assert reason == "stillness_measured"
    assert score == pytest.approx(1.0)


def test_walking_subject_scores_moving(monkeypatch):
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.2)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    monitor = casualty.StillnessMonitor()
    score = None
    for step in range(6):
        monitor.advance_camera(CameraMotion(ok=True), FRAME)
        score, reason = monitor.update(1, _bbox(x=100 + step * 40), FRAME)
        time.sleep(0.03)
    assert reason == "stillness_measured"
    assert score == 0.0


def test_unknown_camera_motion_declines_to_score():
    """
    With the camera estimate failed, a motionless body and a drifting drone are
    indistinguishable. Reporting either answer would be a guess.
    """
    monitor = casualty.StillnessMonitor()
    score, reason = _observe(monitor, 1, _bbox(), n=8, motion=CameraMotion(ok=False))
    assert score is None
    assert reason == "stillness_camera_unknown"


def test_camera_motion_is_removed_from_subject_motion(monkeypatch):
    """
    The core of the stillness signal: a body that does not move over the ground
    still slides across the sensor when the drone translates. Here the subject's
    pixel position marches 30px/frame while the camera transform says the whole
    scene moved by exactly that much — the subject must read as still.
    """
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.3)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    monitor = casualty.StillnessMonitor()
    score = None
    for step in range(6):
        monitor.advance_camera(CameraMotion(dx=30.0, dy=0.0, ok=True), FRAME)
        score, reason = monitor.update(1, _bbox(x=100 + step * 30), FRAME)
        time.sleep(0.04)
    assert reason == "stillness_measured"
    assert score > 0.9


# ── Responder veto ────────────────────────────────────────────────────────────

def test_person_at_a_responder_position_is_never_a_casualty():
    responder_registry.report("user-5", 10.3157, 123.8854, name="Casey Nolan")
    det = {"bbox": _box_for((100, 200), (260, 205)), "lat": 10.3157, "lng": 123.8854,
           "track_id": 1, "subject_located": True}
    # Prone posture — the strongest casualty evidence the gate has — and it
    # still loses to knowing who this is.
    verdict = casualty.judge(det, _kps((100, 200), (260, 205)), FRAME)
    assert verdict.is_casualty is False
    assert verdict.responder == "Casey Nolan"
    assert verdict.reasons == ["known_responder"]


def test_responder_veto_is_bounded_by_distance(monkeypatch):
    responder_registry.report("user-5", 10.3157, 123.8854)
    # ~500m away: a different person entirely.
    det = {"bbox": _box_for((100, 200), (260, 205)), "lat": 10.3202, "lng": 123.8854,
           "track_id": 1, "subject_located": True}
    verdict = _judge_twice(monkeypatch, det, _kps((100, 200), (260, 205)))
    assert verdict.responder == ""
    assert verdict.is_casualty is True


# ── Fusion ────────────────────────────────────────────────────────────────────

def test_prone_body_is_promoted_on_posture_alone(monkeypatch):
    det = {"bbox": _box_for((100, 200), (260, 205)), "track_id": 1}
    verdict = _judge_twice(monkeypatch, det, _kps((100, 200), (260, 205)))
    assert verdict.is_casualty is True
    assert verdict.posture == 1.0
    assert "posture_from_pose" in verdict.reasons


def test_standing_person_is_reported_but_not_promoted():
    det = {"bbox": _box_for((200, 100), (205, 260)), "track_id": 1}
    verdict = casualty.judge(det, _kps((200, 100), (205, 260)), FRAME)
    assert verdict.is_casualty is False
    assert verdict.score == 0.0


def test_single_signal_scores_below_two_agreeing_signals(monkeypatch):
    """
    Posture alone must not score as high as posture plus a stillness window
    that agrees with it — otherwise the score cannot be used to rank what a
    reviewer should look at first.
    """
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.2)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    casualty.reset()
    prone = _kps((100, 200), (260, 205))
    bbox = _box_for((100, 200), (260, 205))

    posture_only = casualty.judge({"bbox": bbox}, prone, FRAME)

    for _ in range(6):
        casualty.monitor().advance_camera(CameraMotion(ok=True), FRAME)
        both = casualty.judge({"bbox": bbox, "track_id": 7}, prone, FRAME)
        time.sleep(0.03)

    assert both.stillness is not None
    assert both.score > posture_only.score


def test_gate_can_be_disabled(monkeypatch):
    """The old behaviour stays reachable for footage with no bystanders."""
    monkeypatch.setattr(casualty, "CASUALTY_GATE_ENABLED", False)
    verdict = casualty.judge({"bbox": _bbox(w=60, h=180), "track_id": 1}, None, FRAME)
    assert verdict.is_casualty is True
    assert verdict.reasons == ["gate_disabled"]


# ── Camera geometry ───────────────────────────────────────────────────────────

def _nadir_kps(shoulder_l, shoulder_r, hip, conf=0.9):
    kp = np.zeros((17, 3), dtype=np.float32)
    kp[casualty.KP_L_SHOULDER] = (*shoulder_l, conf)
    kp[casualty.KP_R_SHOULDER] = (*shoulder_r, conf)
    for idx in (casualty.KP_L_HIP, casualty.KP_R_HIP):
        kp[idx] = (*hip, conf)
    return kp


def test_prone_body_seen_from_nadir_is_not_read_as_standing():
    """
    Regression for a real miss on the demo footage.

    Straight down, a body lying on the sand projects with its torso running
    down the image — 11 degrees from vertical — which the oblique measurement
    scored 0.0, "standing". The real geometry was measured on that clip: torso
    58px, shoulders 38px, ratio 1.5.
    """
    kps = _nadir_kps((180, 420), (218, 420), (199, 478))
    bbox = _bbox(x=100, y=380, w=169, h=210)

    oblique, _ = casualty.posture_from_keypoints(kps, bbox, pitch_deg=-20)
    overhead, reason = casualty.posture_from_keypoints(kps, bbox, pitch_deg=-90)

    assert oblique == 0.0                      # what the old code saw
    assert reason == "posture_from_pose_nadir"
    assert overhead == 1.0                     # what the geometry actually says


def test_standing_person_seen_from_nadir_stays_upright():
    """
    The other side of the nadir measurement: a standing torso points at the
    lens and collapses to a fraction of the shoulders. Without this the fix
    would simply call everyone a casualty from overhead.
    """
    # Shoulders 40px apart, torso foreshortened to 12px.
    kps = _nadir_kps((180, 420), (220, 420), (200, 432))
    box = _box_for((180, 420), (220, 420), (200, 432))
    score, reason = casualty.posture_from_keypoints(kps, box, pitch_deg=-90)
    assert reason == "posture_from_pose_nadir"
    assert score == 0.0


def test_nadir_needs_both_shoulders():
    """Shoulder width is the yardstick; one shoulder gives nothing to divide by."""
    kp = _nadir_kps((180, 420), (218, 420), (199, 478))
    kp[casualty.KP_R_SHOULDER][2] = 0.01
    box = _box_for((180, 420), (218, 420), (199, 478))
    score, reason = casualty.posture_from_keypoints(kp, box, pitch_deg=-90)
    assert score is None
    assert reason == "posture_no_shoulder_width"


def test_unknown_pitch_falls_back_to_the_abstaining_measurement():
    """
    With pitch unknown, the oblique branch is used because it declines to
    answer on a foreshortened torso instead of guessing.
    """
    kps = _nadir_kps((180, 420), (220, 420), (200, 432))
    box = _box_for((180, 420), (220, 420), (200, 432))
    score, reason = casualty.posture_from_keypoints(kps, box, pitch_deg=None)
    assert score is None
    assert reason == "posture_foreshortened"


def test_stillness_recovers_after_a_failed_camera_estimate(monkeypatch):
    """
    Regression: a single failed camera estimate used to silence stillness for a
    continuously-tracked subject forever, because the window could only clear
    while the track went unseen — which never happens for a track seen every
    frame.
    """
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.3)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    monitor = casualty.StillnessMonitor()

    _observe(monitor, 1, _bbox(), n=5, gap=0.04)
    monitor.advance_camera(CameraMotion(ok=False), FRAME)
    assert monitor.update(1, _bbox(), FRAME) == (None, "stillness_camera_unknown")

    score, reason = _observe(monitor, 1, _bbox(), n=6, gap=0.04)
    assert reason == "stillness_measured"
    assert score == pytest.approx(1.0)


def test_stillness_window_can_hold_enough_samples_at_real_cadence():
    """
    Regression for a silent failure: the window was 8s with a 5-sample minimum,
    but a /detect round-trip takes ~2.5-3s, so the window only ever held three
    samples and stillness was never measured on real footage — every verdict
    came from posture alone, without anything saying so.

    The defaults must leave headroom at the cadence the system actually runs at.
    """
    cadence_s = 3.0
    samples_in_window = casualty.STILLNESS_WINDOW_S / cadence_s
    assert samples_in_window >= casualty.STILLNESS_MIN_SAMPLES + 1

    # And the span requirement has to be reachable inside the same window.
    span_needed = casualty.STILLNESS_WINDOW_S * casualty.STILLNESS_MIN_SPAN_FRACTION
    assert span_needed / cadence_s >= casualty.STILLNESS_MIN_SAMPLES - 1


def test_track_history_outlives_the_window():
    """A TTL shorter than the window would prune a track before it could score."""
    assert casualty.STILLNESS_TRACK_TTL_S > casualty.STILLNESS_WINDOW_S


def test_veto_does_not_fire_on_a_drone_position(monkeypatch):
    """
    Safety rule. Without per-subject georeferencing every detection in a frame
    carries the aircraft's coordinate, so a drone hovering near one rescuer
    would veto every casualty in view. Missing a casualty is the worse error,
    so an unlocated detection is simply not eligible for the veto — and the
    verdict records that the veto could not be applied.
    """
    responder_registry.report("user-5", 10.3157, 123.8854, name="Casey Nolan")
    det = {"bbox": _box_for((100, 200), (260, 205)), "lat": 10.3157, "lng": 123.8854,
           "track_id": 1, "subject_located": False}
    verdict = _judge_twice(monkeypatch, det, _kps((100, 200), (260, 205)))
    assert verdict.is_casualty is True
    assert verdict.responder == ""
    assert "responder_veto_unavailable_no_subject_position" in verdict.reasons


# ── Keypoint plausibility ─────────────────────────────────────────────────────

def test_keypoints_outside_the_box_are_rejected():
    """
    Regression from stock photographs of people walking. In a crowded frame the
    pose model returned a "shoulder" sitting on a bus roof, well outside the
    box it belonged to — a torso running diagonally across the whole image at
    45 degrees, which scored as half horizontal and promoted a walking man to
    casualty.
    """
    kps = _kps((60, 40), (500, 900))          # joints sprayed across the frame
    bbox = {"x": 640, "y": 380, "w": 140, "h": 490}   # a tall, narrow person
    score, reason = casualty.posture_from_keypoints(kps, bbox)
    assert score is None
    assert reason == "posture_keypoints_outside_box"


def test_torso_longer_than_the_body_is_rejected():
    """
    A torso cannot be nearly as long as the diagonal of the box containing the
    whole body. When it is, the joints came from more than one person — the
    failure that paired one man's shoulder with another man's hip and read the
    result as a body lying flat.
    """
    kps = _kps((100, 300), (700, 320))
    bbox = {"x": 80, "y": 280, "w": 640, "h": 60}
    score, reason = casualty.posture_from_keypoints(kps, bbox)
    assert score is None
    assert reason == "posture_torso_implausible"


def test_box_shape_alone_cannot_promote_a_casualty():
    """
    Aspect ratio cannot distinguish a fallen body from two people standing side
    by side, a vehicle misread as a person, or a clump of grass. Without a
    keypoint reading or a measured stillness window there is no signal that
    actually separates a casualty from a person, so nothing is claimed.
    """
    det = {"bbox": {"x": 100, "y": 100, "w": 200, "h": 60}, "track_id": 1}
    verdict = casualty.judge(det, None, FRAME)
    assert verdict.is_casualty is False
    assert "posture_from_bbox" in verdict.reasons
    assert "no_qualifying_signal" in verdict.reasons


def test_box_shape_plus_measured_stillness_can_promote(monkeypatch):
    """Stillness is a qualifying signal, so the weak posture reading can count."""
    monkeypatch.setattr(casualty, "STILLNESS_WINDOW_S", 0.2)
    monkeypatch.setattr(casualty, "STILLNESS_MIN_SAMPLES", 3)
    casualty.reset()
    det = {"bbox": {"x": 100, "y": 100, "w": 200, "h": 60}, "track_id": 4}
    verdict = None
    for _ in range(6):
        casualty.monitor().advance_camera(CameraMotion(ok=True), FRAME)
        verdict = casualty.judge(det, None, FRAME)
        time.sleep(0.03)
    assert verdict.stillness is not None
    assert "no_qualifying_signal" not in verdict.reasons


# ── Walkers in close oblique shots ────────────────────────────────────────────

def test_first_sighting_alone_is_not_a_casualty():
    """One frame cannot tell a body on the ground from someone mid-stride."""
    det = {"bbox": _box_for((100, 200), (260, 205)), "track_id": 1}
    verdict = casualty.judge(det, _kps((100, 200), (260, 205)), FRAME)
    assert verdict.is_casualty is False
    assert "awaiting_second_sighting" in verdict.reasons


def test_walker_that_reads_as_lying_is_vetoed_by_motion(monkeypatch):
    """
    Close oblique footage with no gimbal telemetry is judged as nadir, where a
    walker's torso can read as horizontal. Two body lengths in 1.5 s is not
    something a casualty does.
    """
    clock = [1000.0]
    monkeypatch.setattr(casualty.time, "monotonic", lambda: clock[0])
    kps = _kps((100, 200), (260, 205))
    box = _box_for((100, 200), (260, 205))
    casualty.judge({"bbox": dict(box), "track_id": 1}, kps, FRAME)
    clock[0] += 1.5
    moved = dict(box, x=box["x"] + 2 * box["w"])
    shifted = kps.copy()
    shifted[:, 0] += 2 * box["w"]
    verdict = casualty.judge({"bbox": moved, "track_id": 1}, shifted, FRAME)
    assert verdict.is_casualty is False
    assert "moving" in verdict.reasons

