"""Unit tests for the pure helper functions in routers/detect.py.
Importing this module does not trigger any model loading (that only happens
inside load_all(), called from main.py's lifespan — never imported here).
"""
import numpy as np
from routers import detect


def test_measure_brightness_black_frame_is_low():
    black = np.zeros((10, 10, 3), dtype=np.uint8)
    assert detect._measure_brightness(black) == 0.0


def test_measure_brightness_white_frame_is_high():
    white = np.full((10, 10, 3), 255, dtype=np.uint8)
    assert detect._measure_brightness(white) == 255.0


def test_measure_brightness_gray_frame_is_midpoint():
    gray = np.full((10, 10, 3), 128, dtype=np.uint8)
    assert detect._measure_brightness(gray) == 128.0


def test_bbox_to_grid_maps_into_expected_cell():
    # Center of an 8x6 grid over a 640x480 frame → roughly the middle cell
    bbox = {"x": 300, "y": 220, "w": 40, "h": 40}
    row, col = detect._bbox_to_grid(bbox, cols=8, rows=6)
    assert 0 <= row < 6
    assert 0 <= col < 8


def test_bbox_to_grid_clamps_to_last_cell_for_out_of_range_coords():
    bbox = {"x": 10_000, "y": 10_000, "w": 10, "h": 10}
    row, col = detect._bbox_to_grid(bbox, cols=8, rows=6)
    assert row == 5
    assert col == 7


def test_nms_collapses_overlapping_boxes_keeping_highest_confidence():
    boxes = np.array([
        [10, 10, 50, 50],
        [12, 12, 52, 52],   # heavily overlaps box 0
        [200, 200, 240, 240],  # disjoint — should survive independently
    ], dtype=np.float32)
    scores = np.array([0.9, 0.5, 0.8], dtype=np.float32)
    keep = detect._nms(boxes, scores, iou_thresh=0.45)
    assert 0 in keep      # higher-confidence overlapping box survives
    assert 1 not in keep  # suppressed duplicate
    assert 2 in keep      # disjoint box always survives


def test_nms_empty_input_returns_empty_list():
    assert detect._nms(np.empty((0, 4)), np.empty((0,))) == []


def test_letterbox_output_is_square_target_size():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    padded, scale, pad_x, pad_y = detect._letterbox(img, target=640)
    assert padded.shape == (640, 640, 3)
    assert scale == 640 / 640  # scaled by the larger dimension (width=640)
    assert pad_x >= 0 and pad_y >= 0


def test_thermal_lut_has_256_entries_and_valid_rgb_range():
    lut = detect._THERMAL_LUT
    assert lut.shape == (256, 3)
    assert lut.min() >= 0
    assert lut.max() <= 255


def test_apply_thermal_preserves_frame_dimensions():
    frame = np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)
    thermal = detect._apply_thermal(frame)
    assert thermal.shape == (20, 30, 3)


def test_a_hand_on_a_visible_body_is_left_to_the_body_detector():
    body = {"bbox": {"x": 100, "y": 100, "w": 80, "h": 200}, "confidence": 0.8}
    own_hand = {"bbox": {"x": 160, "y": 180, "w": 25, "h": 25}, "confidence": 0.6, "partial": True}
    buried_hand = {"bbox": {"x": 600, "y": 400, "w": 20, "h": 20}, "confidence": 0.6, "partial": True}
    assert detect._partly_buried([own_hand, buried_hand], [body]) == [buried_hand]


def test_a_weak_body_box_over_rubble_does_not_swallow_a_sure_hand():
    rubble = {"bbox": {"x": 665, "y": 0, "w": 449, "h": 349}, "confidence": 0.39}
    hand = {"bbox": {"x": 681, "y": 237, "w": 99, "h": 95}, "confidence": 0.89, "partial": True}
    assert detect._partly_buried([hand], [rubble]) == [hand]


def test_buried_detection_is_off_without_the_model(monkeypatch):
    monkeypatch.setattr(detect, "get_buried_ort_session", lambda: None)
    assert detect._run_buried(np.zeros((720, 1280, 3), dtype=np.uint8)) == []


def test_posture_model_reading_goes_to_the_overlapping_person_only():
    lying = {"bbox": {"x": 100, "y": 300, "w": 90, "h": 30}, "down": 0.95}
    standing = {"bbox": {"x": 600, "y": 200, "w": 30, "h": 80}, "down": 0.01}
    assert detect._model_down_for({"x": 105, "y": 298, "w": 85, "h": 34}, [lying, standing]) == 0.95
    assert detect._model_down_for({"x": 598, "y": 205, "w": 32, "h": 76}, [lying, standing]) == 0.01
    assert detect._model_down_for({"x": 900, "y": 500, "w": 30, "h": 80}, [lying, standing]) is None


def test_posture_model_is_off_without_the_model(monkeypatch):
    monkeypatch.setattr(detect, "get_casualty_ort_session", lambda: None)
    assert detect._run_posture_model(np.zeros((720, 1280, 3), dtype=np.uint8)) == []
