"""
Checks a victim-detector candidate against the installed one on the 17 Nov
2026 staged footage (see prepare_hard_negatives.py).

    .venv-train/Scripts/python.exe scripts/training/eval_hard_negatives.py models/victim_best.pt runs/candidates/victim_hardneg.pt

False:  boxes per frame on the part of clip 0104 NOT used for training
        (poles, pipes and bags, nobody in it), and boxes on the striped pole
        in clip 0103, which no training frame came from.
People: on clips with people in them, the share of the FIRST model's sure
        boxes (>= 0.5) that each model also finds at the live cutoff (0.25).
        A proxy, not ground truth: run eval_small_person.py and
        eval_lying_person.py for the real recall numbers.
"""
from __future__ import annotations

import sys

import cv2

F = "D:/RE RescueEye/footage-2026-11-17/dji_fly_20261117_"
HELD_NEG = (F + "142802_0104.mp4", 18.0, 36.0, 0.5)
POLE = (F + "142422_0103.mp4", 39.0, 41.5, 0.25, (1150, 440, 1280, 640))   # x0,y0,x1,y1 at 1280 wide
PEOPLE = [(F + "142422_0103.mp4", 0, 41, 1.0), (F + "144232_0105.mp4", 0, 24, 1.0),
          (F + "141022_0028.mp4", 0, 21, 1.0), (F + "135916_0026.mp4", 0, 33, 1.0)]
LIVE_CONF = 0.25


def frames(clip, a, b, step):
    cap = cv2.VideoCapture(clip)
    fps = cap.get(cv2.CAP_PROP_FPS)
    t = a
    while t <= b:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, f = cap.read()
        if ok:
            yield t, cv2.resize(f, (1280, round(f.shape[0] * 1280 / f.shape[1])), interpolation=cv2.INTER_AREA)
        t += step


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix + 1e-9)


def main() -> None:
    from ultralytics import YOLO
    models = {p: YOLO(p) for p in sys.argv[1:]}

    def boxes(m, f, conf=LIVE_CONF):
        r = m.predict(f, imgsz=1280, conf=conf, verbose=False, device=0)[0]
        return [(c, b) for c, b in zip(r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]

    for name, m in models.items():
        n = c25 = c50 = 0
        for _, f in frames(*HELD_NEG):
            bs = boxes(m, f)
            n += 1
            c25 += len(bs)
            c50 += sum(c >= 0.5 for c, _ in bs)
        clip, a, b, step, (x0, y0, x1, y1) = POLE
        pole = sum(any(x0 <= (bb[0] + bb[2]) / 2 <= x1 and y0 <= (bb[1] + bb[3]) / 2 <= y1 for _, bb in boxes(m, f))
                   for _, f in frames(clip, a, b, step))
        print(f"{name}\n  held-out 0104 (nobody): {c25 / n:.2f} boxes/frame @0.25, {c50 / n:.2f} @0.5"
              f"\n  striped pole in 0103: boxed in {pole}/{int((b - a) / step) + 1} frames")

    ref = next(iter(models.values()))
    found = {k: 0 for k in models}
    total = 0
    for clip, a, b, step in PEOPLE:
        for _, f in frames(clip, a, b, step):
            sure = [bb for c, bb in boxes(ref, f, 0.5)]
            if not sure:
                continue
            total += len(sure)
            for k, m in models.items():
                got = [bb for _, bb in boxes(m, f)]
                found[k] += sum(any(iou(s, g) >= 0.3 for g in got) for s in sure)
    for k in models:
        print(f"  people (first model's sure boxes, {total}): {k} finds {found[k]} ({found[k] / max(total, 1):.0%})")


if __name__ == "__main__":
    main()
