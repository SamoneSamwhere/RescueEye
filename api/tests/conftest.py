"""
Shared pytest fixtures for the api/ test suite.

These env vars MUST be set before routers.detect is first imported by any
test module, since it reads them at import time to decide the confidence
thresholds for firing background tasks (incident creation + ntfy alert).
Setting them here (module scope, executed on conftest collection, which
always happens before test collection) neutralizes both so tests never
make real outbound network calls to ntfy.sh or a live Node server.
"""
import os

os.environ.setdefault("NTFY_MIN_CONF", "2.0")
os.environ.setdefault("INCIDENT_CONF_MIN", "2.0")

import base64
import io

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from routers import detect, classify, detections, models as models_router, logs as logs_router
from services import detection_store


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(detect.router, prefix="/detect")
    app.include_router(classify.router, prefix="/classify")
    app.include_router(detections.router, prefix="/detections")
    app.include_router(models_router.router, prefix="/models")
    app.include_router(logs_router.router, prefix="/logs")
    return app


def _jpeg_b64(rgb: tuple[int, int, int], size=(640, 480)) -> str:
    img = Image.new("RGB", size, rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def bright_frame_b64() -> str:
    return _jpeg_b64((200, 200, 200))


@pytest.fixture()
def dark_frame_b64() -> str:
    return _jpeg_b64((5, 5, 5))


@pytest.fixture()
def prone_victim(monkeypatch):
    """
    Makes /detect return one body lying down, with the pose keypoints to prove
    it — the evidence the casualty gate requires.

    The stub path inside _run_victim cannot stand in for this any more: without
    keypoints or a stillness window, box shape alone is not allowed to claim a
    casualty (a wide box is just as likely to be two people or a vehicle). Tests
    about endpoint mechanics still need something that actually gets emitted.
    """
    from routers import detect

    bbox = {"x": 80, "y": 180, "w": 220, "h": 90}
    kps = np.zeros((17, 3), dtype=np.float32)
    # Torso across the box, both joints well inside it. Left and right
    # shoulders are distinct points: the overhead posture measurement divides
    # by shoulder width, and coincident shoulders give it nothing to divide by.
    kps[5] = (130.0, 210.0, 0.95)   # left shoulder
    kps[6] = (150.0, 234.0, 0.95)   # right shoulder
    for idx in (11, 12):
        kps[idx] = (250.0, 228.0, 0.95)
    pose = {"class": "person", "confidence": 0.9, "bbox": bbox, "keypoints": kps}

    monkeypatch.setattr(
        detect, "_run_victim",
        lambda frame: ([{"class": "person", "confidence": 0.9, "bbox": bbox}], 5.0, [pose]),
    )
    # A body already seen lying still on an earlier pass: these tests are about
    # endpoint mechanics, and the second-sighting rule is pinned in
    # test_casualty_gate.py.
    from services import casualty
    monkeypatch.setattr(casualty.StillnessMonitor, "recent_motion", lambda self, track_id: 0.0)
    return bbox


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(logs_router, "LOG_FILE", tmp_path / "inference_log.jsonl")
    detection_store._store.clear()
    detect._tracker.reset()
    yield TestClient(_build_test_app())
    detection_store._store.clear()
    detect._tracker.reset()
