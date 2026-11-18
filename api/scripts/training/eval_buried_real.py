"""
Scores buried-person weights on the 17 Nov 2026 staged footage.

    .venv-train/Scripts/python.exe scripts/training/eval_buried_real.py --labels DIR --models a.pt b.pt [--scenes trunk sheet]

Found:  share of labelled frames of a scene where a box at >= CONF overlaps
        the hidden person (IoU >= 0.2, or the box centre inside the label).
        Run it on a scene the weights were NOT trained on for an honest number.
False:  boxes at >= CONF per frame on footage with nobody hidden in it -
        the OpenCV pedestrian clip and the team's walking/yard clips. Some of
        these frames show whole people; the API drops a part box that sits
        inside a body box, so "false" here is an upper bound.
Frames are run whole at 1280 wide, as the API does.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

FOOTAGE = Path("D:/RE RescueEye/footage-2026-11-17")
SCENES = {
    "trunk": [("trunk_0105.json", "dji_fly_20261117_144232_0105.mp4", (40.5, 57.5))],
    "sheet": [("sheet_0102_early.json", "dji_fly_20261117_142134_0102.mp4", (6.5, 10.0)),
              ("sheet_0102.json", "dji_fly_20261117_142134_0102.mp4", (17.0, 37.5))],
}
NEGATIVE = [("C:/RescueEyeData/evalclips/vtest.avi", 0, 60, 1.0),
            (str(FOOTAGE / "dji_fly_20261117_142422_0103.mp4"), 0, 41, 1.0),   # people walking in the yard
            (str(FOOTAGE / "dji_fly_20261117_141022_0028.mp4"), 0, 21, 1.0),   # two walkers + one on the pipes
            (str(FOOTAGE / "dji_fly_20261117_135916_0026.mp4"), 0, 33, 1.0)]   # forest road, one lying on sand


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def grab(clip: str, t: float, cache: dict):
    cap = cache.setdefault(clip, cv2.VideoCapture(clip))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * cap.get(cv2.CAP_PROP_FPS))))
    ok, f = cap.read()
    return f if ok else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--scenes", nargs="+", default=list(SCENES))
    ap.add_argument("--conf", type=float, nargs="+", default=[0.5, 0.3])
    ap.add_argument("--step", type=float, default=0.5, help="seconds between scored frames of a scene")
    args = ap.parse_args()

    from ultralytics import YOLO
    cache: dict = {}
    lo = min(args.conf)

    for weights in args.models:
        model = YOLO(weights)

        def boxes(f):
            r = model.predict(f, imgsz=1280, conf=lo, verbose=False, device=0)[0]
            return [(float(c), b) for c, b in zip(r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]

        print(f"\n== {weights}")
        for scene in args.scenes:
            hits = {c: 0 for c in args.conf}
            n = 0
            best = []
            for label_file, clip, (a, b) in SCENES[scene]:
                gt_all = json.loads((Path(args.labels) / label_file).read_text())["boxes"]
                last = -1e9
                for t_s, gt in gt_all.items():
                    t = float(t_s)
                    if not (a <= t <= b) or t - last < args.step - 1e-6:
                        continue
                    last = t
                    f = grab(str(FOOTAGE / clip), t, cache)
                    if f is None:
                        continue
                    n += 1
                    found = [c for c, bb in boxes(f)
                             if iou(bb, gt) >= 0.2 or (gt[0] <= (bb[0] + bb[2]) / 2 <= gt[2] and gt[1] <= (bb[1] + bb[3]) / 2 <= gt[3])]
                    top = max(found, default=0.0)
                    best.append(top)
                    for c in args.conf:
                        hits[c] += top >= c
            med = sorted(best)[len(best) // 2] if best else 0
            print(f"  {scene:6s} found  " + "  ".join(f"@{c}: {hits[c]}/{n} ({hits[c] / max(n, 1):.0%})" for c in args.conf)
                  + f"   median score on the person {med:.2f}")

        for clip, t0, t1, step in NEGATIVE:
            cnt = {c: 0 for c in args.conf}
            n = 0
            t = t0
            while t < t1:
                f = grab(clip, t, cache)
                t += step
                if f is None:
                    continue
                n += 1
                for c, _ in boxes(f):
                    for k in args.conf:
                        cnt[k] += c >= k
            print(f"  false  {Path(clip).name[:34]:34s} " + "  ".join(f"@{c}: {cnt[c] / max(n, 1):.2f}/frame" for c in args.conf))


if __name__ == "__main__":
    main()
