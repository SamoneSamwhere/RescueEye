"""
Fine-tune the victim (person) detector for small subjects seen from altitude.

Starts from the installed models/victim_best.pt — so everything it already
detects is kept — and continues training on data/small_person.yaml
(scripts/training/prepare_small_person_dataset.py): VisDrone pedestrians and
non-upright people, HERIDAL wilderness SAR, and SeaDronesSee swimmers.

Run in the GPU training venv, in a visible terminal to watch progress:

    .venv-train/Scripts/python.exe scripts/training/train_small_person.py

Outputs land in runs/candidates/ (never over the live model):
    victim_small.pt                      best weights
    victim_small_736x1280_fp16.onnx      the live fast-path format (victim_fast.onnx)
    victim_small_1280_fp32.onnx          the standard format (victim_best.onnx)
Compare against the installed model before switching:
    .venv/Scripts/python.exe scripts/training/eval_small_person.py --victim runs/candidates/victim_small_736x1280_fp16.onnx
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

API = Path(__file__).resolve().parents[2]   # scripts/training/ -> api/
BASE = API / "models/victim_best.pt"
DATA = API / "data/small_person.yaml"
RUNS = API / "runs/victim_small"
OUT = API / "runs/candidates"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    # Batch 4 @1280 reached 8.65 GB on the 6 GB RTX 4050: Windows spilled into
    # shared system memory, each step went from ~0.3 s to 3.3 s, and the run
    # diverged to NaN losses in epoch 2 (2026-10-28). Batch 2 fits; Ultralytics
    # accumulates gradients to its nominal batch of 64 either way.
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--lr0", type=float, default=0.0002)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", action="store_true", help="continue an interrupted run from last.pt")
    args = ap.parse_args()

    from ultralytics import YOLO

    if args.resume:
        model = YOLO(str(RUNS / "train/weights/last.pt"))
        results = model.train(resume=True)
    else:
        print(f"Fine-tuning {BASE.name} on {DATA.name} — {args.epochs} epochs @ {args.imgsz}px, batch {args.batch}")
        model = YOLO(str(BASE))
        t0 = time.time()
        results = model.train(
            data=str(DATA),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            device=0,
            patience=8,
            # Fine-tuning: a gentle learning rate keeps what the weights already
            # know about VisDrone pedestrians while they learn new poses.
            optimizer="AdamW",
            lr0=args.lr0,
            cos_lr=True,
            warmup_epochs=1,
            # A drone looks down from any heading, so vertical flips are real views.
            flipud=0.5,
            fliplr=0.5,
            mosaic=1.0,
            close_mosaic=5,
            # Shrinking is on (scale) but bounded: subjects are already tiny,
            # and a 0.9 scale range would push many below what can be learned.
            scale=0.4,
            project=str(RUNS),
            name="train",
            exist_ok=True,
            plots=True,
        )
        print(f"Training took {(time.time() - t0) / 3600:.1f} h")

    best = RUNS / "train/weights/best.pt"
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "victim_small.pt"
    shutil.copy2(best, dst)

    rd = getattr(results, "results_dict", {}) or {}
    meta = {
        "map50": round(float(rd.get("metrics/mAP50(B)", 0)), 4),
        "map50_95": round(float(rd.get("metrics/mAP50-95(B)", 0)), 4),
        "precision": round(float(rd.get("metrics/precision(B)", 0)), 4),
        "recall": round(float(rd.get("metrics/recall(B)", 0)), 4),
        "base": BASE.name,
        "dataset": "VisDrone (pedestrian+people) + HERIDAL + SeaDronesSee swimmers, tiled to 1280",
        "imgsz": args.imgsz,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / "victim_small_meta.json").write_text(json.dumps(meta, indent=2))
    print("Validation:", meta)

    for hw, half, name in (((736, 1280), True, "victim_small_736x1280_fp16.onnx"),
                           ((1280, 1280), False, "victim_small_1280_fp32.onnx")):
        tmp = OUT / "victim_small_export.pt"
        shutil.copy2(dst, tmp)
        f = YOLO(str(tmp)).export(format="onnx", imgsz=list(hw), opset=12, half=half,
                                  device=0 if half else "cpu", simplify=False)
        shutil.move(f, OUT / name)
        tmp.unlink(missing_ok=True)
        print("Exported", OUT / name)

    print("\nDone. Compare with the installed model:\n"
          "  .venv/Scripts/python.exe scripts/training/eval_small_person.py --victim "
          "runs/candidates/victim_small_736x1280_fp16.onnx")


if __name__ == "__main__":
    main()
