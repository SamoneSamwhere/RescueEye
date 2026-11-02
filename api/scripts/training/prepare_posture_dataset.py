"""
Build data/posture/: person crops labelled lying / not_lying, for the posture
classifier the casualty gate runs on every person the detector finds.

Why a classifier and not a new detector: the live person detector is single
class (the ORT decode reads score row 0), and it is good at finding people. What
it cannot say is whether a person is down. The keypoint posture rule answers
that well from overhead but badly in close oblique shots, where walkers read as
lying. A crop classifier learns the look of a body on the ground directly.

Sources:
  Okutama-Action (github.com/miquelmarti/Okutama-Action, 1280x720 frames zips)
      real DJI Phantom 4 footage, 10-45 m, every person labelled per frame.
      "Lying" -> lying; every other action (standing, walking, running,
      sitting, carrying, ...) -> not_lying. Labels are in 3840x2160 pixels.
  VisDrone2019-DET (HF shijli/visdrone2019-det, CC BY-NC-SA 3.0) category 1
      "pedestrian" (walking or standing) -> not_lying, so the upright class
      is not all one baseball field.

Rejected: C2A's pose labels. Boxes labelled lying are the same shape as
kneeling/sitting/bent ones (median w/h 0.85 for all four) and spot checks show
standing people labelled lying, so they carry no posture information.

Splits are by video, never by frame - neighbouring frames are near duplicates.
Okutama's own test set is the test split, minus TEST_TO_TRAIN; two training
videos are held out as val. VisDrone's train shards split 90/10 by image id; its test shard is test.

    .venv-train/Scripts/python.exe scripts/training/prepare_posture_dataset.py --okutama <dir with TrainSetFrames.zip, TestSetFrames.zip>
"""
from __future__ import annotations

import argparse
import io
import random
import zipfile
import zlib
from collections import Counter
from pathlib import Path

from PIL import Image

API = Path(__file__).resolve().parents[2]
OUT = API / "data/posture"
VISDRONE = Path(r"C:\RescueEyeData\downloads\visdrone\detection")

CROP = 96            # saved crop side; the classifier trains at this size
CONTEXT = 1.3        # square crop side = longest box side * CONTEXT
MIN_SIDE = 12        # px; smaller boxes carry no posture information
LABEL_SCALE = 3.0    # Okutama labels are 3840x2160, the frames 1280x720
VAL_VIDEOS = {"1.2.6", "2.1.7"}   # training videos held out, both with lying actors
# Okutama test video moved into training: close shots of a person curled up on
# the ground with others standing beside them. Nothing in the training videos
# looks like it, and the first two models missed 77-89% of its lying people -
# the close-shot case the gate most needs. 1.1.8 and 1.2.10 stay held out.
TEST_TO_TRAIN = {"2.2.10"}

# Every Nth frame of a track: lying is the rare class, so it is sampled densely.
LYING_EVERY = 1
NOT_LYING_EVERY = 20
VISDRONE_CAP = {"train": 6000, "val": 700, "test": 1500}


def square_crop(img: Image.Image, cx: float, cy: float, side: float) -> Image.Image:
    """Square crop around a box centre, padded with black where it leaves the frame."""
    half = side / 2
    box = (round(cx - half), round(cy - half), round(cx + half), round(cy + half))
    return img.crop(box).resize((CROP, CROP), Image.BILINEAR)


def save(crop: Image.Image, split: str, cls: str, name: str) -> None:
    d = OUT / split / cls
    d.mkdir(parents=True, exist_ok=True)
    crop.convert("RGB").save(d / f"{name}.jpg", quality=92)


def prepare_okutama(zip_path: Path, test: bool) -> Counter:
    z = zipfile.ZipFile(zip_path)
    frames = {}
    for n in z.namelist():
        parts = n.split("/")
        if len(parts) == 5 and parts[2].startswith("Extracted-Frames") and parts[4].endswith(".jpg"):
            frames[(parts[3], parts[4][:-4])] = n
    counts = Counter()
    for label_file in sorted(n for n in z.namelist() if "/SingleActionLabels/" in n and n.endswith(".txt")):
        video = Path(label_file).stem
        split = ("train" if video in TEST_TO_TRAIN else "test") if test else (
            "val" if video in VAL_VIDEOS else "train")
        by_frame: dict[str, list] = {}
        for row in z.read(label_file).decode().split("\n"):
            r = row.split()
            # id xmin ymin xmax ymax frame lost occluded generated "label" "action"
            if len(r) < 11 or r[6] != "0" or r[7] != "0":
                continue
            lying = r[10].strip('"') == "Lying"
            if int(r[5]) % (LYING_EVERY if lying else NOT_LYING_EVERY):
                continue
            box = [int(v) / LABEL_SCALE for v in r[1:5]]
            if max(box[2] - box[0], box[3] - box[1]) < MIN_SIDE:
                continue
            by_frame.setdefault(r[5], []).append((r[0], lying, box))
        for frame, people in by_frame.items():
            name = frames.get((video, frame))
            if name is None:
                continue
            img = Image.open(io.BytesIO(z.read(name))).convert("RGB")
            for track, lying, (x1, y1, x2, y2) in people:
                cls = "lying" if lying else "not_lying"
                side = max(x2 - x1, y2 - y1) * CONTEXT
                save(square_crop(img, (x1 + x2) / 2, (y1 + y2) / 2, side), split, cls,
                     f"ok_{video}_{frame}_{track}")
                counts[(split, cls)] += 1
        print(f"  okutama {video} -> {split}: {sum(v for k, v in counts.items() if k[0] == split)} so far", flush=True)
    return counts


def prepare_visdrone(rng: random.Random) -> Counter:
    import pyarrow.parquet as pq

    counts = Counter()
    for shard in sorted(VISDRONE.glob("*.parquet")):
        is_test = shard.name.startswith("test")
        for row in pq.read_table(shard).to_pylist():
            split = "test" if is_test else ("val" if zlib.crc32(str(row["id"]).encode()) % 10 == 0 else "train")
            if counts[(split, "not_lying")] >= VISDRONE_CAP[split]:
                continue
            obj = row["objects"]
            boxes = [(x, y, bw, bh) for (x, y, bw, bh), cat, score
                     in zip(obj["bbox"], obj["category"], obj["score"])
                     if cat == 1 and score != 0 and max(bw, bh) >= MIN_SIDE]
            if not boxes:
                continue
            img = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB")
            # A few per image, so the set spans many scenes rather than a few crowds.
            for j, (x, y, bw, bh) in enumerate(rng.sample(boxes, min(4, len(boxes)))):
                save(square_crop(img, x + bw / 2, y + bh / 2, max(bw, bh) * CONTEXT),
                     split, "not_lying", f"vd_{row['id']}_{j}")
                counts[(split, "not_lying")] += 1
        print(f"  visdrone {shard.name} done", flush=True)
    return counts


NOT_LYING_TRAIN_MAX = 15000


def balance_train(rng: random.Random) -> None:
    """
    Training split only. Lying people come from about twenty actors, so the
    class is both rare and narrow. Each lying crop gets one copy rotated by 90,
    180 or 270 degrees: a body on the ground is still lying at any rotation,
    and the turned copies stand in for straight-down views. Upright crops are
    never rotated - a standing person turned 90 degrees looks like a lying one.
    The upright class is then thinned to keep the ratio near 1:1.
    """
    lying = sorted((OUT / "train/lying").glob("*.jpg"))
    for f in lying:
        Image.open(f).rotate(rng.choice((90, 180, 270))).save(f.with_name(f.stem + "_rot.jpg"), quality=92)
    upright = sorted((OUT / "train/not_lying").glob("*.jpg"))
    rng.shuffle(upright)
    for f in upright[NOT_LYING_TRAIN_MAX:]:
        f.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--okutama", type=Path, required=True,
                    help="folder holding TrainSetFrames.zip and TestSetFrames.zip")
    args = ap.parse_args()
    counts = (prepare_okutama(args.okutama / "TrainSetFrames.zip", test=False)
              + prepare_okutama(args.okutama / "TestSetFrames.zip", test=True)
              + prepare_visdrone(random.Random(0)))
    for split in ("train", "val", "test"):
        print(split, {c: counts[(split, c)] for c in ("lying", "not_lying")})
    balance_train(random.Random(0))
    print("train after balancing:",
          {c: len(list((OUT / "train" / c).glob("*.jpg"))) for c in ("lying", "not_lying")})


if __name__ == "__main__":
    main()
