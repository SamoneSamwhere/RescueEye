"""
Train the lying / not_lying posture classifier on data/posture
(scripts/training/prepare_posture_dataset.py).

YOLOv8n-cls at 96 px: the crops are small people, and the gate runs this once
per person per frame, so it has to be tiny. YOLOv8 rather than YOLO11 because
the API's ultralytics (8.2.56) cannot load YOLO11 checkpoints.

    .venv-train/Scripts/python.exe scripts/training/train_posture.py

Writes runs/candidates/posture/{posture.pt, posture.onnx, metrics.json};
nothing goes live until it is copied to models/ by hand.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ultralytics import YOLO

API = Path(__file__).resolve().parents[2]
DATA = API / "data/posture"
RUNS = API / "runs/posture"
OUT = API / "runs/candidates/posture"
IMGSZ = 96


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(API / "models/base/yolov8n-cls.pt"),
                    help="starting weights, e.g. yolov8s-cls.pt (downloaded on first use)")
    model = YOLO(ap.parse_args().base)
    # No vertical flips: a person upside down is not a pose the camera produces
    # often, and lying is about orientation. Rotations stay small for the same
    # reason - a 90 degree turn would turn a standing person into a lying one.
    model.train(data=str(DATA), epochs=20, imgsz=IMGSZ, batch=128, patience=6, optimizer="AdamW", lr0=0.0005, dropout=0.2,
                fliplr=0.5, flipud=0.0, degrees=10, hsv_h=0.015, hsv_s=0.5, hsv_v=0.4, erasing=0.2,
                project=str(RUNS), name="train", exist_ok=True, device=0, workers=2)

    best = RUNS / "train/weights/best.pt"
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(best, OUT / "posture.pt")
    trained = YOLO(str(OUT / "posture.pt"))
    r = trained.val(data=str(DATA), split="test", imgsz=IMGSZ, batch=128, device=0, plots=False,
                    project=str(RUNS), name="test", exist_ok=True)
    onnx = trained.export(format="onnx", imgsz=IMGSZ, opset=17, simplify=True, dynamic=True)
    shutil.move(onnx, OUT / "posture.onnx")
    metrics = {"test_top1": round(float(r.top1), 4), "imgsz": IMGSZ, "names": trained.names,
               "dataset": "Okutama-Action (Lying vs every other action) + VisDrone pedestrians"}
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("POSTURE TEST:", json.dumps(metrics))


if __name__ == "__main__":
    main()
