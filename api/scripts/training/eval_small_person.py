"""
Small-subject person detection benchmark on the UAV-SAR test set.

Runs the live detection path (routers/detect.py:_run_victim — victim model plus
the pose/COCO assist, merged) over drone frames where people are ~30-40px, and
reports AP50 and recall/precision at the live confidence threshold. Use it to
compare victim models before switching one in.

    python scripts/training/eval_small_person.py                      # current models
    python scripts/training/eval_small_person.py --victim path.onnx   # a candidate

Dataset: https://zenodo.org/records/3924925 (gvessio, "for testing and
evaluation purposes only") — extracted under data/raw/downloads/uav_sar/.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np

API = Path(__file__).resolve().parents[2]   # scripts/training/ -> api/
sys.path.insert(0, str(API))
os.chdir(API)
logging.disable(logging.CRITICAL)

DATA = API / "data/raw/downloads/uav_sar/gvessio-uav-search-and-rescue-8961f73/dataset"
IOU_MATCH = 0.3   # tiny boxes: a few pixels of offset already costs a lot of IoU


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def load_gt(txt: Path, w: int, h: int) -> list[list[float]]:
    boxes = []
    for line in txt.read_text().splitlines():
        p = line.split()
        if len(p) >= 5:
            cx, cy, bw, bh = (float(v) for v in p[1:5])
            boxes.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
    return boxes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--victim", help="ONNX victim model to evaluate instead of the installed one")
    ap.add_argument("--no-assist", action="store_true", help="victim model alone, without the pose/COCO assist")
    ap.add_argument("--sweep", action="store_true", help="also print recall/precision at other cutoffs")
    args = ap.parse_args()

    from services import yolo_model
    yolo_model.load_all()
    if args.victim:
        import onnxruntime as ort
        yolo_model._victim_ort_session = ort.InferenceSession(
            args.victim, providers=["DmlExecutionProvider", "CPUExecutionProvider"])
    from routers import detect
    live_conf = detect.CONFIDENCE_THRESHOLD
    detect.CONFIDENCE_THRESHOLD = 0.05        # collect low scores too, for the PR curve
    detect.COCO_ASSIST_CONF = detect.POSE_ASSIST_CONF = 0.05

    frames = sorted(DATA.glob("*/frames/*.jpg"))
    preds: list[tuple[float, bool]] = []      # (score, is_true_positive)
    n_gt = 0
    for f in frames:
        frame = detect._decode_jpeg(f.read_bytes())
        h, w = frame.shape[:2]
        gt = load_gt(f.parent.parent / "annotations" / f"{f.stem}.txt", w, h)
        n_gt += len(gt)
        if args.no_assist:
            dets, _ = detect._run_victim_primary(frame)
        else:
            dets, _, _ = detect._run_victim(frame)
        used: set[int] = set()
        for d in sorted(dets, key=lambda d: -d["confidence"]):
            b = d["bbox"]; box = [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]]
            best, bi = 0.0, -1
            for i, g in enumerate(gt):
                if i not in used and (v := iou(box, g)) > best:
                    best, bi = v, i
            hit = best >= IOU_MATCH
            if hit:
                used.add(bi)
            preds.append((d["confidence"], hit))

    preds.sort(key=lambda p: -p[0])
    tp = np.cumsum([p[1] for p in preds]); fp = np.cumsum([not p[1] for p in preds])
    recall = tp / max(n_gt, 1); precision = tp / np.maximum(tp + fp, 1)
    # All-point interpolated AP.
    mrec = np.concatenate([[0], recall, [1]]); mpre = np.concatenate([[1], precision, [0]])
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    ap_val = float(np.sum((mrec[1:] - mrec[:-1]) * mpre[1:]))
    at = [p for p in preds if p[0] >= live_conf]
    r_live = sum(p[1] for p in at) / max(n_gt, 1)
    p_live = sum(p[1] for p in at) / max(len(at), 1)
    name = Path(args.victim).name if args.victim else "installed"
    print(f"RESULT {name}{' (no assist)' if args.no_assist else ''}: {len(frames)} frames, {n_gt} people | "
          f"AP@IoU{IOU_MATCH} {ap_val:.3f} | at live conf {live_conf}: recall {r_live:.3f}, precision {p_live:.3f}")
    if args.sweep:
        for c in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
            at = [p for p in preds if p[0] >= c]
            print(f"  conf {c:.2f}: recall {sum(p[1] for p in at) / max(n_gt, 1):.3f}, "
                  f"precision {sum(p[1] for p in at) / max(len(at), 1):.3f}")


if __name__ == "__main__":
    main()
