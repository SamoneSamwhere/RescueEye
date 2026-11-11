"""
How many lying people the live detection path finds, on real aerial frames it
was never trained on: the Okutama-Action test split (prepared by
prepare_casualty_dataset.py, labelled upright / down).

Reports recall for lying and upright people separately, plus precision, at
the live confidence threshold - the casualty gate can only judge people the
detector finds, so lying-person recall is the number this run exists to move.

    .venv/Scripts/python.exe scripts/training/eval_lying_person.py                # installed model
    .venv/Scripts/python.exe scripts/training/eval_lying_person.py --victim x.onnx
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.chdir(API)
logging.disable(logging.CRITICAL)

DATA = Path("C:/RescueEyeData/casualty")
IOU_MATCH = 0.3


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--victim", help="ONNX victim model to evaluate instead of the installed one")
    ap.add_argument("--limit", type=int, default=0, help="first N frames only (quick check)")
    args = ap.parse_args()

    from services import yolo_model
    yolo_model.load_all()
    if args.victim:
        import onnxruntime as ort
        yolo_model._victim_ort_session = ort.InferenceSession(
            args.victim, providers=["DmlExecutionProvider", "CPUExecutionProvider"])
    from routers import detect
    conf = detect.CONFIDENCE_THRESHOLD

    frames = sorted((DATA / "images/test").glob("ok_*"))
    if args.limit:
        frames = frames[: args.limit]
    found = {"0": 0, "1": 0}
    total = {"0": 0, "1": 0}
    tp = fp = 0
    for f in frames:
        frame = detect._decode_jpeg(f.read_bytes())
        h, w = frame.shape[:2]
        gt = []
        for line in (DATA / "labels/test" / f"{f.stem}.txt").read_text().splitlines():
            p = line.split()
            if len(p) == 5 and p[0] in found:
                cx, cy, bw, bh = (float(v) for v in p[1:])
                gt.append((p[0], [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]))
                total[p[0]] += 1
        dets, _, _ = detect._run_victim(frame)
        used: set[int] = set()
        for d in sorted((d for d in dets if d["confidence"] >= conf), key=lambda d: -d["confidence"]):
            b = d["bbox"]
            box = [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]]
            best, bi = 0.0, -1
            for i, (_, g) in enumerate(gt):
                if i not in used and (v := iou(box, g)) > best:
                    best, bi = v, i
            if best >= IOU_MATCH:
                used.add(bi)
                found[gt[bi][0]] += 1
                tp += 1
            else:
                fp += 1

    name = Path(args.victim).name if args.victim else "installed"
    print(
        f"RESULT {name}: {len(frames)} frames | lying people found {found['1']}/{total['1']} "
        f"({found['1'] / max(total['1'], 1):.1%}) | upright found {found['0']}/{total['0']} "
        f"({found['0'] / max(total['0'], 1):.1%}) | precision {tp / max(tp + fp, 1):.1%} at conf {conf}"
    )


if __name__ == "__main__":
    main()
