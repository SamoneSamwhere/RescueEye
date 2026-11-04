"""
Trains the casualty detector: upright / down / partial for every person
(data from prepare_casualty_dataset.py).

yolov8s from COCO: it already knows people, and the step up from the n model
is for the "down" class, which turns on small cues (body length against the
ground, shadow) in people a few dozen pixels tall.

Trained at 960, which is what a 1280x720 stream frame becomes when letterboxed
to 960: people are the same size in training and live. Exported at 544x960.

Run in the GPU training venv, in a visible terminal:
    .venv-train/Scripts/python.exe scripts/training/train_casualty.py

Outputs land in runs/candidates/ (never over a live model):
    casualty.pt, casualty_544x960_fp16.onnx, casualty_meta.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

API = Path(__file__).resolve().parents[2]
DATA = Path("C:/RescueEyeData/casualty/casualty.yaml")
RUNS = API / "runs/casualty"
OUT = API / "runs/candidates"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="yolov8s.pt")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--imgsz", type=int, default=960)
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
            patience=12,
            cos_lr=True,
            # Flips only, never rotation: a standing person turned 90 degrees
            # looks exactly like a lying one, and would be labelled upright.
            flipud=0.0,
            fliplr=0.5,
            degrees=0.0,
            mosaic=1.0,
            close_mosaic=8,
            scale=0.4,
            project=str(RUNS),
            name="train",
            exist_ok=True,
            plots=True,
        )
        print(f"Training took {(time.time() - t0) / 3600:.1f} h")

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "casualty.pt"
    shutil.copy2(RUNS / "train/weights/best.pt", dst)
    rd = getattr(results, "results_dict", {}) or {}
    meta = {
        "map50": round(float(rd.get("metrics/mAP50(B)", 0)), 4),
        "map50_95": round(float(rd.get("metrics/mAP50-95(B)", 0)), 4),
        "precision": round(float(rd.get("metrics/precision(B)", 0)), 4),
        "recall": round(float(rd.get("metrics/recall(B)", 0)), 4),
        "base": Path(args.base).name,
        "dataset": "Okutama-Action (Lying -> down) + VisDrone + partly buried composites and SeaDronesSee swimmers",
        "classes": ["upright", "down", "partial"],
        "imgsz": args.imgsz,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / "casualty_meta.json").write_text(json.dumps(meta, indent=2))
    print("Validation:", meta)

    tmp = OUT / "casualty_export.pt"
    shutil.copy2(dst, tmp)
    f = YOLO(str(tmp)).export(format="onnx", imgsz=[544, 960], opset=12, half=True, device=0, simplify=False)
    shutil.move(f, OUT / "casualty_544x960_fp16.onnx")
    tmp.unlink(missing_ok=True)
    print("Exported", OUT / "casualty_544x960_fp16.onnx")


if __name__ == "__main__":
    main()
