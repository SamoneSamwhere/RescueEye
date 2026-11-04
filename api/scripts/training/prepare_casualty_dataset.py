"""
Builds the dataset for the casualty detector: one detector that says, for
every person, whether they are upright, down, or only partly visible.

  0 upright   standing, walking, running, sitting, carrying...
  1 down      lying on the ground
  2 partial   only part of the body shows: under rubble, or in water

Why a detector and not the old crop classifier (prepare_posture_dataset.py):
the classifier saw a 96px crop and nothing else, and scored 0 on a casualty
filmed straight down - from overhead a body lying flat looks like an upright
one seen from an angle. A detector sees the whole frame: the ground, the
shadows, the people around, and how big a standing person is at that range.
Okutama-Action was filmed at 45 and 90 degrees, so both views are in training.

Sources:
  Okutama-Action   real drone video, 10-45 m, every person labelled per frame
                   with an action. "Lying" -> down; anything else -> upright.
                   Split by video: two training videos are val, the official
                   test set is test (never trained on).
  VisDrone tiles   from data/small_person (vd_*): street scenes, people upright.
  buried dataset   C:/RescueEyeData/buried/dataset (prepare_buried_dataset.py):
                   composited partly buried people and real SeaDronesSee
                   swimmers -> partial, plus its decoy and negative images.

    .venv-train/Scripts/python.exe scripts/training/prepare_casualty_dataset.py
Output: C:/RescueEyeData/casualty/ (D: is nearly full)
"""
from __future__ import annotations

import argparse
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

API = Path(__file__).resolve().parents[2]
OKUTAMA = Path("C:/RescueEyeData/okutama")
BURIED = Path("C:/RescueEyeData/buried/dataset")
OUT = Path("C:/RescueEyeData/casualty")

UPRIGHT, DOWN, PARTIAL = 0, 1, 2
NAMES = {UPRIGHT: "upright", DOWN: "down", PARTIAL: "partial"}

LABEL_SCALE = 3.0                  # Okutama labels are 3840x2160, frames 1280x720
FRAME_W, FRAME_H = 1280, 720
VAL_VIDEOS = {"1.2.6", "2.1.7"}    # training videos held out, both with lying actors
# Close shots of a person curled up on the ground with others beside them. No
# training video looks like it, so the posture work moved it into training.
TEST_TO_TRAIN = {"2.2.10"}
# Neighbouring frames are near duplicates. Frames with someone lying are rare
# and kept densely; frames of only upright people are thinned hard.
DOWN_FRAME_EVERY = 3
UPRIGHT_FRAME_EVERY = 30
MIN_SIDE = 6                       # px at 1280x720; smaller boxes are noise


def _put(split: str, name: str, image_bytes: bytes | None, src: Path | None, lines: list[str]) -> None:
    img_dir, lbl_dir = OUT / "images" / split, OUT / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    if image_bytes is not None:
        (img_dir / f"{name}.jpg").write_bytes(image_bytes)
    else:
        shutil.copy2(src, img_dir / f"{name}{src.suffix}")
    (lbl_dir / f"{name}.txt").write_text("".join(lines))


def okutama(zip_path: Path, test_set: bool, counts: Counter) -> None:
    z = zipfile.ZipFile(zip_path)
    frames = {}
    for n in z.namelist():
        parts = n.split("/")
        if len(parts) == 5 and parts[2].startswith("Extracted-Frames") and parts[4].endswith(".jpg"):
            frames[(parts[3], parts[4][:-4])] = n
    for label_file in sorted(n for n in z.namelist() if "/SingleActionLabels/" in n and n.endswith(".txt")):
        video = Path(label_file).stem
        split = ("train" if video in TEST_TO_TRAIN else "test") if test_set else (
            "val" if video in VAL_VIDEOS else "train")
        by_frame: dict[int, list] = {}
        for row in z.read(label_file).decode().split("\n"):
            r = row.split()
            # id xmin ymin xmax ymax frame lost occluded generated "label" "action"
            # Occluded people are kept: a detector must see every person in
            # the frame labelled, or the unlabelled ones teach it "background".
            if len(r) < 11 or r[6] != "0":
                continue
            x1, y1, x2, y2 = (int(v) / LABEL_SCALE for v in r[1:5])
            if max(x2 - x1, y2 - y1) < MIN_SIDE:
                continue
            cls = DOWN if r[10].strip('"') == "Lying" else UPRIGHT
            by_frame.setdefault(int(r[5]), []).append((cls, x1, y1, x2, y2))
        for frame, people in sorted(by_frame.items()):
            has_down = any(p[0] == DOWN for p in people)
            if frame % (DOWN_FRAME_EVERY if has_down else UPRIGHT_FRAME_EVERY):
                continue
            name = frames.get((video, str(frame)))
            if name is None:
                continue
            lines = []
            for cls, x1, y1, x2, y2 in people:
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(FRAME_W, x2), min(FRAME_H, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                lines.append(f"{cls} {(x1 + x2) / 2 / FRAME_W:.6f} {(y1 + y2) / 2 / FRAME_H:.6f} "
                             f"{(x2 - x1) / FRAME_W:.6f} {(y2 - y1) / FRAME_H:.6f}\n")
                counts[(split, NAMES[cls])] += 1
            _put(split, f"ok_{video}_{frame}", z.read(name), None, lines)
            counts[(split, "images")] += 1
        print(f"  okutama {video} -> {split}", flush=True)


def visdrone(n_train: int, n_val: int, rng: random.Random, counts: Counter) -> None:
    for split, n in (("train", n_train), ("val", n_val)):
        tiles = sorted((API / f"data/small_person/images/{split}").glob("vd_*"))
        for f in rng.sample(tiles, min(n, len(tiles))):
            lbl = API / f"data/small_person/labels/{split}/{f.stem}.txt"
            lines = [l + "\n" for l in lbl.read_text().splitlines() if l.strip()]   # already class 0
            _put(split, f.stem, None, f, lines)
            counts[(split, "upright")] += len(lines)
            counts[(split, "images")] += 1


def buried(n_train: int, n_val: int, rng: random.Random, counts: Counter) -> None:
    """Partly buried composites, swimmers, decoys and negatives, relabelled to class 2."""
    for split, n in (("train", n_train), ("val", n_val)):
        files = sorted((BURIED / "images" / split).glob("*.jpg"))
        for f in rng.sample(files, min(n, len(files))):
            lbl = BURIED / "labels" / split / f"{f.stem}.txt"
            lines = [f"{PARTIAL} " + l.split(None, 1)[1] + "\n" for l in lbl.read_text().splitlines() if l.strip()]
            _put(split, f"bu_{f.stem}", None, f, lines)
            counts[(split, "partial")] += len(lines)
            counts[(split, "images")] += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    if OUT.exists():
        shutil.rmtree(OUT)
    counts: Counter = Counter()
    okutama(OKUTAMA / "TrainSetFrames.zip", test_set=False, counts=counts)
    okutama(OKUTAMA / "TestSetFrames.zip", test_set=True, counts=counts)
    visdrone(3000, 300, rng, counts)
    buried(5000, 600, rng, counts)
    for split in ("train", "val", "test"):
        print(split, {k: counts[(split, k)] for k in ("images", "upright", "down", "partial")})
    (OUT / "casualty.yaml").write_text(
        f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "nc: 3\nnames:\n  0: upright\n  1: down\n  2: partial\n")


if __name__ == "__main__":
    main()
