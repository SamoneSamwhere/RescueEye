"""
The tracker under a moving camera (services/tracker.Sort.advance_camera).

A still person seen from a flying drone slides across the image. Detection
frames are about a second apart, so the slide is often wider than the box,
and without the camera motion the same person got a new track ID each frame,
restarting the stillness test that decides whether they are a casualty.
"""
import numpy as np

from services.egomotion import CameraMotion
from services.tracker import Sort

FRAME = (720, 1280, 3)


def _det(x, y, w=30, h=30):
    return np.array([[x, y, x + w, y + h, 0.9]], dtype=np.float32)


def _ids_over_pan(compensate: bool) -> set[int]:
    trk = Sort()
    ids = set()
    x = 600.0
    for _ in range(6):
        out = trk.update(_det(x, 300))
        ids.update(int(r[5]) for r in out)
        x -= 80.0                                     # the drone pans; the person slides 80 px
        if compensate:
            trk.advance_camera(CameraMotion(dx=-80.0, ok=True), FRAME)
    return ids


def test_a_still_person_keeps_one_id_while_the_drone_pans():
    assert len(_ids_over_pan(compensate=True)) == 1


def test_without_the_camera_motion_the_same_person_splits():
    # Documents the failure the compensation fixes.
    assert len(_ids_over_pan(compensate=False)) > 1


def test_a_failed_camera_estimate_leaves_tracks_alone():
    trk = Sort()
    trk.update(_det(600, 300))
    before = trk._tracks[0].state().copy()
    trk.advance_camera(CameraMotion(dx=-80.0, ok=False), FRAME)
    assert np.allclose(trk._tracks[0].state(), before)


def test_a_zoom_in_grows_the_predicted_box():
    trk = Sort()
    trk.update(_det(620, 345, 40, 40))
    cx, cy = 640.0, 360.0
    H = np.array([[1.5, 0, cx - 1.5 * cx], [0, 1.5, cy - 1.5 * cy], [0, 0, 1.0]])
    trk.advance_camera(CameraMotion(ok=True, H=H, scale=1.5), FRAME)
    x1, y1, x2, y2 = trk._tracks[0].state()
    assert abs((x2 - x1) - 60.0) < 1.0
