"""
POST /detect — YOLOv8 casualty detection on a base64-encoded JPEG frame.
Uses the custom victim_best.pt if available; falls back to COCO yolov8n.pt.

Phase 4: bridges high-confidence detections to Node.js /incidents (httpx,
conf ≥ 0.75, 10s cooldown per grid cell) and appends to inference log.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Body, HTTPException
from PIL import Image

from services.yolo_model import (
    DAMAGE_PROXY_CLASSES,
    PERSON_CLASS,
    get_coco_assist,
    get_coco_ort_session,
    get_fire_ort_names,
    get_fire_ort_session,
    get_pose_assist,
    get_pose_ort_session,
    get_victim_model,
    get_victim_ort_session,
    ort_run,
    victim_state,
)
from services import casualty as casualty_gate
from services.detection_store import add_detections
from services.egomotion import EgoMotionEstimator
from services import drone_locations, feed_registry, georef
from services.tracker import Sort
from routers.classify import classify_frame
from routers.logs import append_log

logger = logging.getLogger("rescueeye.detect")
router = APIRouter()

LATENCY_WARN_MS      = float(os.getenv("LATENCY_WARN_MS",      "3000"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.40"))
INCIDENT_CONF_MIN    = float(os.getenv("INCIDENT_CONF_MIN",    "0.75"))
NODE_SERVER_URL      = os.getenv("NODE_SERVER_URL", "http://localhost:3001")
DRONE_ID             = os.getenv("DRONE_ID", "DRN-01")
DRONE_CALLSIGN       = os.getenv("DRONE_CALLSIGN", "Rescue-1")
NTFY_TOPIC           = os.getenv("NTFY_TOPIC", "rescueeye-alerts")
NTFY_MIN_CONF        = float(os.getenv("NTFY_MIN_CONF", "0.10"))
GRID_COOLDOWN_S      = 10.0
NTFY_COOLDOWN_S      = 30.0
SAHI_ENABLED         = os.getenv("SAHI_ENABLED", "true").lower() == "true"
SAHI_TILES           = int(os.getenv("SAHI_TILES", "2"))      # NxN grid (2→4 tiles, 3→9 tiles)
SAHI_SKIP_CONF       = float(os.getenv("SAHI_SKIP_CONF", "0.65"))  # skip tiles if full-frame already this confident
# Close-range assist (see services/yolo_model.py). 960 is the accuracy/latency
# knee on the 1280x720 frames the stream hands us: 640 misses bodies the custom
# model also misses, and 1280 costs ~130ms more for no gain.
COCO_ASSIST_IMGSZ    = int(os.getenv("COCO_ASSIST_IMGSZ", "960"))
COCO_ASSIST_CONF     = float(os.getenv("COCO_ASSIST_CONF", "0.35"))

_grid_cooldown: dict[tuple[int, int], float] = {}
_grid_lock = asyncio.Lock()
_ntfy_last_sent: float = 0.0
_ntfy_lock = asyncio.Lock()

# SORT tracker — persists across requests, maintains Kalman state per person
_tracker = Sort(max_age=4, min_hits=1, iou_threshold=0.20)

# Camera motion between consecutive frames, so the stillness signal in
# services/casualty.py measures the subject rather than the drone.
_egomotion = EgoMotionEstimator()

# Pose assist shares the COCO assist resolution — it is the same detection
# problem at the same scale, and a separate knob would only be a way to get
# the two passes accidentally out of step.
POSE_ASSIST_CONF = float(os.getenv("POSE_ASSIST_CONF", "0.35"))

# Whether people the casualty gate rejected are reported at all. Off: the API
# only ever emits casualties, so a person walking through the search area never
# reaches an operator's screen. On: they come back labelled "person", for
# threshold tuning.
REPORT_NON_CASUALTIES = os.getenv("REPORT_NON_CASUALTIES", "false").lower() == "true"

# Fire/smoke boxes and the whole-frame damage label ride along on every pass so
# the live overlay needs no second request. Both are hazards to show, not
# subjects to track: they skip the tracker, the store and the casualty alerts.
FIRE_CONF       = float(os.getenv("FIRE_CONF", "0.35"))
SCENE_CLASSIFY  = os.getenv("SCENE_CLASSIFY", "true").lower() == "true"



def _bbox_to_grid(bbox: dict, cols: int = 8, rows: int = 6) -> tuple[int, int]:
    cx = bbox["x"] + bbox["w"] / 2
    cy = bbox["y"] + bbox["h"] / 2
    return (min(int(cy / 480 * rows), rows - 1), min(int(cx / 640 * cols), cols - 1))


async def _maybe_create_incident(detection: dict) -> None:
    if detection.get("confidence", 0) < INCIDENT_CONF_MIN:
        return
    cell = _bbox_to_grid(detection["bbox"])
    now  = time.monotonic()
    async with _grid_lock:
        if now - _grid_cooldown.get(cell, 0) < GRID_COOLDOWN_S:
            return
        _grid_cooldown[cell] = now
    class_to_type = {
        "casualty":          "VICTIM_DETECTED",
        "fire_damage":       "FIRE",
        "flood_damage":      "FLOOD",
        "structural_damage": "STRUCTURAL",
    }
    try:
        import httpx  # type: ignore
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{NODE_SERVER_URL}/incidents",
                json={
                    "type":        class_to_type.get(detection["class"], "UNKNOWN"),
                    "severity":    "HIGH" if detection["confidence"] >= 0.90 else "MEDIUM",
                    "description": (
                        f"AI detected {detection['class']} "
                        f"(conf={detection['confidence']:.2f}) via {DRONE_CALLSIGN}"
                    ),
                    "reportedBy":    "AI_SYSTEM",
                    # Where the drone spotted the casualty — the incident is
                    # pinned here, and the map shows "spotted by <callsign>".
                    "lat":           detection.get("lat"),
                    "lng":           detection.get("lng"),
                    "droneId":       DRONE_ID,
                    "droneCallsign": DRONE_CALLSIGN,
                },
            )
    except Exception as exc:
        logger.debug(f"[detect] Incident bridge error (non-fatal): {exc}")


async def _send_ntfy_alert(detection: dict) -> None:
    global _ntfy_last_sent
    if detection.get("confidence", 0) < NTFY_MIN_CONF:
        return
    now = time.monotonic()
    async with _ntfy_lock:
        if now - _ntfy_last_sent < NTFY_COOLDOWN_S:
            return
        _ntfy_last_sent = now
    # Use the coordinate already stamped onto the detection so the map pin in
    # this alert points at the same place as the incident. Falling back to the
    # drone's live position keeps the link meaningful if it's ever missing —
    # previously this rolled a fresh random coordinate, so the "GPS" in the
    # alert had no relationship to where the casualty was reported.
    lat = detection.get("lat")
    lng = detection.get("lng")
    gps = f"{round(lat, 4)}, {round(lng, 4)}" if lat is not None and lng is not None else "unknown (no drone location)"
    conf_pct = round(detection["confidence"] * 100)
    tid = detection.get("track_id", "?")
    body = (
        f"Casualty detected — {conf_pct}% confidence\n"
        f"Track ID: #{tid}\n"
        f"GPS: {gps}\n"
        f"Dispatch nearest field team immediately."
    )
    try:
        import httpx
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                content=body.encode(),
                headers={
                    "Title":    "RescueEye — Casualty Detected",
                    "Priority": "urgent",
                    "Tags":     "sos,rotating_light",
                    "Click":    f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}&zoom=17",
                },
            )
        logger.info(f"[detect] ntfy alert sent → ntfy.sh/{NTFY_TOPIC} (conf={conf_pct}%)")
    except Exception as exc:
        logger.debug(f"[detect] ntfy error (non-fatal): {exc}")


LABEL_COLORS: dict[str, tuple[int, int, int]] = {
    "casualty":          (255, 59,  59),
    "person":            (148, 163, 184),
    "fire_damage":       (255, 119, 0),
    "flood_damage":      (0,   212, 255),
    "structural_damage": (249, 115, 22),
}

# Brightness below this (0-255) triggers thermal mode
DARK_THRESHOLD = float(os.getenv("DARK_THRESHOLD", "60"))

# Inferno-like LUT: maps grayscale 0-255 → RGB thermal color
def _build_thermal_lut() -> np.ndarray:
    lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        t = i / 255.0
        if t < 0.25:
            r = int(t * 4 * 30)
            g = 0
            b = int(20 + t * 4 * 80)
        elif t < 0.5:
            r = int(30 + (t - 0.25) * 4 * 190)
            g = 0
            b = int(100 - (t - 0.25) * 4 * 90)
        elif t < 0.75:
            r = 220
            g = int((t - 0.5) * 4 * 120)
            b = 0
        else:
            r = 255
            g = int(120 + (t - 0.75) * 4 * 135)
            b = int((t - 0.75) * 4 * 60)
        lut[i] = [min(r, 255), min(g, 255), min(b, 255)]
    return lut

_THERMAL_LUT = _build_thermal_lut()


def _measure_brightness(frame_rgb: np.ndarray) -> float:
    return float(np.mean(frame_rgb))


def _apply_thermal(frame_rgb: np.ndarray) -> np.ndarray:
    """Convert RGB frame to simulated thermal using inferno colormap."""
    gray = np.mean(frame_rgb, axis=2).astype(np.uint8)
    return _THERMAL_LUT[gray]


def _annotate_frame(frame_rgb: np.ndarray, detections: list[dict]) -> str:
    """Draw bounding boxes on a downscaled frame, return as base64 JPEG thumbnail."""
    from PIL import ImageDraw
    img = Image.fromarray(frame_rgb).resize((320, 240), Image.BILINEAR)
    sx, sy = 320 / frame_rgb.shape[1], 240 / frame_rgb.shape[0]
    draw = ImageDraw.Draw(img)
    for d in detections:
        b = d["bbox"]
        x1, y1 = int(b["x"] * sx), int(b["y"] * sy)
        x2, y2 = int((b["x"] + b["w"]) * sx), int((b["y"] + b["h"]) * sy)
        color = LABEL_COLORS.get(d["class"], (255, 255, 255))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{d['class'].upper()} {round(d['confidence'] * 100)}%"
        tw, th = 7 * len(label), 12
        ly = y1 - th - 1 if y1 > th + 1 else y2 + 1
        draw.rectangle([x1, ly, x1 + tw, ly + th], fill=color)
        draw.text((x1 + 2, ly + 1), label, fill=(10, 14, 26))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=40)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _letterbox(img: np.ndarray, target: int = 1280) -> tuple[np.ndarray, float, int, int]:
    """Resize + pad to square keeping aspect ratio. Returns (padded_rgb, scale, pad_x, pad_y)."""
    h, w = img.shape[:2]
    scale = target / max(h, w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))
    resized = np.array(Image.fromarray(img).resize((new_w, new_h), Image.BILINEAR))
    pad = np.full((target, target, 3), 114, dtype=np.uint8)
    pad_y = (target - new_h) // 2
    pad_x = (target - new_w) // 2
    pad[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
    return pad, scale, pad_x, pad_y


def _input_hw(sess, default: int) -> tuple[int, int]:
    """(height, width) a graph was exported at; `default` square if dynamic."""
    shape = sess.get_inputs()[0].shape
    if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
        return int(shape[2]), int(shape[3])
    return default, default


def _blob(img: np.ndarray, target: int | tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
    """
    Letterboxed NCHW float32 input for an ONNX YOLO graph, built in one buffer.

    The old chain — PIL resize, pad, astype, /255, transpose, copy — made five
    full-size copies per model and was ~75ms of every pass. cv2 INTER_LINEAR is
    also what Ultralytics letterboxes with in training; PIL's BILINEAR
    antialiases on downscale, so the models were seeing slightly softer frames
    than they were trained on. Returns (blob, scale, pad_x, pad_y) like
    _letterbox.

    `target` may be (height, width): a graph exported at 736x1280 takes a 16:9
    frame with 16 rows of padding instead of the 560 a 1280 square needs —
    44% of a square input's compute was spent on grey bars.
    """
    th, tw = (target, target) if isinstance(target, int) else target
    h, w = img.shape[:2]
    scale = min(th / h, tw / w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (tw - new_w) // 2, (th - new_h) // 2
    blob = np.full((1, 3, th, tw), 114, dtype=np.float32)
    blob[0, :, pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized.transpose(2, 0, 1)
    blob *= 1.0 / 255.0
    return blob, scale, pad_x, pad_y


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.45) -> list[int]:
    """Simple NMS — returns surviving indices."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[1:][iou < iou_thresh]
    return keep


def _run_victim_ort(frame: np.ndarray) -> tuple[list[dict], float]:
    """GPU inference via DirectML ONNX Runtime (bypasses PyTorch entirely)."""
    sess = get_victim_ort_session()
    t0   = time.perf_counter()

    blob, scale, pad_x, pad_y = _blob(frame, _input_hw(sess, 1280))

    raw = ort_run(sess, blob)[0]  # [1, 5, 33600]

    preds = raw[0]          # [5, 33600]
    cx, cy, bw, bh = preds[0], preds[1], preds[2], preds[3]
    conf = preds[4]

    logger.info(f"[ort] threshold={CONFIDENCE_THRESHOLD} max_conf={conf.max():.4f} frame={frame.shape}")
    mask = conf >= CONFIDENCE_THRESHOLD
    if not mask.any():
        elapsed = (time.perf_counter() - t0) * 1000
        return [], round(elapsed, 1)

    cx, cy, bw, bh, conf = cx[mask], cy[mask], bw[mask], bh[mask], conf[mask]

    # Convert from padded-input coords → original frame coords
    orig_x1 = ((cx - bw / 2) - pad_x) / scale
    orig_y1 = ((cy - bh / 2) - pad_y) / scale
    orig_x2 = ((cx + bw / 2) - pad_x) / scale
    orig_y2 = ((cy + bh / 2) - pad_y) / scale

    boxes = np.stack([orig_x1, orig_y1, orig_x2, orig_y2], axis=1)
    keep  = _nms(boxes, conf, iou_thresh=0.30)

    fh, fw = frame.shape[:2]
    detections: list[dict] = []
    for i in keep:
        x1 = max(0, int(orig_x1[i]))
        y1 = max(0, int(orig_y1[i]))
        x2 = min(fw, int(orig_x2[i]))
        y2 = min(fh, int(orig_y2[i]))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append({
            "class":      "person",
            "confidence": round(float(conf[i]), 3),
            "bbox":       {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
        })

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return detections, round(elapsed_ms, 1)


def _run_victim_ort_sahi(frame: np.ndarray) -> tuple[list[dict], float]:
    """
    SAHI (Slicing Aided Hyper Inference):
    - Pass 1: full frame letterboxed to 1280 (high-res global pass)
    - Pass 2…N: NxN overlapping tiles each letterboxed to 640 (zoom-in pass)
    All detections merged then NMS'd together. Catches tiny people that the
    full-frame pass misses at altitude.
    """
    sess = get_victim_ort_session()
    t0   = time.perf_counter()
    fh, fw = frame.shape[:2]
    all_boxes:  list[list[float]] = []
    all_scores: list[float]       = []

    def _infer_tile(tile: np.ndarray, off_x: int, off_y: int, target: tuple[int, int]) -> None:
        blob, scale, pad_x, pad_y = _blob(np.ascontiguousarray(tile), target)
        raw  = ort_run(sess, blob)[0][0]  # [5, N]
        cx, cy, bw_, bh_, conf = raw[0], raw[1], raw[2], raw[3], raw[4]
        mask = conf >= CONFIDENCE_THRESHOLD
        if not mask.any():
            return
        cx, cy, bw_, bh_, conf = cx[mask], cy[mask], bw_[mask], bh_[mask], conf[mask]
        x1 = np.clip(((cx - bw_ / 2) - pad_x) / scale + off_x, 0, fw)
        y1 = np.clip(((cy - bh_ / 2) - pad_y) / scale + off_y, 0, fh)
        x2 = np.clip(((cx + bw_ / 2) - pad_x) / scale + off_x, 0, fw)
        y2 = np.clip(((cy + bh_ / 2) - pad_y) / scale + off_y, 0, fh)
        for i in range(len(conf)):
            if x2[i] > x1[i] and y2[i] > y1[i]:
                all_boxes.append([float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i])])
                all_scores.append(float(conf[i]))

    # Determine model's fixed input size from the session
    model_size = _input_hw(sess, 1280)   # e.g. (1280, 1280), or (736, 1280) for a rectangular export

    # Pass 1 — full frame (global context)
    _infer_tile(frame, 0, 0, model_size)
    n = SAHI_TILES   # logged below even when the early exit skips the tiles

    # Adaptive early-exit: if full-frame already found a confident detection,
    # tiles won't add much — skip them to save ~800ms
    if all_scores and max(all_scores) >= SAHI_SKIP_CONF:
        logger.info(f"[ort-sahi] skipping tiles — full-frame conf={max(all_scores):.2f} >= {SAHI_SKIP_CONF}")
    else:
        # Pass 2…N — NxN tile grid with 25% overlap (sequential — DirectML is single-threaded)
        tile_w = fw // n
        tile_h = fh // n
        ovl_x  = int(tile_w * 0.25)
        ovl_y  = int(tile_h * 0.25)
        for row in range(n):
            for col in range(n):
                tx1 = max(0,  col * tile_w - ovl_x)
                ty1 = max(0,  row * tile_h - ovl_y)
                tx2 = min(fw, (col + 1) * tile_w + ovl_x)
                ty2 = min(fh, (row + 1) * tile_h + ovl_y)
                _infer_tile(frame[ty1:ty2, tx1:tx2], tx1, ty1, model_size)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not all_boxes:
        return [], round(elapsed_ms, 1)

    boxes  = np.array(all_boxes,  dtype=np.float32)
    scores = np.array(all_scores, dtype=np.float32)
    keep   = _nms(boxes, scores, iou_thresh=0.30)

    detections: list[dict] = []
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        detections.append({
            "class":      "person",
            "confidence": round(float(scores[i]), 3),
            "bbox":       {"x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)},
        })

    logger.info(
        f"[ort-sahi] tiles={n}x{n} pre_nms={len(all_boxes)} "
        f"post_nms={len(detections)} inference={elapsed_ms:.0f}ms"
    )
    return detections, round(elapsed_ms, 1)


def _run_coco_assist_ort(frame: np.ndarray) -> list[dict] | None:
    """
    COCO assist through ONNX Runtime on the GPU.

    Output is [1, 84, N]: rows 0-3 are cx/cy/w/h, rows 4.. are the 80 class
    scores, so row 4 is "person". Returns None when no session is loaded, which
    tells the caller to fall back to the PyTorch path.
    """
    sess = get_coco_ort_session()
    if sess is None:
        return None
    try:
        blob, scale, pad_x, pad_y = _blob(frame, _input_hw(sess, COCO_ASSIST_IMGSZ))
        raw = ort_run(sess, blob)[0][0]   # [84, N]
    except Exception as exc:
        logger.warning(f"[detect] COCO assist ORT failed: {exc}")
        return None

    scores = raw[4 + PERSON_CLASS]
    keep = scores >= COCO_ASSIST_CONF
    if not keep.any():
        return []

    cx, cy, bw, bh = raw[0][keep], raw[1][keep], raw[2][keep], raw[3][keep]
    conf = scores[keep]
    x1 = ((cx - bw / 2) - pad_x) / scale
    y1 = ((cy - bh / 2) - pad_y) / scale
    x2 = ((cx + bw / 2) - pad_x) / scale
    y2 = ((cy + bh / 2) - pad_y) / scale

    boxes = np.stack([x1, y1, x2, y2], axis=1)
    fh, fw = frame.shape[:2]
    out: list[dict] = []
    for i in _nms(boxes, conf):
        x, y = max(0, int(boxes[i][0])), max(0, int(boxes[i][1]))
        w, h = int(boxes[i][2] - boxes[i][0]), int(boxes[i][3] - boxes[i][1])
        if w <= 0 or h <= 0:
            continue
        out.append({
            "class":      "person",
            "confidence": round(float(conf[i]), 3),
            "bbox":       {"x": x, "y": y, "w": min(fw - x, w), "h": min(fh - y, h)},
        })
    return out


def _run_hazards(frame: np.ndarray) -> list[dict]:
    """
    Fire and smoke boxes from the D-Fire detector, or [] when it isn't loaded.

    Output is [1, 4 + nc, N] like the COCO graph, with nc=2. Classes are NMS'd
    separately: smoke rises out of the flame, so a smoke box that overlaps a
    fire box is a second finding, not a duplicate of the first.
    """
    sess = get_fire_ort_session()
    if sess is None:
        return []
    try:
        blob, scale, pad_x, pad_y = _blob(frame, _input_hw(sess, 640))
        raw = ort_run(sess, blob)[0][0]   # [4+nc, N]
    except Exception as exc:
        logger.warning(f"[detect] fire ORT failed: {exc}")
        return []

    names = get_fire_ort_names()
    fh, fw = frame.shape[:2]
    out: list[dict] = []
    for cls_id, name in enumerate(names):
        scores = raw[4 + cls_id]
        keep = scores >= FIRE_CONF
        if not keep.any():
            continue
        cx, cy, bw, bh = raw[0][keep], raw[1][keep], raw[2][keep], raw[3][keep]
        conf = scores[keep]
        boxes = np.stack([
            ((cx - bw / 2) - pad_x) / scale, ((cy - bh / 2) - pad_y) / scale,
            ((cx + bw / 2) - pad_x) / scale, ((cy + bh / 2) - pad_y) / scale,
        ], axis=1)
        for i in _nms(boxes, conf):
            x, y = max(0, int(boxes[i][0])), max(0, int(boxes[i][1]))
            w, h = min(fw, int(boxes[i][2])) - x, min(fh, int(boxes[i][3])) - y
            if w <= 0 or h <= 0:
                continue
            out.append({
                "class":      name,
                "confidence": round(float(conf[i]), 3),
                "bbox":       {"x": x, "y": y, "w": w, "h": h},
            })
    return out


def _run_coco_assist(frame: np.ndarray) -> list[dict]:
    """
    Whole-body casualties via the generic COCO detector (class 0 = person).

    The custom weights are trained on VisDrone-scale targets and produce boxes
    a few dozen pixels tall, so a body filling much of the frame goes unboxed.
    This pass covers that range; results are merged, never substituted, so
    small distant targets still come from the custom model.
    """
    gpu = _run_coco_assist_ort(frame)
    if gpu is not None:
        return gpu

    model = get_coco_assist()
    if model is None:
        return []
    try:
        results = model(frame, imgsz=COCO_ASSIST_IMGSZ, classes=[PERSON_CLASS],
                        conf=COCO_ASSIST_CONF, verbose=False)
    except Exception as exc:
        logger.warning(f"[detect] COCO assist failed: {exc}")
        return []

    out: list[dict] = []
    fh, fw = frame.shape[:2]
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x, y = max(0, int(x1)), max(0, int(y1))
            out.append({
                "class":      "person",
                "confidence": round(float(box.conf[0]), 3),
                "bbox":       {"x": x, "y": y,
                               "w": min(fw - x, int(x2 - x1)),
                               "h": min(fh - y, int(y2 - y1))},
            })
    return out


def _run_pose_assist_ort(frame: np.ndarray) -> list[dict] | None:
    """
    Pose assist through ONNX Runtime on the GPU.

    Output is [1, 56, N]: rows 0-3 are cx/cy/w/h, row 4 is the person score,
    and rows 5.. are the 17 keypoints as (x, y, confidence) triples. Returns
    None when no session is loaded, which tells the caller to fall back to the
    PyTorch path.
    """
    sess = get_pose_ort_session()
    if sess is None:
        return None
    try:
        blob, scale, pad_x, pad_y = _blob(frame, _input_hw(sess, COCO_ASSIST_IMGSZ))
        raw = ort_run(sess, blob)[0][0]   # [56, N]
    except Exception as exc:
        logger.warning(f"[detect] pose assist ORT failed: {exc}")
        return None

    scores = raw[4]
    keep = scores >= POSE_ASSIST_CONF
    if not keep.any():
        return []

    cx, cy, bw, bh = raw[0][keep], raw[1][keep], raw[2][keep], raw[3][keep]
    conf = scores[keep]
    kps = raw[5:][:, keep]                      # [51, M]

    x1 = ((cx - bw / 2) - pad_x) / scale
    y1 = ((cy - bh / 2) - pad_y) / scale
    x2 = ((cx + bw / 2) - pad_x) / scale
    y2 = ((cy + bh / 2) - pad_y) / scale
    boxes = np.stack([x1, y1, x2, y2], axis=1)

    fh, fw = frame.shape[:2]
    out: list[dict] = []
    for i in _nms(boxes, conf):
        x, y = max(0, int(boxes[i][0])), max(0, int(boxes[i][1]))
        w, h = int(boxes[i][2] - boxes[i][0]), int(boxes[i][3] - boxes[i][1])
        if w <= 0 or h <= 0:
            continue
        # Keypoints share the letterbox, so they come back the same way the
        # box corners do. Confidence passes through untouched.
        triples = kps[:, i].reshape(17, 3).astype(np.float32).copy()
        triples[:, 0] = (triples[:, 0] - pad_x) / scale
        triples[:, 1] = (triples[:, 1] - pad_y) / scale
        out.append({
            "class":      "person",
            "confidence": round(float(conf[i]), 3),
            "bbox":       {"x": x, "y": y, "w": min(fw - x, w), "h": min(fh - y, h)},
            "keypoints":  triples,
        })
    return out


def _run_pose_assist(frame: np.ndarray) -> list[dict]:
    """
    People plus their COCO keypoints, for the posture signal.

    Returns the same shape as the COCO assist (class "person") with an extra
    `keypoints` entry: a 17x3 array of (x, y, confidence) in frame pixels.
    Empty when no pose model is loaded, which is a supported state — posture
    then falls back to bounding-box aspect ratio.
    """
    gpu = _run_pose_assist_ort(frame)
    if gpu is not None:
        return gpu

    model = get_pose_assist()
    if model is None:
        return []
    try:
        results = model(frame, imgsz=COCO_ASSIST_IMGSZ, conf=POSE_ASSIST_CONF,
                        classes=[PERSON_CLASS], verbose=False)
    except Exception as exc:
        logger.warning(f"[detect] pose assist failed: {exc}")
        return []

    out: list[dict] = []
    fh, fw = frame.shape[:2]
    for result in results:
        kp_all = getattr(result, "keypoints", None)
        for i, box in enumerate(result.boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x, y = max(0, int(x1)), max(0, int(y1))
            entry = {
                "class":      "person",
                "confidence": round(float(box.conf[0]), 3),
                "bbox":       {"x": x, "y": y,
                               "w": min(fw - x, int(x2 - x1)),
                               "h": min(fh - y, int(y2 - y1))},
            }
            if kp_all is not None and kp_all.data is not None and i < len(kp_all.data):
                entry["keypoints"] = kp_all.data[i].cpu().numpy()
            out.append(entry)
    return out


def _iou(a: dict, b: dict) -> float:
    """IoU of two bbox dicts."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _keypoints_for(bbox: dict, poses: list[dict], iou_min: float = 0.35):
    """
    Best-matching pose keypoints for a tracked box, or None.

    Keypoints are matched back by overlap rather than carried through the
    merge: NMS may keep the box from the custom model over the pose one, and
    the tracker rebuilds boxes from its Kalman state, so neither path can be
    relied on to preserve a field.
    """
    best, best_iou = None, iou_min
    for pose in poses:
        kps = pose.get("keypoints")
        if kps is None:
            continue
        overlap = _iou(bbox, pose["bbox"])
        if overlap >= best_iou:
            best, best_iou = kps, overlap
    return best


def _merge_detections(primary: list[dict], extra: list[dict],
                      iou_thresh: float = 0.45) -> list[dict]:
    """Union of two detector outputs, de-duplicated by NMS on the same frame."""
    combined = primary + extra
    if len(combined) < 2:
        return combined
    boxes = np.array([[d["bbox"]["x"], d["bbox"]["y"],
                       d["bbox"]["x"] + d["bbox"]["w"],
                       d["bbox"]["y"] + d["bbox"]["h"]] for d in combined], dtype=np.float32)
    scores = np.array([d["confidence"] for d in combined], dtype=np.float32)
    keep = _nms(boxes, scores, iou_thresh)
    return [combined[i] for i in keep]


def _run_victim(frame: np.ndarray) -> tuple[list[dict], float, list[dict]]:
    """
    Custom victim model plus a close-range assist pass, merged.

    The assist is the pose model when one is loaded and the plain COCO
    detector otherwise — never both. They find the same class 0 people, so
    running the pair would spend a second inference producing duplicate boxes
    for NMS to discard. The pose entries are returned alongside so the caller
    can match keypoints back to the tracked boxes.
    """
    t_all = time.perf_counter()
    detections, elapsed = _run_victim_primary(frame)

    poses = _run_pose_assist(frame)
    # Fall back to the plain COCO pass only when there is no pose model — not
    # when the pose model looked and found nobody. Both detect COCO class 0 at
    # the same threshold, so a second look at an empty frame finds nothing new,
    # and it cost ~95ms on exactly the frames a search flight is mostly made of.
    pose_loaded = get_pose_ort_session() is not None or get_pose_assist() is not None
    assist = poses if pose_loaded else _run_coco_assist(frame)
    if assist:
        detections = _merge_detections(detections, assist)
        elapsed = (time.perf_counter() - t_all) * 1000
    return detections, round(elapsed, 1), poses


def _run_victim_primary(frame: np.ndarray) -> tuple[list[dict], float]:
    # Prefer SAHI + DirectML when ORT session available and SAHI is enabled
    if get_victim_ort_session() is not None:
        if SAHI_ENABLED:
            return _run_victim_ort_sahi(frame)
        return _run_victim_ort(frame)

    model  = get_victim_model()
    state  = victim_state()
    t0     = time.perf_counter()

    if model is None:
        import random
        elapsed = (time.perf_counter() - t0) * 1000
        # Shaped like a body lying down, not standing. This path exists to
        # prove the pipeline end to end with no weights present, and since the
        # endpoint only emits casualties, an upright stub would be suppressed
        # and the stub would demonstrate nothing.
        return [
            {
                "class":      "person",
                "confidence": round(random.uniform(0.82, 0.95), 2),
                "bbox":       {"x": 80, "y": 60, "w": 110, "h": 55},
            }
        ], round(elapsed + random.uniform(40, 80), 1)

    results    = model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    detections = []
    for result in results:
        for box in result.boxes:
            cls_id  = int(box.cls[0])
            conf    = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            if state.is_custom:
                label = "person"
            elif cls_id == PERSON_CLASS:
                label = "person"
            elif cls_id in DAMAGE_PROXY_CLASSES:
                label = DAMAGE_PROXY_CLASSES[cls_id]
            else:
                continue

            detections.append({
                "class":      label,
                "confidence": round(conf, 3),
                "bbox":       {"x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)},
            })

    return detections, round(elapsed_ms, 1)


# ── Per-stream state ──────────────────────────────────────────────────────────
# Track ids, camera motion and stillness history only mean something within one
# video. They used to be single module-level objects, so with two feeds open
# the tracker matched feed 1's boxes against feed 2's, and egomotion measured
# "camera motion" between frames of different videos — which corrupted exactly
# the stillness signal the casualty gate leans on.
@dataclass
class StreamState:
    tracker:   Sort
    egomotion: EgoMotionEstimator
    stillness: casualty_gate.StillnessMonitor
    # One pass at a time per stream: tracking and stillness are sequential by
    # nature, and two overlapping passes would feed the tracker out of order.
    lock:      threading.Lock = field(default_factory=threading.Lock)
    scene:     dict | None = None
    scene_at:  float = float("-inf")
    # The feed id this stream analyses, which says which drone it is.
    key:       str | None = None


# Plain /detect callers with no stream key keep the module-level objects, so
# existing clients (and the test fixtures that reset _tracker) are unchanged.
_default_stream = StreamState(_tracker, _egomotion, casualty_gate.monitor())
_streams: dict[str, StreamState] = {}
_streams_lock = threading.Lock()


def stream_state(key: str | None) -> StreamState:
    if not key:
        return _default_stream
    with _streams_lock:
        st = _streams.get(key)
        if st is None:
            st = _streams[key] = StreamState(
                Sort(max_age=4, min_hits=1, iou_threshold=0.20),
                EgoMotionEstimator(),
                casualty_gate.StillnessMonitor(),
                key=key,
            )
        return st


DEFAULT_GIMBAL_PITCH_DEG = float(os.getenv("GIMBAL_PITCH_DEG", "-90"))


def _drone_location(stream_key: str | None) -> drone_locations.DroneLocation | None:
    """
    Where the drone behind this stream is (services/drone_locations.py).

    A feed of a live drone is looked up by its drone id. A recording, or a
    caller with no feed, has no aircraft to ask; demo mode still gives it the
    simulated track, and otherwise its detections carry no position at all.
    """
    drone_id = None
    if stream_key:
        try:
            drone_id = feed_registry.get_feed(stream_key).drone_id
        except feed_registry.FeedNotFound:
            drone_id = None
    return drone_locations.locate(drone_id or "")


def drop_stream(key: str) -> None:
    """Forget a closed feed's tracks, so a later feed never inherits them."""
    with _streams_lock:
        _streams.pop(key, None)


# Inference runs off the event loop. Done inline, a ~150ms pass froze every
# other request for its duration — including the MJPEG generators, so all
# four feeds stuttered whenever any one of them was being analysed. Two
# workers let one stream's CPU work (decode, egomotion, NMS, gate) overlap
# another's GPU work; GPU calls themselves are serialised by GPU_LOCK.
DETECT_WORKERS = int(os.getenv("DETECT_WORKERS", "2"))
_pool = ThreadPoolExecutor(max_workers=DETECT_WORKERS, thread_name_prefix="detect")

# The scene label is a whole-frame judgement that changes over seconds, not
# frames; classifying it on every pass of every feed was paying for the same
# answer again. Fire/smoke boxes are NOT throttled: the drone moves, so a box
# cached for even a second would sit on the wrong patch of ground.
SCENE_INTERVAL_S = float(os.getenv("SCENE_INTERVAL_S", "1.0"))


def _decode_jpeg(raw: bytes) -> np.ndarray:
    """JPEG bytes -> RGB array. cv2 decodes a 1280x720 frame in a third of PIL's time."""
    arr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        # Not something cv2 can read; PIL gives a useful error message for it.
        return np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def _analyse(jpeg: bytes, stream: StreamState, want_annotation: bool,
             force_mode: str | None) -> dict:
    """Everything that costs time. Runs on a worker thread; touches no shared stores."""
    frame = _decode_jpeg(jpeg)

    # ── Dual-technology mode selection ────────────────────────────────────────
    brightness = _measure_brightness(frame)
    if force_mode in ("visual", "thermal"):
        mode = force_mode
    else:
        mode = "thermal" if brightness < DARK_THRESHOLD else "visual"

    # Thermal/life-sensor mode: display as infrared colormap, run YOLO on the
    # original RGB (the colouring is display-only). The class stays "casualty"
    # — thermal vs visual is reported in `mode`, so it does not need a second
    # name for the same subject.
    display_frame = _apply_thermal(frame) if (mode == "thermal" and want_annotation) else frame

    with stream.lock:
        detections, inference_ms, poses = _run_victim(frame)

        # ── SORT tracking — assign persistent IDs via Kalman filter ─────────
        fh, fw = frame.shape[:2]
        if detections:
            det_arr = np.array([
                [d["bbox"]["x"], d["bbox"]["y"],
                 d["bbox"]["x"] + d["bbox"]["w"],
                 d["bbox"]["y"] + d["bbox"]["h"],
                 d["confidence"]]
                for d in detections
            ], dtype=np.float32)
            tracked = stream.tracker.update(det_arr)  # [M, 6]: x1,y1,x2,y2,score,track_id
            detections = []
            for row in tracked:
                x1, y1, x2, y2, score, tid = row
                detections.append({
                    # Still a person here. The casualty verdict is assigned
                    # below, once posture, stillness and responder context are
                    # in hand — this used to hardcode "casualty" for every box.
                    "class":      "person",
                    "confidence": round(float(score), 3),
                    "track_id":   int(tid),
                    "bbox":       {
                        "x": max(0, int(x1)), "y": max(0, int(y1)),
                        "w": min(fw - max(0, int(x1)), int(x2 - x1)),
                        "h": min(fh - max(0, int(y1)), int(y2 - y1)),
                    },
                })
        else:
            stream.tracker.update(np.empty((0, 5), dtype=np.float32))

        frame_id  = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # One position for the whole frame: every casualty visible in this
        # frame is on the ground beneath the drone at this instant. Sampling a
        # fresh random coordinate per detection (the previous behaviour)
        # scattered casualties from a single frame kilometres apart on the map.
        # It is *this* feed's drone, from the most accurate source available,
        # and None when nothing knows where that drone is.
        location = _drone_location(stream.key)
        lat = round(location.lat, 6) if location else None
        lng = round(location.lng, 6) if location else None

        # Each subject gets its own ground coordinate where the geometry allows
        # it, falling back to the drone's. `subject_located` records which
        # happened — the responder veto below must not act on a position that
        # is really the aircraft's, or a drone hovering near one rescuer would
        # suppress every casualty in the frame.
        pitch_deg = (location.gimbal_pitch_deg
                     if location and location.gimbal_pitch_deg is not None else DEFAULT_GIMBAL_PITCH_DEG)
        annotated = []
        for i, d in enumerate(detections):
            # Placing a subject within the frame needs the aircraft's own GPS
            # and altitude; a pilot-phone position only says "near the pilot".
            fix = georef.locate_detection(
                d["bbox"], fw, fh, lat, lng,
                location.altitude_m, location.heading_deg, pitch_deg,
            ) if location and location.can_georeference else None
            annotated.append({
                **d,
                "id": f"{frame_id[:8]}-{i}",
                "timestamp": timestamp,
                "lat": round(fix[0], 6) if fix else lat,
                "lng": round(fix[1], 6) if fix else lng,
                "subject_located": fix is not None,
                # How far off this position may be, and where it came from:
                # drone_gps | pilot | simulated, or None when unknown.
                "location_source": location.source if location else None,
                "location_accuracy_m": round(location.accuracy_m, 1) if location else None,
                "drone_id": location.drone_id if location else None,
            })

        # ── Casualty gate — which of these people are casualties ────────────
        # Runs after the position stamp, because the responder veto is a
        # question about where the detection is, and after tracking, because
        # stillness is a property of a track rather than of a box.
        camera_motion = stream.egomotion.estimate(frame, exclude=annotated)
        stream.stillness.advance_camera(camera_motion, frame.shape)
        # Camera pitch (read above with the position) decides how posture is
        # measured at all — straight down, the angle of a torso means the
        # opposite of what it means from the side.
        for det in annotated:
            verdict = casualty_gate.judge(det, _keypoints_for(det["bbox"], poses),
                                          frame.shape, pitch_deg, monitor=stream.stillness)
            det["class"] = "casualty" if verdict.is_casualty else "person"
            det.update(verdict.as_fields())
            det["camera_motion_known"] = camera_motion.ok

        # ── Hazards — where the fire is, and what the scene is ──────────────
        # Run on the original frame, never the thermal display copy: both
        # models were trained on colour, and flame is the one thing the
        # inferno LUT would make look like everything else.
        hazards = _run_hazards(frame)
        if SCENE_CLASSIFY and time.monotonic() - stream.scene_at >= SCENE_INTERVAL_S:
            try:
                stream.scene = classify_frame(frame)
                stream.scene_at = time.monotonic()
            except Exception as exc:
                logger.warning(f"[detect] scene classification failed: {exc}")
        scene = stream.scene if SCENE_CLASSIFY else None

    casualties = [d for d in annotated if d["class"] == "casualty"]

    # ── What leaves this endpoint ──────────────────────────────────────────
    # Only casualties. Everyone in frame is still detected, tracked and judged
    # above — that is how a person who lies down and stops moving becomes a
    # casualty a few seconds later — but a person walking around is not output
    # at all: no box on the stream, no record in the store, no row to review.
    # Set REPORT_NON_CASUALTIES=true to see the people the gate rejected, which
    # is useful when tuning thresholds and noise the rest of the time.
    emitted = annotated if REPORT_NON_CASUALTIES else casualties

    # Callers that draw their own overlay (Live Monitoring renders the MJPEG
    # stream with positioned boxes) opt out of the annotated JPEG, which costs
    # ~60ms a frame — thermal colouring of the full frame plus a JPEG encode.
    annotated_frame = (_annotate_frame(display_frame, emitted)
                       if emitted and want_annotation else None)
    # In thermal mode always return the thermal frame so the UI can show it
    if want_annotation and mode == "thermal" and annotated_frame is None:
        buf = io.BytesIO()
        Image.fromarray(display_frame).save(buf, format="JPEG", quality=55)
        annotated_frame = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    return {
        "frame": frame, "annotated": annotated, "casualties": casualties,
        "emitted": emitted, "hazards": hazards, "scene": scene, "poses": poses,
        "camera_motion_ok": camera_motion.ok, "inference_ms": inference_ms,
        "frame_id": frame_id, "annotated_frame": annotated_frame,
        "mode": mode, "brightness": brightness,
    }


async def run_detection(jpeg: bytes, stream_key: str | None = None,
                        annotate: bool = True, force_mode: str | None = None) -> dict:
    """
    One detection pass over a JPEG frame. The heavy work runs on the detect
    pool; the store, log and alerts are written back here on the event loop,
    which is the only place they are read from.
    """
    loop = asyncio.get_running_loop()
    r = await loop.run_in_executor(
        _pool, _analyse, jpeg, stream_state(stream_key), annotate, force_mode)

    frame, emitted, casualties = r["frame"], r["emitted"], r["casualties"]
    inference_ms = r["inference_ms"]
    suppressed = len(r["annotated"]) - len(emitted)

    if inference_ms > LATENCY_WARN_MS:
        logger.warning(f"[detect] LATENCY EXCEEDED: {inference_ms:.0f}ms > {LATENCY_WARN_MS:.0f}ms")

    add_detections(emitted, inference_ms,
                   frame_width=frame.shape[1], frame_height=frame.shape[0],
                   frame=frame, scene=r["scene"])

    append_log({
        "frame_id":        r["frame_id"],
        "detection_count": len(emitted),
        "casualty_count":  len(casualties),
        "people_seen":     len(r["annotated"]),
        "inference_ms":    inference_ms,
        "model_version":   victim_state().version,
        "mode":            r["mode"],
    })

    # Bridge high-confidence detections to Node.js /incidents + ntfy push
    # (non-blocking). Only casualties escalate: a bystander or a rescuer is a
    # real detection worth showing on the stream, but it is not an incident and
    # it must not wake anyone up.
    for det in casualties:
        asyncio.create_task(_maybe_create_incident(det))
        asyncio.create_task(_send_ntfy_alert(det))

    scene = r["scene"]
    logger.info(
        f"[detect] stream={stream_key or '-'} mode={r['mode']} brightness={r['brightness']:.0f} "
        f"people={len(r['annotated'])} casualties={len(casualties)} suppressed={suppressed} "
        f"hazards={len(r['hazards'])} scene={scene['label'] if scene else '-'} "
        f"pose={'yes' if r['poses'] else 'no'} ego={'ok' if r['camera_motion_ok'] else 'unknown'} "
        f"inference={inference_ms:.0f}ms model={victim_state().version}"
    )

    return {
        "detections":        emitted,
        "casualty_count":    len(casualties),
        # People seen in this frame, and how many of them the gate withheld as
        # not casualties. Reported so "nothing found" can be told apart from
        # "found three people, none of them casualties".
        "person_count":      len(r["annotated"]),
        "suppressed_count":  suppressed,
        # Fire/smoke boxes in the same pixel space as `detections`, and the
        # damage classifier's label for the whole frame (null when disabled).
        "hazards":           r["hazards"],
        "scene":             scene,
        "inference_time_ms": inference_ms,
        "frame_id":          r["frame_id"],
        "model_version":     victim_state().version,
        "annotated_frame":   r["annotated_frame"],
        "mode":              r["mode"],
        "brightness":        round(r["brightness"], 1),
        # Boxes are in this frame's pixel space; an overlay needs it to scale.
        "frameWidth":        int(frame.shape[1]),
        "frameHeight":       int(frame.shape[0]),
    }


@router.post("")
async def detect_objects(payload: dict = Body(...)):
    b64 = payload.get("frame", "")
    if not b64:
        raise HTTPException(422, "'frame' field with base64 JPEG is required")
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    try:
        jpeg = base64.b64decode(b64)
        return await run_detection(jpeg,
                                   stream_key=payload.get("stream"),
                                   annotate=bool(payload.get("annotate", True)),
                                   force_mode=payload.get("force_mode"))
    except (ValueError, OSError) as exc:
        # binascii.Error is a ValueError; PIL's UnidentifiedImageError is an OSError.
        raise HTTPException(422, f"Could not decode frame: {exc}")
