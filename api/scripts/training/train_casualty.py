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

Second version (extra data from prepare_casualty_v2.py), fine-tuned from the first:
    .venv-train/Scripts/python.exe scripts/training/train_casualty.py --base runs/candidates/casualty.pt
        --data C:/RescueEyeData/casualty_v2.yaml --tag casualty_v2 --epochs 15 --lr0 0.003
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
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--tag", default="casualty", help="run and output file name")
    ap.add_argument("--lr0", type=float, default=None, help="SGD start rate; set when fine-tuning")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    from ultralytics import YOLO

    run = RUNS / ("train" if args.tag == "casualty" else args.tag)
    tune = {"optimizer": "SGD", "lr0": args.lr0, "warmup_epochs": 1} if args.lr0 else {}
    if args.resume:
        results = YOLO(str(run / "weights/last.pt")).train(resume=True)
    else:
        t0 = time.time()
        results = YOLO(args.base).train(
            data=str(args.data),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            device=0,
            patience=12 if not args.lr0 else 6,
            cos_lr=True,
            # Flips only, never rotation: a standing person turned 90 degrees
            # looks exactly like a lying one, and would be labelled upright.
            flipud=0.0,
            fliplr=0.5,
            degrees=0.0,
            mosaic=1.0,
            close_mosaic=8 if not args.lr0 else 4,
            scale=0.4,
            project=str(RUNS),
            name=run.name,
            exist_ok=True,
            plots=True,
            **tune,
        )
        print(f"Training took {(time.time() - t0) / 3600:.1f} h")

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"{args.tag}.pt"
    shutil.copy2(run / "weights/best.pt", dst)
    rd = getattr(results, "results_dict", {}) or {}
    meta = {
        "map50": round(float(rd.get("metrics/mAP50(B)", 0)), 4),
        "map50_95": round(float(rd.get("metrics/mAP50-95(B)", 0)), 4),
        "precision": round(float(rd.get("metrics/precision(B)", 0)), 4),
        "recall": round(float(rd.get("metrics/recall(B)", 0)), 4),
        "base": Path(args.base).name,
        "dataset": "Okutama-Action (Lying -> down) + VisDrone + partly buried composites and SeaDronesSee swimmers"
                   + (" + turned Okutama casualties and overhead whole-body composites" if args.data != DATA else ""),
        "classes": ["upright", "down", "partial"],
        "imgsz": args.imgsz,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / f"{args.tag}_meta.json").write_text(json.dumps(meta, indent=2))
    print("Validation:", meta)

    tmp = OUT / f"{args.tag}_export.pt"
    shutil.copy2(dst, tmp)
    f = YOLO(str(tmp)).export(format="onnx", imgsz=[544, 960], opset=12, half=True, device=0, simplify=False)
    shutil.move(f, OUT / f"{args.tag}_544x960_fp16.onnx")
    tmp.unlink(missing_ok=True)
    print("Exported", OUT / f"{args.tag}_544x960_fp16.onnx")


if __name__ == "__main__":
    main()
