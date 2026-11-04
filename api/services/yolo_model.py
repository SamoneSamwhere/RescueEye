"""
RescueEye — dual-model singleton service.

Manages two YOLOv8 models independently:
  _victim_model   — detection (casualty localisation)
  _damage_model   — classification (flood/fire/structural/no_damage)

Priority order for each:
  1. Custom-trained weights (VICTIM_MODEL_PATH / DAMAGE_MODEL_PATH env vars)
  2. Generic COCO pretrained fallback (MODEL_PATH / models/base/yolov8n.pt)

Hot-swap is supported: call reload_victim() / reload_damage() to swap weights
at runtime without restarting the server (used by /models/reload endpoint).
"""
from __future__ import annotations

import json
import ast
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("rescueeye.yolo")

# ── COCO class constants (used by detect.py when victim model is COCO) ────────
# COCO's own class index for a human; the label the API emits is "casualty".
PERSON_CLASS = 0
DAMAGE_PROXY_CLASSES: dict[int, str] = {
    72: "fire_damage",
    8:  "flood_damage",
    7:  "flood_damage",
    2:  "structural_damage",
    5:  "structural_damage",
    56: "structural_damage",
}

# ── Damage classification labels (custom model) ───────────────────────────────
# MUST stay in the model's own class order: routers/classify.py indexes this
# list by the class id the model returns whenever the graph's names are not
# available. It was previously ["flood", "fire", "structural", "no_damage"],
# which is not the trained order — every one of the four ids resolved to the
# wrong label, and id 2 turned real structural damage into "no_damage", which
# _get_severity then reports as CLEAR. Verified against damage_best.onnx.
DAMAGE_CLASS_NAMES = ["fire_damage", "flood_damage", "no_damage", "structural_damage"]


@dataclass
class ModelState:
    model:        Any   = None
    weights:      str   = ""
    version:      str   = "none"
    loaded_at:    str   = ""
    is_custom:    bool  = False
    map50:        float = 0.0
    accuracy:     float = 0.0
    meta:         dict  = field(default_factory=dict)


_victim = ModelState()
_damage = ModelState()

# Close-range assist. The custom victim weights are trained on VisDrone —
# pedestrians a few dozen pixels tall, seen from altitude — so they miss a body
# filling a large part of the frame, which is exactly what an uploaded clip
# shot from low altitude looks like. A generic COCO detector covers that case;
# the two are merged in detect.py rather than one replacing the other.
_coco_assist = ModelState()
_pose_assist = ModelState()

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).parent.parent
MODELS_DIR = REPO_ROOT / "models"
# Stock Ultralytics weights (COCO detector, pose, classifier) live apart from
# our trained models. They used to sit loose in api/, and model files are not
# in git, so a checkout made before the move still has them there — look in
# both places rather than break that machine.
BASE_DIR = MODELS_DIR / "base"


def base_weight(name: str) -> str:
    """Path to a stock weight file: models/base/<name>, else the legacy api/<name>, else models/base/<name>."""
    for candidate in (BASE_DIR / name, REPO_ROOT / name):
        if candidate.exists():
            return str(candidate)
    # Neither exists: Ultralytics downloads stock weights on first use, so
    # point it at the new home.
    return str(BASE_DIR / name)


def _load_meta(meta_file: Path) -> dict:
    try:
        return json.loads(meta_file.read_text())
    except Exception:
        return {}


def _load_single(weights_path: str, task: str, imgsz: int | None = None) -> tuple[Any, bool]:
    """Load a YOLO model via Ultralytics; returns (model, success)."""
    try:
        from ultralytics import YOLO  # type: ignore
        m = YOLO(weights_path)
        dummy = np.zeros((480, 640, 3), dtype="uint8")
        # An exported ONNX graph has its input size baked in, so warming up at
        # the Ultralytics default (640) raises on a model exported at another
        # size. The training imgsz recorded in *_meta.json is the right one.
        warm = {"imgsz": int(imgsz)} if imgsz else {}
        m(dummy, verbose=False, **warm)
        logger.info(f"[yolo] loaded {task} model on CPU via Ultralytics")
        return m, True
    except Exception as exc:
        logger.warning(f"[yolo] Failed to load {weights_path}: {exc}")
        return None, False


# Every ONNX session shares one DirectML device. Detection now runs on a small
# thread pool, and concurrent Run() calls on DML sessions are not something to
# rely on — so GPU calls are serialised here while the CPU work around them
# (decode, NMS, tracking, the casualty gate) overlaps freely across feeds.
GPU_LOCK = threading.Lock()


def ort_run(session: Any, blob: np.ndarray) -> list:
    """
    session.run for a single-input graph, under GPU_LOCK.

    An FP16 export takes and returns half precision; callers always build and
    read float32, so the cast lives here rather than at every call site.
    """
    inp = session.get_inputs()[0]
    if getattr(inp, "type", "") == "tensor(float16)":
        blob = blob.astype(np.float16)
    with GPU_LOCK:
        outs = session.run(None, {inp.name: blob})
    return [o.astype(np.float32) if getattr(o, "dtype", None) == np.float16 else o for o in outs]


def _dml_available() -> bool:
    """True when onnxruntime-directml is installed and a GPU adapter is present."""
    try:
        import onnxruntime as ort
        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ── DirectML ONNX session for victim model (GPU, no PyTorch needed) ───────────
_victim_ort_session: Any = None


def _load_victim_ort(onnx_path: str) -> None:
    """Load victim_best.onnx into an ONNX Runtime session using DirectML."""
    global _victim_ort_session
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _victim_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        active = _victim_ort_session.get_providers()[0]
        logger.info(f"[yolo] victim ONNX session ready — provider: {active} — {Path(onnx_path).name}")
    except Exception as exc:
        logger.warning(f"[yolo] ORT session failed: {exc}")
        _victim_ort_session = None


def get_victim_ort_session() -> Any:
    return _victim_ort_session


# ── DirectML ONNX session for the COCO assist ────────────────────────────────
# Ultralytics runs the assist through PyTorch, and the torch wheel on Windows is
# CPU-only — measured at 220ms a frame, several times the cost of everything
# else in the request. The same weights exported to ONNX run on DirectML in 9ms.
_coco_ort_session: Any = None


def _load_coco_ort(onnx_path: str) -> None:
    global _coco_ort_session
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _coco_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        logger.info(f"[yolo] COCO assist ONNX ready — provider: {_coco_ort_session.get_providers()[0]}")
    except Exception as exc:
        logger.warning(f"[yolo] COCO assist ORT session failed ({exc}) — falling back to PyTorch")
        _coco_ort_session = None


def get_coco_ort_session() -> Any:
    return _coco_ort_session


# -- DirectML ONNX session for the pose assist --------------------------------
# The pose pass replaced the COCO assist, and the COCO assist ran on the GPU
# while yolov8n-pose.pt runs through PyTorch on a CPU-only torch build. That
# swap roughly doubled the cost of a detection pass (~190ms to ~450ms measured)
# and the CPU it spends is the same CPU FFmpeg needs to decode and re-encode
# the video, which an operator sees as a choppier stream.
_pose_ort_session: Any = None


def _load_pose_ort(onnx_path: str) -> None:
    global _pose_ort_session
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _pose_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        logger.info(f"[yolo] pose assist ONNX ready — provider: {_pose_ort_session.get_providers()[0]} — {Path(onnx_path).name}")
    except Exception as exc:
        logger.warning(f"[yolo] pose assist ORT session failed ({exc}) — falling back to PyTorch")
        _pose_ort_session = None


def get_pose_ort_session() -> Any:
    return _pose_ort_session


# -- DirectML ONNX session for the damage classifier --------------------------
# The last model still running through PyTorch, and the torch wheel here is a
# CPU-only build, so it was the one piece of inference the GPU never touched.
# The exported graph runs on the same DirectML provider as the other two.
_damage_ort_session: Any = None
_damage_ort_names: list[str] = []
DAMAGE_ORT_IMGSZ = 224


def _load_damage_ort(onnx_path: str) -> None:
    global _damage_ort_session
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _damage_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        # Take the class order from the graph, never from a hand-written list:
        # DAMAGE_CLASS_NAMES is in a different order than the model was trained
        # in, so indexing it by the argmax silently renames every prediction.
        global _damage_ort_names
        meta = _damage_ort_session.get_modelmeta().custom_metadata_map or {}
        names = ast.literal_eval(meta["names"]) if "names" in meta else {}
        _damage_ort_names = [names[i] for i in sorted(names)] if names else list(DAMAGE_CLASS_NAMES)
        logger.info(f"[yolo] damage ONNX session ready - provider: "
                    f"{_damage_ort_session.get_providers()[0]} - classes: {_damage_ort_names}")
    except Exception as exc:
        logger.warning(f"[yolo] damage ORT session failed ({exc}) - falling back to PyTorch")
        _damage_ort_session = None


def get_damage_ort_session() -> Any:
    return _damage_ort_session


def get_damage_ort_names() -> list[str]:
    """Class names in the graph's own index order."""
    return _damage_ort_names


# -- DirectML ONNX session for the fire/smoke detector ------------------------
# The damage classifier labels a whole frame; it cannot say where the fire is.
# This detector boxes flame and smoke (trained on D-Fire, see
# scripts/training/prepare_aerial_datasets.py). ONNX only: there is no PyTorch fallback,
# because the CPU torch path would cost more than the rest of /detect combined.
FIRE_DETECT_ENABLED = os.getenv("FIRE_DETECT", "true").lower() == "true"
_fire_ort_session: Any = None
_fire_ort_names: list[str] = []
_fire_meta: dict = {}


def _load_fire_ort(onnx_path: str) -> None:
    global _fire_ort_session, _fire_ort_names, _fire_meta
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _fire_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        meta = _fire_ort_session.get_modelmeta().custom_metadata_map or {}
        names = ast.literal_eval(meta["names"]) if "names" in meta else {}
        _fire_ort_names = [names[i] for i in sorted(names)] if names else ["smoke", "fire"]
        _fire_meta = _load_meta(MODELS_DIR / "fire_meta.json")
        logger.info(f"[yolo] fire ONNX session ready - provider: "
                    f"{_fire_ort_session.get_providers()[0]} - classes: {_fire_ort_names}")
    except Exception as exc:
        logger.warning(f"[yolo] fire ORT session failed ({exc}) - fire detection off")
        _fire_ort_session = None


def get_fire_ort_session() -> Any:
    return _fire_ort_session


def get_fire_ort_names() -> list[str]:
    """Class names in the graph's own index order."""
    return _fire_ort_names


# -- DirectML ONNX session for the partly-buried-person detector ---------------
# The victim and pose models learned whole bodies; a hand showing out of rubble
# is not one. This detector boxes just the part that shows (trained on COCO
# body parts composited onto disaster scenes, see
# scripts/training/prepare_buried_dataset.py). ONNX only, like the fire model.
BURIED_DETECT_ENABLED = os.getenv("BURIED_DETECT", "true").lower() == "true"
_buried_ort_session: Any = None
_buried_meta: dict = {}


def _load_buried_ort(onnx_path: str) -> None:
    global _buried_ort_session, _buried_meta
    try:
        import onnxruntime as ort
        providers = (["DmlExecutionProvider", "CPUExecutionProvider"]
                     if _dml_available() else ["CPUExecutionProvider"])
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _buried_ort_session = ort.InferenceSession(onnx_path, sess_options=opts, providers=providers)
        _buried_meta = _load_meta(MODELS_DIR / "buried_meta.json")
        logger.info(f"[yolo] buried-person ONNX session ready - provider: "
                    f"{_buried_ort_session.get_providers()[0]}")
    except Exception as exc:
        logger.warning(f"[yolo] buried-person ORT session failed ({exc}) - partial-body detection off")
        _buried_ort_session = None


def get_buried_ort_session() -> Any:
    return _buried_ort_session


def _resolve_victim_weights() -> tuple[str, bool]:
    """Return (weights_path, is_custom). Prefers ONNX over PT for faster CPU inference."""
    onnx = MODELS_DIR / "victim_best.onnx"
    if onnx.exists():
        return str(onnx), True
    custom = os.getenv("VICTIM_MODEL_PATH", str(MODELS_DIR / "victim_best.pt"))
    if Path(custom).exists():
        return custom, True
    fallback = os.getenv("MODEL_PATH") or base_weight("yolov8n.pt")
    return fallback, False


def _resolve_damage_weights() -> tuple[str, bool]:
    custom = os.getenv("DAMAGE_MODEL_PATH", str(MODELS_DIR / "damage_best.pt"))
    if Path(custom).exists():
        return custom, True
    return base_weight("yolov8n-cls.pt"), False


def _init_model(state: ModelState, weights: str, is_custom: bool,
                meta_file: Path | None = None, task: str = "detect") -> None:
    meta = _load_meta(meta_file) if meta_file and meta_file.exists() else {}
    logger.info(f"[yolo] Loading {'custom' if is_custom else 'pretrained'} {task} model: {weights}")
    t0 = time.perf_counter()
    model, ok = _load_single(weights, task, imgsz=meta.get("imgsz"))
    elapsed = (time.perf_counter() - t0) * 1000

    state.model     = model
    state.weights   = weights
    state.is_custom = is_custom
    state.loaded_at = datetime.now(timezone.utc).isoformat()
    state.version   = "custom_v1" if is_custom else "pretrained_coco"

    if model is not None:
        logger.info(f"[yolo] {task} model ready in {elapsed:.0f}ms — {state.version}")
    else:
        logger.warning(f"[yolo] {task} model failed to load — stub mode")
        state.version = "stub"

    if meta:
        state.meta     = meta
        state.map50    = meta.get("map50", 0.0)
        state.accuracy = meta.get("accuracy_top1", 0.0)


# ── Public API ────────────────────────────────────────────────────────────────

COCO_ASSIST_ENABLED = os.getenv("COCO_ASSIST", "true").lower() == "true"
COCO_ASSIST_WEIGHTS = os.getenv("COCO_ASSIST_WEIGHTS") or base_weight("yolov8n.pt")

# Pose assist. Same person boxes as the COCO assist, plus the 17 COCO
# keypoints, which is what lets services/casualty.py tell a body lying on the
# ground from a person standing up. When it loads, it REPLACES the plain COCO
# assist pass rather than adding a third inference: yolov8n-pose detects the
# same class 0 people, so running both would cost latency to produce duplicate
# boxes for NMS to throw away.
POSE_ASSIST_ENABLED = os.getenv("POSE_ASSIST", "true").lower() == "true"
POSE_ASSIST_WEIGHTS = os.getenv("POSE_ASSIST_WEIGHTS") or base_weight("yolov8n-pose.pt")


def get_coco_assist() -> Any:
    """Generic COCO detector used to catch close-range bodies, or None."""
    return _coco_assist.model


def coco_assist_state() -> ModelState:
    return _coco_assist


def get_pose_assist() -> Any:
    """Pose detector used to read body posture, or None when unavailable."""
    return _pose_assist.model


def pose_assist_state() -> ModelState:
    return _pose_assist


def _gpu_graph(override: str | None, fast: Path, standard: Path) -> str | None:
    """
    Which ONNX file the DirectML session loads: an explicit override, else the
    fast export when present, else the standard one.

    The fast exports (rectangular 736x1280 / 544x960 input, FP16) cut a 4-feed
    detection round from ~1.7-2.1s to ~0.55-0.77s with the same detections on
    the demo clips. They exist only for this ORT path: the Ultralytics fallback
    feeds float32 and rejects an FP16 graph, so the standard files stay in
    place for it — overwriting them would have left the model "stub".
    """
    for candidate in (override, fast, standard):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def load_all() -> None:
    """Called once from FastAPI lifespan. Loads both models."""
    v_weights, v_custom = _resolve_victim_weights()
    _init_model(_victim, v_weights, v_custom,
                meta_file=MODELS_DIR / "victim_meta.json", task="detect")

    # Load GPU-accelerated ONNX session for victim model (DirectML)
    onnx_path = _gpu_graph(os.getenv("VICTIM_ORT_ONNX"), MODELS_DIR / "victim_fast.onnx",
                           MODELS_DIR / "victim_best.onnx")
    if onnx_path:
        _load_victim_ort(onnx_path)

    d_weights, d_custom = _resolve_damage_weights()
    _init_model(_damage, d_weights, d_custom,
                meta_file=MODELS_DIR / "damage_meta.json", task="classify")

    damage_onnx = MODELS_DIR / "damage_best.onnx"
    if damage_onnx.exists():
        _load_damage_ort(str(damage_onnx))

    fire_onnx = MODELS_DIR / "fire_best.onnx"
    if FIRE_DETECT_ENABLED and fire_onnx.exists():
        _load_fire_ort(str(fire_onnx))
    elif FIRE_DETECT_ENABLED:
        logger.info(f"[yolo] no {fire_onnx.name} - fire/smoke boxes off "
                    "(train with scripts/training/train_models.py --fire-only)")

    buried_onnx = MODELS_DIR / "buried_best.onnx"
    if BURIED_DETECT_ENABLED and buried_onnx.exists():
        _load_buried_ort(str(buried_onnx))
    elif BURIED_DETECT_ENABLED:
        logger.info(f"[yolo] no {buried_onnx.name} - partly buried people off "
                    "(train with scripts/training/train_buried.py)")

    if COCO_ASSIST_ENABLED:
        coco_onnx = Path(REPO_ROOT / os.environ["COCO_ASSIST_ONNX"] if os.getenv("COCO_ASSIST_ONNX") else base_weight("yolov8n.onnx"))
        if coco_onnx.exists():
            _load_coco_ort(str(coco_onnx))
            _coco_assist.weights = str(coco_onnx)
            _coco_assist.version = "pretrained_coco"
        if _coco_ort_session is None:
            # No ONNX export available — the PyTorch path still works, just slower.
            _init_model(_coco_assist, COCO_ASSIST_WEIGHTS, is_custom=False, task="coco-assist")

    if POSE_ASSIST_ENABLED:
        pose_path = _gpu_graph(
            str(REPO_ROOT / os.environ["POSE_ASSIST_ONNX"]) if os.getenv("POSE_ASSIST_ONNX") else None,
            Path(base_weight("yolov8n-pose-fast.onnx")), Path(base_weight("yolov8n-pose.onnx")))
        pose_onnx = Path(pose_path) if pose_path else Path(base_weight("yolov8n-pose.onnx"))
        if pose_path:
            _load_pose_ort(str(pose_onnx))
            _pose_assist.weights = str(pose_onnx)
            _pose_assist.version = "pretrained_pose"
        # Ultralytics fetches these weights on first use. That download can
        # fail on an air-gapped or offline machine, and it must not take the
        # server down with it: _init_model leaves the state in "stub" and
        # detect.py falls back to the plain COCO assist, with posture derived
        # from box aspect ratio instead of keypoints.
        if _pose_ort_session is None:
            _init_model(_pose_assist, POSE_ASSIST_WEIGHTS, is_custom=False, task="pose-assist")
        if _pose_assist.model is None and _pose_ort_session is None:
            logger.warning(
                "[yolo] pose assist unavailable — casualty posture will fall back "
                "to bounding-box aspect ratio, which is a much weaker signal"
            )


def get_victim_model() -> Any:
    return _victim.model


def get_damage_model() -> Any:
    return _damage.model


def victim_state() -> ModelState:
    return _victim


def damage_state() -> ModelState:
    return _damage


def reload_victim() -> dict:
    """Hot-swap victim model weights (no server restart needed)."""
    weights, is_custom = _resolve_victim_weights()
    _init_model(_victim, weights, is_custom,
                meta_file=MODELS_DIR / "victim_meta.json", task="detect")
    return model_status()


def reload_damage() -> dict:
    """Hot-swap damage model weights."""
    weights, is_custom = _resolve_damage_weights()
    _init_model(_damage, weights, is_custom,
                meta_file=MODELS_DIR / "damage_meta.json", task="classify")
    # /classify prefers the ONNX session over the model reloaded above, so a
    # reload that left the old session in place kept serving the old weights.
    damage_onnx = MODELS_DIR / "damage_best.onnx"
    if damage_onnx.exists():
        _load_damage_ort(str(damage_onnx))
    return model_status()


def model_status() -> dict:
    """Serialisable status dict — returned by GET /models/status."""
    def _state_dict(s: ModelState, kind: str) -> dict:
        d: dict = {
            "version":     s.version,
            "weights":     s.weights,
            "loaded":      s.model is not None,
            "is_custom":   s.is_custom,
            "loaded_at":   s.loaded_at,
        }
        if kind == "victim" and s.map50:
            d["map50"] = s.map50
        if kind == "damage" and s.accuracy:
            d["accuracy"] = s.accuracy
        return d

    return {
        "victim_model": _state_dict(_victim, "victim"),
        "damage_model": _state_dict(_damage, "damage"),
        "coco_assist": {
            "enabled":  COCO_ASSIST_ENABLED,
            "loaded":   _coco_assist.model is not None or _coco_ort_session is not None,
            "weights":  _coco_assist.weights,
            "runtime":  "onnx-directml" if _coco_ort_session is not None else
                        ("pytorch-cpu" if _coco_assist.model is not None else "none"),
        },
        "pose_assist": {
            "enabled":  POSE_ASSIST_ENABLED,
            "loaded":   _pose_assist.model is not None or _pose_ort_session is not None,
            "weights":  _pose_assist.weights,
            "runtime":  "onnx-directml" if _pose_ort_session is not None else
                        ("pytorch" if _pose_assist.model is not None else "none"),
        },
        "fire_model": {
            "enabled":  FIRE_DETECT_ENABLED,
            "loaded":   _fire_ort_session is not None,
            "classes":  _fire_ort_names,
            "map50":    _fire_meta.get("map50"),
        },
        "buried_model": {
            "enabled":  BURIED_DETECT_ENABLED,
            "loaded":   _buried_ort_session is not None,
            "map50":    _buried_meta.get("map50"),
        },
    }


def model_info() -> dict:
    """Legacy compat — used by /health."""
    return {
        "victim": {"loaded": _victim.model is not None, "version": _victim.version},
        "damage": {"loaded": _damage.model is not None, "version": _damage.version},
    }
