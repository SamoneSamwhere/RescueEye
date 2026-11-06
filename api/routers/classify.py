"""
POST /classify — Damage classification using the custom damage model
(damage_best.pt if available) or YOLOv8n-cls COCO proxy fallback.
"""
from __future__ import annotations

import base64
import io
import logging
import time
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Body, HTTPException
from PIL import Image

from services.yolo_model import (
    DAMAGE_CLASS_NAMES,
    DAMAGE_PROXY_CLASSES,
    PERSON_CLASS,
    DAMAGE_ORT_IMGSZ,
    get_damage_model,
    get_damage_ort_session,
    get_damage_ort_names,
    damage_state,
    ort_run,
)

logger = logging.getLogger("rescueeye.classify")
router = APIRouter()

CONFIDENCE_THRESHOLD = 0.35


def _decode_frame(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    return np.array(Image.open(io.BytesIO(raw)).convert("RGB"))


def _get_severity(label: str, confidence: float) -> tuple[str, str]:
    """Map damage label + confidence to (severity_tier, suggested_action)."""
    if label == "no_damage":
        return "CLEAR", "No immediate action required"
    crit_thresh = {"fire_damage": 0.80, "structural_damage": 0.80, "flood_damage": 0.80}
    mod_thresh  = {"fire_damage": 0.55, "structural_damage": 0.55, "flood_damage": 0.55}
    actions: dict[tuple[str, str], str] = {
        ("fire_damage",       "CRITICAL"): "Deploy fire suppression — immediate evacuation required",
        ("fire_damage",       "MODERATE"): "Alert fire responders — monitor active spread",
        ("fire_damage",       "MINOR"):    "Early fire signs — investigate the area",
        ("structural_damage", "CRITICAL"): "Do not enter — structural collapse risk",
        ("structural_damage", "MODERATE"): "Assess load-bearing integrity before entry",
        ("structural_damage", "MINOR"):    "Surface damage — inspect foundations",
        ("flood_damage",      "CRITICAL"): "Evacuation zone — deploy water rescue units immediately",
        ("flood_damage",      "MODERATE"): "Rising water — stage rescue assets nearby",
        ("flood_damage",      "MINOR"):    "Localised flooding — monitor water levels",
    }
    if confidence >= crit_thresh.get(label, 0.80):
        tier = "CRITICAL"
    elif confidence >= mod_thresh.get(label, 0.55):
        tier = "MODERATE"
    else:
        tier = "MINOR"
    return tier, actions.get((label, tier), f"{tier.title()} damage detected — assess area")


def _run_damage_ort(session, frame) -> "np.ndarray":
    """
    Preprocess exactly as the classifier was trained: square resize to the
    export size, RGB, scaled to 0-1, channels-first.

    Ultralytics normally does this inside its predictor; driving the session
    directly means doing it here, and getting it wrong shows up as confident
    nonsense rather than an error.
    """
    img = frame if isinstance(frame, Image.Image) else Image.fromarray(frame)
    img = img.convert("RGB")
    # Match Ultralytics' classify transform exactly: resize the SHORT edge to
    # the export size, then centre-crop. A square stretch instead of this
    # changed the prediction on 5 of 8 sample frames - it fails silently as a
    # confident wrong label, never as an error.
    s = DAMAGE_ORT_IMGSZ
    w, h = img.size
    scale = s / min(w, h)
    img = img.resize((round(w * scale), round(h * scale)), Image.BILINEAR)
    left, top = (img.width - s) // 2, (img.height - s) // 2
    img = img.crop((left, top, left + s, top + s))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    out = ort_run(session, arr)[0]
    return np.asarray(out).reshape(-1)


SCENE_SMOOTHING = 0.4      # weight of the newest reading in the running average
SCENE_MIN_CONF  = 0.5      # below this the scene is reported as no damage


def _scene_crops(frame: np.ndarray) -> list[np.ndarray]:
    """The whole frame plus left, centre and right squares of it."""
    h, w = frame.shape[:2]
    s = min(h, w)
    return [frame] + [frame[:, x:x + s] for x in np.linspace(0, w - s, 3).astype(int)]


def classify_scene(frame: np.ndarray, previous: "np.ndarray | None") -> tuple[dict, "np.ndarray | None"]:
    """
    The live scene label for a feed: classify_frame, adapted to drone footage.

    The classifier saw damage filling the frame in training (AIDER: high,
    wide aerial shots). A low drone shot of people on a roof has the flood only
    at the edges, and the centre-cropped whole frame read it as no damage
    83-98% of the time. Each damage class therefore takes its strongest score
    over the whole frame and its three squares, while "no damage" must hold in
    all of them. Readings are averaged over a few seconds so the badge follows
    the scene rather than flickering with each frame.

    Measured on the library: the flood-roof clip goes from no badge to a damage
    badge throughout; the undamaged clips (field, rescue-patrol, walkers) stay
    clear, and the fire/flood/collapse clips keep their labels.

    Returns the result and the running average to pass back next time.
    """
    session = get_damage_ort_session()
    if session is None or not damage_state().is_custom:
        return classify_frame(frame), None
    t0 = time.perf_counter()
    probs = np.array([_run_damage_ort(session, c) for c in _scene_crops(frame)])
    names = get_damage_ort_names()
    no = names.index("no_damage") if "no_damage" in names else None
    reading = probs.max(axis=0)
    if no is not None:
        reading[no] = probs[:, no].min()
    reading = reading / reading.sum()
    avg = reading if previous is None or previous.shape != reading.shape else \
        (1 - SCENE_SMOOTHING) * previous + SCENE_SMOOTHING * reading

    k = int(np.argmax(avg))
    label, conf = names[k], float(avg[k])
    if no is not None and label != "no_damage" and conf < SCENE_MIN_CONF:
        label, conf = "no_damage", float(avg[no])
    tier, action = _get_severity(label, conf)
    return {
        "label":             label,
        "confidence":        round(conf, 3),
        "severity":          tier,
        "suggested_action":  action,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "model_version":     damage_state().version,
        "inference_time_ms": round((time.perf_counter() - t0) * 1000, 1),
    }, avg


@router.post("")
async def classify_damage(payload: dict = Body(...)):
    b64 = payload.get("frame", "")
    if not b64:
        raise HTTPException(422, "'frame' field required")

    try:
        frame = _decode_frame(b64)
    except Exception as exc:
        raise HTTPException(422, f"Could not decode frame: {exc}")

    return classify_frame(frame)


def classify_frame(frame: np.ndarray) -> dict:
    """
    Whole-frame damage label for an RGB frame. Shared with /detect, which
    labels the scene on every live pass — one code path, so the preprocessing
    and label-order fixes above cannot drift between the two endpoints.
    """
    model     = get_damage_model()
    state     = damage_state()
    timestamp = datetime.now(timezone.utc).isoformat()

    if model is None:
        import random
        label = random.choice(DAMAGE_CLASS_NAMES)
        conf  = round(random.uniform(0.72, 0.93), 2)
        tier, action = _get_severity(label, conf)
        return {
            "label":            label,
            "confidence":       conf,
            "severity":         tier,
            "suggested_action": action,
            "timestamp":        timestamp,
            "model_version":    "stub",
        }

    # GPU path: the exported graph on DirectML, same provider as the victim
    # model. Classification post-processing is just a softmax over four
    # logits, so the whole Ultralytics result wrapper is unnecessary here.
    ort_session = get_damage_ort_session()
    if ort_session is not None and state.is_custom:
        t0 = time.perf_counter()
        try:
            logits = _run_damage_ort(ort_session, frame)
        except Exception as exc:
            logger.warning(f"[classify] GPU inference failed ({exc}) - using CPU model")
            ort_session = None
        else:
            inference_ms = round((time.perf_counter() - t0) * 1000, 1)
            cls_id = int(np.argmax(logits))
            conf = float(logits[cls_id])
            ort_names = get_damage_ort_names()
            label = (ort_names[cls_id] if cls_id < len(ort_names)
                     else DAMAGE_CLASS_NAMES[cls_id % len(DAMAGE_CLASS_NAMES)])
            tier, action = _get_severity(label, conf)
            logger.info(
                f"[classify] label={label} conf={conf:.2f} severity={tier} "
                f"inference={inference_ms:.0f}ms model={state.version} device=gpu"
            )
            return {
                "label":            label,
                "confidence":       round(conf, 3),
                "severity":         tier,
                "suggested_action": action,
                "timestamp":        timestamp,
                "model_version":    state.version,
                "inference_time_ms": inference_ms,
            }

    t0 = time.perf_counter()
    # Ultralytics assumes a numpy frame is BGR (OpenCV order) and runs
    # cvtColor(BGR2RGB) on it. _decode_frame produces RGB, so passing it
    # straight through fed the classifier inverted channels - reversing here
    # means the model finally sees the colours it was trained on.
    results = model(frame[:, :, ::-1], verbose=False)
    inference_ms = round((time.perf_counter() - t0) * 1000, 1)

    if state.is_custom:
        # Custom classification model — top-1 prediction
        probs   = results[0].probs
        cls_id  = int(probs.top1)
        conf    = float(probs.top1conf)
        names   = results[0].names
        label   = names.get(cls_id, DAMAGE_CLASS_NAMES[cls_id % len(DAMAGE_CLASS_NAMES)])
        # Normalise label to our 4 canonical names
        if label not in DAMAGE_CLASS_NAMES:
            label = DAMAGE_CLASS_NAMES[cls_id % len(DAMAGE_CLASS_NAMES)]
    else:
        # COCO detection fallback — find highest-conf non-person box
        best_label = None
        best_conf  = 0.0
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                if cls_id == PERSON_CLASS:
                    continue
                dmg = DAMAGE_PROXY_CLASSES.get(cls_id)
                if dmg and conf > best_conf:
                    best_label, best_conf = dmg, conf
        if best_label is None:
            best_label = "no_damage"
            best_conf  = 0.70
        label, conf = best_label, best_conf

    tier, action = _get_severity(label, float(conf))
    logger.info(
        f"[classify] label={label} conf={conf:.2f} severity={tier} "
        f"inference={inference_ms:.0f}ms model={state.version}"
    )

    return {
        "label":            label,
        "confidence":       round(float(conf), 3),
        "severity":         tier,
        "suggested_action": action,
        "timestamp":        timestamp,
        "inference_time_ms": inference_ms,
        "model_version":    state.version,
    }
