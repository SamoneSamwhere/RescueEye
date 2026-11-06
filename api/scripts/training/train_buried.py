"""
Trains the partly-buried-person detector: a hand, arm, head or leg showing out
of rubble or water (data from prepare_buried_dataset.py).

A separate model from the victim detector on purpose. That one is tuned for
whole bodies at altitude and was just measured on UAV-SAR; retraining it on
composited body parts would put that at risk. This one starts from COCO
yolov8n, which already knows what people look like up close.

Run in the GPU training venv, in a visible terminal:
    .venv-train/Scripts/python.exe scripts/training/train_buried.py

Outputs land in runs/candidates/ (never over a live model):
    buried.pt, buried_736x1280_fp16.onnx, buried_meta.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

API = Path(__file__).resolve().parents[2]
BASE = API / "models/base/yolov8n.pt"
DATA = Path("C:/RescueEyeData/buried/dataset/buried.yaml")
RUNS = API / "runs/buried"
OUT = API / "runs/candidates"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--base", default=str(BASE), help="weights to start from (default: COCO yolov8n)")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    # ~3 GB of RAM is free on this laptop; more workers crashed a run silently.
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    from ultralytics import YOLO

    if args.resume:
        results = YOLO(str(RUNS / "train/weights/last.pt")).train(resume=True)
    else:
        t0 = time.time()
        results = YOLO(args.base).train(
            data=str(DATA),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            device=0,
            patience=15,
            cos_lr=True,
            # Seen from above at any heading; the composites are already rotated.
            flipud=0.5,
            fliplr=0.5,
            mosaic=1.0,
            close_mosaic=10,
            scale=0.5,
            project=str(RUNS),
            name="train",
            exist_ok=True,
            plots=True,
        )
        print(f"Training took {(time.time() - t0) / 3600:.1f} h")

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "buried.pt"
    shutil.copy2(RUNS / "train/weights/best.pt", dst)
    rd = getattr(results, "results_dict", {}) or {}
    meta = {
        "map50": round(float(rd.get("metrics/mAP50(B)", 0)), 4),
        "map50_95": round(float(rd.get("metrics/mAP50-95(B)", 0)), 4),
        "precision": round(float(rd.get("metrics/precision(B)", 0)), 4),
        "recall": round(float(rd.get("metrics/recall(B)", 0)), 4),
        "base": Path(args.base).name,
        "dataset": "COCO 2017 body parts composited onto AIDER collapse/fire/flood scenes, with unlabelled COCO object decoys, VisDrone/D-Fire negatives and SeaDronesSee swimmers",
        "classes": ["buried_person"],
        "imgsz": args.imgsz,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / "buried_meta.json").write_text(json.dumps(meta, indent=2))
    print("Validation:", meta)

    tmp = OUT / "buried_export.pt"
    shutil.copy2(dst, tmp)
    f = YOLO(str(tmp)).export(format="onnx", imgsz=[736, 1280], opset=12, half=True, device=0, simplify=False)
    shutil.move(f, OUT / "buried_736x1280_fp16.onnx")
    tmp.unlink(missing_ok=True)
    print("Exported", OUT / "buried_736x1280_fp16.onnx")


if __name__ == "__main__":
    main()
