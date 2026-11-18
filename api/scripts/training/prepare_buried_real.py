"""
Adds REAL partly-hidden people to the buried-person training data (v4).

v3 was trained on body parts pasted onto disaster photos. On the team's staged
shoot of 17 Nov 2026 it scored 0.00-0.41 on a person pinned under a fallen
trunk (only the head and a shoulder showing) and on a person under a metal
sheet (only legs, shoes and a hand) - it had never seen a real one.

Labels are one box around the visible part of each hidden person, drawn by
hand on one frame per scene and carried to the neighbouring frames along the
camera's motion (background features matched frame to frame; the scene and
the person are still, only the drone moves). Every carried box was checked by
eye; only the time spans where they fit are listed in SCENES.

Each labelled frame becomes several images: the whole frame, and random
crops around the person at two zoom levels, so the model sees them at the
sizes the 1280-wide detector input gives at different heights.
Frames from a clip with nobody in it are added as negatives, so the trunk,
branches and metal sheets themselves do not become "a person".

Writes C:/RescueEyeData/buried_real/{images,labels}/{scene}/ and the list
files the training runs use:
  cv_trunk.yaml  - train on everything except the trunk scene, validate on it
  cv_sheet.yaml  - the same for the metal-sheet scene
  final.yaml     - train on everything
Each mixes in a fixed random 5000 of the v3 composites so the model keeps
what it learnt there.

    .venv/Scripts/python.exe scripts/training/prepare_buried_real.py --labels DIR
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2

FOOTAGE = Path("D:/RE RescueEye/footage-2026-11-17")
OUT = Path("C:/RescueEyeData/buried_real")
OLD = Path("C:/RescueEyeData/buried/dataset")

# scene -> (label file, clip, [(t_from, t_to), ...] where the carried boxes fit)
SCENES = {
    "trunk": ("trunk_0105.json", "dji_fly_20261117_144232_0105.mp4", [(40.5, 57.5)]),
    "sheet": [("sheet_0102_early.json", "dji_fly_20261117_142134_0102.mp4", [(6.5, 10.0)]),
              ("sheet_0102.json", "dji_fly_20261117_142134_0102.mp4", [(17.0, 37.5)])],
}
NEGATIVE_CLIPS = ["dji_fly_20261117_140514_0027.mp4"]     # pipes and trees, nobody in it
OLD_SUBSET = 5000
MAX_SIDE = 1280


def write(img, boxes, stem: str, scene: str) -> Path:
    h, w = img.shape[:2]
    s = MAX_SIDE / max(h, w)
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ip = OUT / "images" / scene / f"{stem}.jpg"
    lp = OUT / "labels" / scene / f"{stem}.txt"
    ip.parent.mkdir(parents=True, exist_ok=True)
    lp.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ip), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    lp.write_text("".join(
        f"0 {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}\n"
        for x0, y0, x1, y1 in boxes))
    return ip


def crop_around(frame, box, frac: float, rng: random.Random):
    """A crop `frac` of the frame's size that contains the whole box, placed at random."""
    H, W = frame.shape[:2]
    cw, ch = int(W * frac), int(H * frac)
    x0, y0, x1, y1 = box
    cw, ch = max(cw, int(x1 - x0) + 20), max(ch, int(y1 - y0) + 20)
    lo_x, hi_x = max(0, int(x1) - cw), min(int(x0), W - cw)
    lo_y, hi_y = max(0, int(y1) - ch), min(int(y0), H - ch)
    cx = rng.randint(lo_x, max(lo_x, hi_x))
    cy = rng.randint(lo_y, max(lo_y, hi_y))
    return frame[cy:cy + ch, cx:cx + cw], [(x0 - cx, y0 - cy, x1 - cx, y1 - cy)]


def frames(clip: Path):
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS)

    def at(t: float):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, f = cap.read()
        return f if ok else None
    return at, cap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="folder with the carried-box JSON files")
    args = ap.parse_args()
    rng = random.Random(17)
    made: dict[str, list[Path]] = {}

    for scene, spec in SCENES.items():
        for label_file, clip, spans in (spec if isinstance(spec, list) else [spec]):
            boxes = json.loads((Path(args.labels) / label_file).read_text())["boxes"]
            at, cap = frames(FOOTAGE / clip)
            for t_s, box in boxes.items():
                t = float(t_s)
                if not any(a <= t <= b for a, b in spans):
                    continue
                f = at(t)
                if f is None:
                    continue
                stem = f"{scene}_{clip[17:23]}_{t:05.2f}"
                made.setdefault(scene, []).append(write(f, [box], f"{stem}_full", scene))
                for i, frac in enumerate((rng.uniform(0.4, 0.6), rng.uniform(0.2, 0.33))):
                    img, b = crop_around(f, box, frac, rng)
                    made[scene].append(write(img, b, f"{stem}_c{i}", scene))
            cap.release()

    for clip in NEGATIVE_CLIPS:
        at, cap = frames(FOOTAGE / clip)
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
        t = 0.0
        while t < n - 0.5:
            f = at(t)
            if f is not None:
                stem = f"neg_{clip[17:23]}_{t:05.2f}"
                made.setdefault("neg", []).append(write(f, [], f"{stem}_full", "neg"))
                H, W = f.shape[:2]
                frac = rng.uniform(0.25, 0.5)
                cw, ch = int(W * frac), int(H * frac)
                x, y = rng.randint(0, W - cw), rng.randint(0, H - ch)
                made["neg"].append(write(f[y:y + ch, x:x + cw], [], f"{stem}_c0", "neg"))
            t += 0.5
        cap.release()

    old = sorted((OLD / "images/train").glob("*.jpg"))
    old = random.Random(4).sample(old, min(OLD_SUBSET, len(old)))
    old_val = sorted((OLD / "images/val").glob("*.jpg"))

    def lst(name: str, paths) -> str:
        p = OUT / f"{name}.txt"
        p.write_text("\n".join(str(x).replace("\\", "/") for x in paths) + "\n")
        return str(p).replace("\\", "/")

    real = {k: v for k, v in made.items() if k != "neg"}
    for held in list(real) + [None]:
        train = old + made["neg"] + [p for k, v in real.items() if k != held for p in v]
        # Positive real images are few next to 5000 composites: repeat them so each epoch sees them often.
        reps = [p for k, v in real.items() if k != held for p in v] * 3
        name = f"cv_{held}" if held else "final"
        val = [p for p in real[held] if p.stem.endswith("_full")] if held else old_val[:800] + [
            p for v in real.values() for p in v if p.stem.endswith("_full")]
        (OUT / f"{name}.yaml").write_text(
            f"train: {lst(name + '_train', train + reps)}\nval: {lst(name + '_val', val)}\nnc: 1\nnames:\n  0: buried_person\n")
    print({k: len(v) for k, v in made.items()}, "old subset", len(old))


if __name__ == "__main__":
    main()
