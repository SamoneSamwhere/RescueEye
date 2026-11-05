"""
Extra training data for the second casualty detector, added on top of the
first one's dataset (prepare_casualty_dataset.py), not copied into it.

Why: the first model called 60% of Okutama's lying people "down" and almost no
upright ones, but found nothing at all in rescue-patrol - a woman lying flat on
sand, filmed straight down from close range. Okutama's lying actors are small
and filmed at an angle, and training had rotation off (a standing person turned
on their side looks like a lying one), so "down" never varied in heading.

  rotated   every Okutama frame with someone lying, once more, with each lying
            person's square patch turned 90, 180 or 270 degrees. Lying is lying
            at any heading; upright people around them are left as they are. A
            patch of plain ground is turned too, so a turned square is not
            itself the sign of "down".
  overhead  COCO people, whole body showing and facing the camera, pasted at a
            random heading onto ground seen from above: seen straight down, a
            body lying flat looks like that. Backgrounds are empty HERIDAL
            wilderness tiles, damage photos, and VisDrone street tiles whose
            walking people stay labelled upright, so pasted down people and
            real upright ones share images. COCO objects are pasted as unlabelled
            decoys and a quarter of the images get decoys only, so "pasted"
            never means "down" (the lesson of the buried-person model).
            On ground filmed at an angle, half the pasted people are stood up
            and labelled upright, and the lying ones lie across the view. The
            second model, which pasted every one as down at any heading, called
            people standing on a roof and firefighters by a truck "down": it
            had learned "a clearly visible whole person" instead of "lying".

Train and val use different COCO splits and different backgrounds.

    .venv-train/Scripts/python.exe scripts/training/prepare_casualty_v2.py fetch
    .venv-train/Scripts/python.exe scripts/training/prepare_casualty_v2.py build
Output: C:/RescueEyeData/casualty_v2/ and C:/RescueEyeData/casualty_v2.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_buried_dataset import _object_cutout  # noqa: E402

API = Path(__file__).resolve().parents[2]
DATA = Path("C:/RescueEyeData")
V1 = DATA / "casualty"
COCO = DATA / "coco"
OUT = DATA / "casualty_v2"
SMALL = API / "data/small_person"
DAMAGE = API / "data/damage"

UPRIGHT, DOWN = 0, 1
W, H = 960, 540            # canvas: a VisDrone tile, and a 16:9 drone frame
# COCO keypoints
L_SH, R_SH, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 5, 6, 11, 12, 13, 14, 15, 16


# -- fetch ----------------------------------------------------------------------

def _whole_body(ann: dict, others: list, im: dict) -> bool:
    """Whole body labelled, facing the camera, clear of other people and the image edge."""
    kp = ann["keypoints"]
    vis = lambda i: kp[i * 3 + 2] == 2  # noqa: E731
    x, y, w, h = ann["bbox"]
    if (ann["iscrowd"] or not isinstance(ann["segmentation"], list) or h < 150 or ann["area"] < 8000
            or not all(vis(i) for i in (L_SH, R_SH, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN))
            or x < 2 or y < 2 or x + w > im["width"] - 2 or y + h > im["height"] - 2):
        return False
    shoulders = abs(kp[L_SH * 3] - kp[R_SH * 3])
    if shoulders < 0.18 * h:   # side-on: from above it would not read as a body lying flat
        return False
    for o in others:
        if o is ann:
            continue
        ox, oy, ow, oh = o["bbox"]
        ix = max(0, min(x + w, ox + ow) - max(x, ox))
        iy = max(0, min(y + h, oy + oh) - max(y, oy))
        if ix * iy > 0.1 * w * h:
            return False
    return True


def _download(items: list[tuple[str, Path]]) -> list[bool]:
    def get(item) -> bool:
        url, dst = item
        if dst.exists() and dst.stat().st_size > 0:
            return True
        try:
            urllib.request.urlretrieve(url, dst)
            return True
        except Exception as exc:  # one missing image is not worth stopping for
            print("skip", dst.name, exc)
            dst.unlink(missing_ok=True)
            return False
    with ThreadPoolExecutor(16) as pool:
        return list(pool.map(get, items))


def fetch_people(split: str, n_images: int, seed: int) -> None:
    data = json.loads((COCO / f"annotations/person_keypoints_{split}2017.json").read_text())
    images = {im["id"]: im for im in data["images"]}
    all_by_image: dict[int, list] = {}
    for ann in data["annotations"]:
        all_by_image.setdefault(ann["image_id"], []).append(ann)
    del data
    by_image = {i: [a for a in anns if _whole_body(a, anns, images[i])] for i, anns in all_by_image.items()}
    ids = sorted(i for i, anns in by_image.items() if anns)
    print(f"{split}: {len(ids)} images with a usable whole body")
    random.Random(seed).shuffle(ids)
    ids = ids[:n_images]
    d = COCO / f"people_{split}"
    d.mkdir(parents=True, exist_ok=True)
    ok = _download([(images[i]["coco_url"], d / images[i]["file_name"]) for i in ids])
    people = [{"file": images[i]["file_name"], "segmentation": a["segmentation"]}
              for i, good in zip(ids, ok) if good for a in by_image[i]]
    (COCO / f"people_{split}.json").write_text(json.dumps(people))
    print(f"{split}: {sum(ok)} images, {len(people)} people")


def fetch_objects(n_images: int, seed: int) -> None:
    data = json.loads((COCO / "annotations/instances_val2017.json").read_text())
    images = {im["id"]: im for im in data["images"]}
    by_image: dict[int, list] = {}
    for ann in data["annotations"]:
        x, y, w, h = ann["bbox"]
        if (ann["category_id"] != 1 and not ann["iscrowd"] and isinstance(ann["segmentation"], list)
                and ann["area"] >= 2500 and max(w, h) >= 50):
            by_image.setdefault(ann["image_id"], []).append(ann)
    ids = sorted(by_image)
    random.Random(seed).shuffle(ids)
    ids = ids[:n_images]
    d = COCO / "objects"
    d.mkdir(parents=True, exist_ok=True)
    ok = _download([(images[i]["coco_url"], d / images[i]["file_name"]) for i in ids])
    split: dict[str, list] = {"train": [], "val": []}
    for i, good in zip(ids, ok):
        if good:
            side = "val" if int(hashlib.md5(str(i).encode()).hexdigest(), 16) % 100 < 15 else "train"
            split[side] += [{"file": images[i]["file_name"], "segmentation": a["segmentation"]} for a in by_image[i]]
    for side, objs in split.items():
        (COCO / f"objects_{side}.json").write_text(json.dumps(objs))
        print(f"objects {side}: {len(objs)}")


# -- build: rotated Okutama ------------------------------------------------------

def _yolo_boxes(label: Path, w: int, h: int) -> list[tuple[int, list[float]]]:
    out = []
    for line in label.read_text().splitlines():
        if line.strip():
            c, x, y, bw, bh = line.split()
            x, y, bw, bh = float(x) * w, float(y) * h, float(bw) * w, float(bh) * h
            out.append((int(c), [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2]))
    return out


def _line(c: int, b, w: int, h: int) -> str:
    x1, y1, x2, y2 = max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])
    return f"{c} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}\n"


def _put(split: str, name: str, img: np.ndarray, lines: list[str]) -> None:
    (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / "images" / split / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    (OUT / "labels" / split / f"{name}.txt").write_text("".join(lines))


def _turn(img: np.ndarray, x0: int, y0: int, side: int, k: int) -> None:
    """Turns a square patch in place, blended in through a soft round edge: a
    hard square seam would itself become the sign of "down"."""
    sq = img[y0:y0 + side, x0:x0 + side].astype(np.float32)
    yy, xx = np.mgrid[:side, :side]
    r = np.hypot(xx - (side - 1) / 2, yy - (side - 1) / 2) / (side / 2)
    m = np.clip((1.0 - r) / 0.16, 0, 1)[..., None]
    img[y0:y0 + side, x0:x0 + side] = (sq * (1 - m) + np.rot90(sq, k) * m).astype(np.uint8)


def rotated(split: str, rng: random.Random) -> int:
    n = 0
    for img_path in sorted((V1 / "images" / split).glob("ok_*.jpg")):
        label = V1 / "labels" / split / f"{img_path.stem}.txt"
        boxes = _yolo_boxes(label, 1280, 720)
        if not any(c == DOWN for c, _ in boxes):
            continue
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        lines, squares = [], []
        for c, b in boxes:
            if c != DOWN:
                lines.append(_line(c, b, w, h))
                continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            side = int(max(b[2] - b[0], b[3] - b[1]) * 1.5) + 4
            x0, y0 = int(cx - side / 2), int(cy - side / 2)
            if x0 < 0 or y0 < 0 or x0 + side > w or y0 + side > h:
                lines.append(_line(c, b, w, h))      # at the frame edge: left as it is
                continue
            k = rng.choice((1, 2, 3))
            _turn(img, x0, y0, side, k)
            squares.append((x0, y0, x0 + side, y0 + side))
            # The box turns with the patch about the patch centre.
            bw, bh = b[2] - b[0], b[3] - b[1]
            if k % 2:
                bw, bh = bh, bw
            pcx, pcy = x0 + side / 2, y0 + side / 2
            dx, dy = cx - pcx, cy - pcy
            dx, dy = {1: (dy, -dx), 2: (-dx, -dy), 3: (-dy, dx)}[k]
            ncx, ncy = pcx + dx, pcy + dy
            lines.append(_line(DOWN, [ncx - bw / 2, ncy - bh / 2, ncx + bw / 2, ncy + bh / 2], w, h))
        # A turned patch of ground somewhere with nobody in it.
        for _ in range(30):
            side = rng.randint(30, 120)
            x0, y0 = rng.randint(0, w - side), rng.randint(0, h - side)
            if all(x0 + side < b[0] or b[2] < x0 or y0 + side < b[1] or b[3] < y0
                   for b in [bb for _, bb in boxes] + squares):
                _turn(img, x0, y0, side, rng.choice((1, 2, 3)))
                break
        _put(split, f"okrot_{img_path.stem}", img, lines)
        n += 1
    return n


# -- build: overhead composites --------------------------------------------------

def _backgrounds(split: str) -> list[tuple[Path, Path | None]]:
    """(image, label or None). VisDrone keeps its labels; the others must be empty of people."""
    out = []
    for f in sorted((SMALL / "images" / split).glob("vd_*")):
        out.append((f, SMALL / "labels" / split / f"{f.stem}.txt"))
    for f in sorted((SMALL / "images" / split).glob("her_*")):
        lbl = SMALL / "labels" / split / f"{f.stem}.txt"
        if not lbl.exists() or not lbl.read_text().strip():
            out.append((f, None))
    for cls in ("no_damage", "structural_damage", "flood_damage", "fire_damage"):
        out += [(f, None) for f in sorted((DAMAGE / split / cls).glob("*"))]
    return out


def _canvas(bg: tuple[Path, Path | None], rng: random.Random):
    img = cv2.imread(str(bg[0]))
    h, w = img.shape[:2]
    if bg[1] is not None and (w, h) == (W, H):
        return img.copy(), [_line(UPRIGHT, b, W, H) for _, b in _yolo_boxes(bg[1], W, H)], \
            [b for _, b in _yolo_boxes(bg[1], W, H)]
    s = max(W / w, H / h)
    img = cv2.resize(img, (max(W, round(w * s)), max(H, round(h * s))), interpolation=cv2.INTER_AREA)
    oy, ox = rng.randint(0, img.shape[0] - H), rng.randint(0, img.shape[1] - W)
    img = img[oy:oy + H, ox:ox + W]
    if rng.random() < 0.5:
        img = cv2.flip(img, rng.choice((0, 1, -1)))
    return img.copy(), [], []


def _body_cutout(person: dict, img: np.ndarray):
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for poly in person["segmentation"]:
        cv2.fillPoly(mask, [np.array(poly, np.int32).reshape(-1, 2)], 255)
    ys, xs = np.nonzero(mask)
    if len(xs) < 500:
        return None
    x0, x1, y0, y1 = max(0, xs.min() - 3), min(w, xs.max() + 4), max(0, ys.min() - 3), min(h, ys.max() + 4)
    return img[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1].copy()


def _paste(canvas, rgb, alpha, length, rng, taken, shadow: bool, angle: float | None = None):
    angle = rng.uniform(0, 360) if angle is None else angle
    h, w = alpha.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    rgb = cv2.warpAffine(rgb, M, (nw, nh), flags=cv2.INTER_LINEAR)
    alpha = cv2.warpAffine(alpha, M, (nw, nh), flags=cv2.INTER_LINEAR)
    # Scale by the body's own length, so the size is the same at any heading.
    s = length / max(h, w)
    nw, nh = max(4, round(nw * s)), max(4, round(nh * s))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    rgb, alpha = cv2.resize(rgb, (nw, nh), interpolation=interp), cv2.resize(alpha, (nw, nh), interpolation=interp)
    if nw >= W - 4 or nh >= H - 4:
        return None
    for _ in range(30):
        x, y = rng.randint(2, W - nw - 2), rng.randint(2, H - nh - 2)
        if all(x + nw < a or a2 < x or y + nh < b or b2 < y for a, b, a2, b2 in taken):
            break
    else:
        return None
    patch = canvas[y:y + nh, x:x + nw].astype(np.float32)
    a = alpha.astype(np.float32) / 255
    if shadow:   # a body lying on the ground casts a short soft shadow
        off = max(1, round(min(nw, nh) * 0.06))
        sh = cv2.GaussianBlur(np.roll(np.roll(a, off, 0), off, 1), (0, 0), max(1.0, off))
        patch = patch * (1 - 0.45 * sh[..., None])
    person = rgb.astype(np.float32)
    pull = rng.uniform(0.0, 0.25)   # light and haze of the scene
    person = person * (1 - pull) + patch.mean(axis=(0, 1)) * pull
    person = person * rng.uniform(0.8, 1.15)
    a = cv2.GaussianBlur(a, (3, 3), 0) if min(nw, nh) > 8 else a
    canvas[y:y + nh, x:x + nw] = (patch * (1 - a[..., None]) + person * a[..., None]).clip(0, 255).astype(np.uint8)
    ys, xs = np.nonzero(a > 0.5)
    if len(xs) < 20:
        return None
    box = [x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1]
    taken.append(box)
    return box


def overhead(split: str, n_images: int, rng: random.Random) -> dict:
    people = json.loads((COCO / f"people_{split}.json").read_text())
    objects = json.loads((COCO / f"objects_{split}.json").read_text())
    backgrounds = _backgrounds(split)
    rng.shuffle(people)
    counts = {"images": 0, "down": 0, "upright": 0, "decoys": 0, "decoy_only": 0}
    cache: dict[str, np.ndarray] = {}

    def load(path: Path) -> np.ndarray:
        key = str(path)
        if key not in cache:
            if len(cache) > 300:
                cache.clear()
            cache[key] = cv2.imread(key)
        return cache[key]

    pi = 0
    for i in range(n_images):
        bg = rng.choice(backgrounds)
        # HERIDAL tiles are filmed straight down; VisDrone and the damage photos mostly at an angle.
        nadir = bg[0].name.startswith("her_")
        canvas, lines, taken = _canvas(bg, rng)
        taken = [list(b) for b in taken]
        decoy_only = rng.random() < 0.25
        for _ in range(0 if decoy_only else rng.choice((1, 1, 1, 2, 2, 3))):
            person = people[pi % len(people)]
            pi += 1
            cut = _body_cutout(person, load(COCO / f"people_{split}" / person["file"]))
            if cut is None:
                continue
            # Body length at 960x540: ~20 px from high up, ~240 px from a few metres.
            length = math.exp(rng.uniform(math.log(20), math.log(240)))
            if nadir:
                # Straight down, a body lying flat can point any way.
                cls, angle, shadow = DOWN, rng.uniform(0, 360), rng.random() < 0.6
            elif rng.random() < 0.5:
                # At an angle, the same photo stood up is someone standing: upright.
                cls, angle, shadow = UPRIGHT, rng.uniform(-10, 10), False
            else:
                # ...and lying is lying across the view, never stood up in it.
                cls, angle, shadow = DOWN, rng.choice((90, 270)) + rng.uniform(-35, 35), rng.random() < 0.6
            box = _paste(canvas, *cut, length, rng, taken, shadow=shadow, angle=angle)
            if box is not None:
                lines.append(_line(cls, box, W, H))
                counts["down" if cls == DOWN else "upright"] += 1
        for _ in range(rng.randint(1, 3) if decoy_only else rng.randint(0, 2)):
            obj = rng.choice(objects)
            cut = _object_cutout(obj, load(COCO / "objects" / obj["file"]), rng)
            if cut is None:
                continue
            length = math.exp(rng.uniform(math.log(20), math.log(200)))
            if _paste(canvas, *cut, length, rng, taken, shadow=rng.random() < 0.6) is not None:
                counts["decoys"] += 1
        counts["decoy_only"] += decoy_only
        _put(split, f"ovh_{split}_{i:05d}", canvas, lines)
        counts["images"] += 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("fetch", "build"))
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()
    if args.stage == "fetch":
        fetch_people("train", 2500, args.seed)
        fetch_people("val", 400, args.seed)
        fetch_objects(1500, args.seed)
        return
    import shutil
    if OUT.exists():
        shutil.rmtree(OUT)
    for split, n, seed in (("train", 4000, args.seed), ("val", 500, args.seed + 1)):
        rng = random.Random(seed)
        print(split, "rotated Okutama:", rotated(split, rng), flush=True)
        print(split, "overhead:", overhead(split, n, rng), flush=True)
    (DATA / "casualty_v2.yaml").write_text(
        f"path: {DATA.as_posix()}\n"
        "train: [casualty/images/train, casualty_v2/images/train]\n"
        "val: [casualty/images/val, casualty_v2/images/val]\n"
        "test: casualty/images/test\n"
        "nc: 3\nnames:\n  0: upright\n  1: down\n  2: partial\n")


if __name__ == "__main__":
    main()
