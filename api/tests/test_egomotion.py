"""
Tests for frame-to-frame camera motion estimation.

This exists to serve the stillness signal in services/casualty.py: without it,
a motionless casualty drifts across the sensor at exactly the speed of the
drone and reads as "moving". The tests use a synthetic textured frame and
shift it by a known amount, so the expected answer is known exactly.
"""
import numpy as np
import pytest

from services.egomotion import CameraMotion, EgoMotionEstimator


def _textured_frame(w=640, h=480, seed=7):
    """
    Random blobs, not random noise: ORB needs corners it can match between
    frames, and per-pixel noise gives it nothing stable to lock onto.
    """
    rng = np.random.default_rng(seed)
    frame = np.full((h, w, 3), 40, dtype=np.uint8)
    for _ in range(120):
        cx, cy = int(rng.integers(20, w - 20)), int(rng.integers(20, h - 20))
        size = int(rng.integers(6, 18))
        colour = rng.integers(80, 255, size=3).astype(np.uint8)
        frame[cy - size // 2:cy + size // 2, cx - size // 2:cx + size // 2] = colour
    return frame


def test_first_frame_has_no_reference():
    est = EgoMotionEstimator()
    motion = est.estimate(_textured_frame())
    assert motion.ok is False


def test_static_camera_reports_no_motion():
    frame = _textured_frame()
    est = EgoMotionEstimator()
    est.estimate(frame)
    motion = est.estimate(frame.copy())
    assert motion.ok is True
    assert abs(motion.dx) < 2.0
    assert abs(motion.dy) < 2.0


def test_translation_is_recovered():
    frame = _textured_frame()
    shifted = np.roll(frame, shift=24, axis=1)  # 24px to the right
    est = EgoMotionEstimator()
    est.estimate(frame)
    motion = est.estimate(shifted)
    assert motion.ok is True
    assert motion.dx == pytest.approx(24, abs=4)
    assert abs(motion.dy) < 4


def test_blank_frames_fail_honestly():
    """
    A featureless frame — fog, an overexposed sky, a dropped feed — gives ORB
    nothing to match. The estimator must report failure rather than return a
    zero transform that would be indistinguishable from a stationary camera.
    """
    blank = np.full((480, 640, 3), 128, dtype=np.uint8)
    est = EgoMotionEstimator()
    est.estimate(blank)
    motion = est.estimate(blank.copy())
    assert motion.ok is False


def test_reset_drops_the_reference_frame():
    frame = _textured_frame()
    est = EgoMotionEstimator()
    est.estimate(frame)
    est.reset()
    assert est.estimate(frame.copy()).ok is False


def test_apply_is_identity_when_estimate_failed():
    """A failed estimate must not silently move points around."""
    motion = CameraMotion(dx=99, dy=99, ok=False)
    assert motion.apply(10.0, 20.0, 320.0, 240.0) == (10.0, 20.0)


def test_apply_shifts_by_translation():
    motion = CameraMotion(dx=30.0, dy=-10.0, scale=1.0, rotation_deg=0.0, ok=True)
    x, y = motion.apply(100.0, 100.0, 320.0, 240.0)
    assert x == pytest.approx(130.0)
    assert y == pytest.approx(90.0)


def test_a_perspective_change_is_recovered_as_a_homography():
    """
    An angled drone camera moving for a second sees the ground in perspective,
    not just shifted. The point mapping must follow it: the tracker matches a
    person's box by where this says it moved.
    """
    import cv2
    frame = _textured_frame(w=960, h=540)
    H_true = np.array([[1.04, 0.02, -30.0], [0.0, 1.06, 12.0], [0.00002, 0.00006, 1.0]])
    warped = cv2.warpPerspective(frame, H_true, (960, 540))
    est = EgoMotionEstimator()
    est.estimate(frame)
    motion = est.estimate(warped)
    assert motion.ok is True and motion.H is not None
    for x, y in [(200.0, 150.0), (760.0, 400.0)]:
        p = H_true @ np.array([x, y, 1.0])
        assert motion.apply(x, y, 480.0, 270.0) == pytest.approx((p[0] / p[2], p[1] / p[2]), abs=3)


def test_apply_uses_the_homography_when_there_is_one():
    H = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, -7.0], [0.0, 0.0, 1.0]])
    motion = CameraMotion(dx=999.0, ok=True, H=H)
    assert motion.apply(10.0, 20.0, 0.0, 0.0) == pytest.approx((15.0, 13.0))
