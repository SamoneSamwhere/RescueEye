"""
Hard negatives for the victim (person) detector: real footage with nobody in it.

On the team's staged shoot of 17 Nov 2026 the installed detector boxed a
black-and-white striped pole lying on the ground at 0.40-0.76, plus a blue
pipe, a yellow bag and stacked pipes. Under an angled camera the casualty
gate then called the pole a casualty (still, and lying flat). These frames,
with empty labels, teach it those objects are not people.

  dji_fly_..._0104  poles, pipes, bags; no people. First half used here,
                    the second half (TEST_FROM_S on) kept back for testing.
  dji_fly_..._0027  a stack of pipes among trees; no people.

Each frame is used whole and as two random crops, so the objects are also
seen at the larger size a lower flight gives. The training list mixes in a
fixed random sample of the detector's own data (small_person + person_lying)
so it keeps finding people while it learns this.

Writes C:/RescueEyeData/hardneg/{images/train/*.jpg, hardneg_train.txt,
hardneg_val.txt, hardneg.yaml}; no label files (background images).

    .venv/Scripts/python.exe scripts/training/prepare_hard_negatives.py
    .venv-train/Scripts/python.exe scripts/training/train_small_person.py \
        --data C:/RescueEyeData/hardneg/hardneg_full.yaml --tag victim_hardneg_full --epochs 3 --workers 2
    (prepare with --full; without it a quick 8000-image subset is written to hardneg.yaml)
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2

FOOTAGE = Path("D:/RE RescueEye/footage-2026-11-17")
OUT = Path("C:/RescueEyeData/hardneg")
API = Path(__file__).resolve().parents[2]
SMALL = API / "data/small_person/images"
LYING = Path("C:/RescueEyeData/person_lying/images")
CLIPS = {"dji_fly_20261117_142802_0104.mp4": (0.0, 18.0),     # TEST_FROM_S = 18
         "dji_fly_20261117_140514_0027.mp4": (0.0, 45.0)}
TEST_FROM_S = 18.0
STEP_S = 0.5
KEEP_SMALL, KEEP_LYING = 6000, 2000
NEG_REPEAT = 2
MAX_SIDE = 1280


def save(img, name: str) -> Path:
    h, w = img.shape[:2]
    s = MAX_SIDE / max(h, w)
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    p = OUT / "images/train" / f"{name}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="keep ALL of the detector's own training data (writes hardneg_full.yaml). "
                         "The 8000-image subset made a 4-epoch run lose precision on UAV-SAR "
                         "(AP 0.716 -> 0.666), so the subset is only for quick trials.")
    args = ap.parse_args()
    keep_small, keep_lying, repeat, tag = ((10 ** 9, 10 ** 9, 6, "hardneg_full") if args.full
                                           else (KEEP_SMALL, KEEP_LYING, NEG_REPEAT, "hardneg"))
    rng = random.Random(19)
    neg: list[Path] = []
    for clip, (a, b) in CLIPS.items():
        cap = cv2.VideoCapture(str(FOOTAGE / clip))
        fps = cap.get(cv2.CAP_PROP_FPS)
        t = a
        while t < b:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
            ok, f = cap.read()
            if ok:
                stem = f"neg_{clip[-8:-4]}_{t:05.2f}"
                neg.append(save(f, stem))
                H, W = f.shape[:2]
                for i in range(2):
                    frac = rng.uniform(0.3, 0.5)
                    cw, ch = int(W * frac), int(H * frac)
                    x, y = rng.randint(0, W - cw), rng.randint(0, H - ch)
                    neg.append(save(f[y:y + ch, x:x + cw], f"{stem}_c{i}"))
            t += STEP_S
        cap.release()

    def pick(folder: Path, n: int, seed: int) -> list[Path]:
        files = sorted(folder.glob("*.jpg"))
        return random.Random(seed).sample(files, min(n, len(files)))

    train = pick(SMALL / "train", keep_small, 1) + pick(LYING / "train", keep_lying, 2) + neg * repeat
    val = pick(SMALL / "val", 500, 3) + pick(LYING / "val", 300, 4)
    for name, items in ((f"{tag}_train", train), (f"{tag}_val", val)):
        (OUT / f"{name}.txt").write_text("\n".join(str(p).replace("\\", "/") for p in items) + "\n")
    (OUT / f"{tag}.yaml").write_text(
        f"train: {(OUT / f'{tag}_train.txt').as_posix()}\nval: {(OUT / f'{tag}_val.txt').as_posix()}\n"
        "nc: 1\nnames:\n  0: person\n")
    print(f"negatives {len(neg)} (x{repeat}), train {len(train)}, val {len(val)} -> {tag}.yaml")


if __name__ == "__main__":
    main()
