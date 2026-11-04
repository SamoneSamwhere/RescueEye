"""
Builds a dataset of partly buried people: only a hand, an arm, a head or a leg
showing out of rubble or floodwater, as a drone would see it.

No public aerial dataset has these, so they are composited:
  people     COCO 2017 person instances, which come with an outline and joint
             positions. The joints say where the hand, arm, head or leg is; the
             outline cuts out exactly those pixels.
  scenes     AIDER drone photos of collapsed buildings, fire and flooding
             (data/raw/damage/AIDER), tiled 2x2 at their native ~300px size.
  negatives  a quarter of the images have no one in them, so the model learns
             that rubble on its own is not a person.
  decoys     other COCO objects (bags, balls, chairs, animals...) pasted the
             same way but not labelled. Without them the first model learned
             "something pasted onto the scene" instead of "a hand": on real
             video it boxed rocks, signposts, cones, hay bales and smoke.
  real       unlabelled VisDrone street scenes (whole people walking, cones,
             signs) and D-Fire fire/smoke photos, from the datasets already
             on disk.
  swimmers   SeaDronesSee tiles, labelled: real people with only the head and
             arms above water, filmed from drones. Without real positives the
             second model learned "pasted = person, real photo = nobody" and
             found 0 of 807 held-out swimmers. The first 600 val tiles are
             kept out of training entirely, as a test of real partial people.

Train and val use different COCO splits and different AIDER photos, so the
val score is measured on people and scenes the model never saw.

Run in the training venv:
    .venv-train/Scripts/python.exe scripts/training/prepare_buried_dataset.py fetch
    .venv-train/Scripts/python.exe scripts/training/prepare_buried_dataset.py fetch-objects
    .venv-train/Scripts/python.exe scripts/training/prepare_buried_dataset.py build

Data lives on C: (D: is nearly full): C:/RescueEyeData/buried/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

API = Path(__file__).resolve().parents[2]
ROOT = Path("C:/RescueEyeData/buried")
RAW = ROOT / "raw"
OUT = ROOT / "dataset"
AIDER = API / "data/raw/damage/AIDER/AIDER"
# traffic_incident is left out: its photos show responders and drivers, unlabelled.
SCENE_CLASSES = ("collapsed_building", "fire", "flooded_areas")

CANVAS = 640
TILE = CANVAS // 2

# COCO keypoint indices
NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 0, 5, 6, 7, 8, 9, 10
L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 11, 12, 13, 14, 15, 16

# What shows above the rubble, and how often. Hands lead: that is the case
# this model exists for, and the hardest one.
PARTS = (("hand", 0.35), ("arm", 0.2), ("head", 0.2), ("leg", 0.1), ("upper_body", 0.15))


# -- fetch ----------------------------------------------------------------------

def _usable(ann: dict) -> bool:
    kp = ann["keypoints"]
    x, y, w, h = ann["bbox"]
    return (not ann["iscrowd"] and isinstance(ann["segmentation"], list)
            and ann["num_keypoints"] >= 8 and h >= 160 and ann["area"] >= 12000
            # at least one forearm, so a hand can be cut out
            and ((kp[L_EL * 3 + 2] and kp[L_WR * 3 + 2]) or (kp[R_EL * 3 + 2] and kp[R_WR * 3 + 2])))


def fetch(split: str, n_images: int, seed: int) -> None:
    data = json.loads((RAW / f"annotations/person_keypoints_{split}2017.json").read_text())
    images = {im["id"]: im for im in data["images"]}
    by_image: dict[int, list] = {}
    for ann in data["annotations"]:
        if _usable(ann):
            by_image.setdefault(ann["image_id"], []).append(ann)
    ids = sorted(by_image)
    random.Random(seed).shuffle(ids)
    ids = ids[:n_images]

    img_dir = RAW / f"coco_{split}"
    img_dir.mkdir(parents=True, exist_ok=True)

    def get(image_id: int) -> bool:
        im = images[image_id]
        dst = img_dir / im["file_name"]
        if dst.exists() and dst.stat().st_size > 0:
            return True
        try:
            urllib.request.urlretrieve(im["coco_url"], dst)
            return True
        except Exception as exc:  # one missing image is not worth stopping for
            print("skip", im["file_name"], exc)
            dst.unlink(missing_ok=True)
            return False

    with ThreadPoolExecutor(16) as pool:
        ok = list(pool.map(get, ids))
    people = [{"file": images[i]["file_name"], "segmentation": a["segmentation"], "keypoints": a["keypoints"]}
              for i, good in zip(ids, ok) if good for a in by_image[i]]
    (RAW / f"people_{split}.json").write_text(json.dumps(people))
    print(f"{split}: {sum(ok)} images, {len(people)} people")


def fetch_objects(n_images: int, seed: int) -> None:
    """Non-person COCO objects for decoys, from val2017 (its annotations are small enough to load)."""
    data = json.loads((RAW / "annotations/instances_val2017.json").read_text())
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
    img_dir = RAW / "coco_objects"
    img_dir.mkdir(parents=True, exist_ok=True)

    def get(image_id: int) -> bool:
        im = images[image_id]
        dst = img_dir / im["file_name"]
        if dst.exists() and dst.stat().st_size > 0:
            return True
        try:
            urllib.request.urlretrieve(im["coco_url"], dst)
            return True
        except Exception as exc:
            print("skip", im["file_name"], exc)
            dst.unlink(missing_ok=True)
            return False

    with ThreadPoolExecutor(16) as pool:
        ok = list(pool.map(get, ids))
    split: dict[str, list] = {"train": [], "val": []}
    for i, good in zip(ids, ok):
        if not good:
            continue
        side = "val" if int(hashlib.md5(str(i).encode()).hexdigest(), 16) % 100 < 15 else "train"
        split[side] += [{"file": images[i]["file_name"], "segmentation": a["segmentation"]} for a in by_image[i]]
    for side, objs in split.items():
        (RAW / f"objects_{side}.json").write_text(json.dumps(objs))
        print(f"objects {side}: {len(objs)}")


# -- build ----------------------------------------------------------------------

def _kp(person: dict, idx: int):
    kp = person["keypoints"]
    return np.array(kp[idx * 3:idx * 3 + 2], float) if kp[idx * 3 + 2] else None


def _capsule(shape, a, b, radius) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    cv2.line(m, tuple(int(v) for v in a), tuple(int(v) for v in b), 255, max(1, int(radius * 2)))
    cv2.circle(m, tuple(int(v) for v in a), int(radius), 255, -1)
    cv2.circle(m, tuple(int(v) for v in b), int(radius), 255, -1)
    return m


def _part_region(person: dict, part: str, shape, rng: random.Random):
    """A mask around the chosen body part, or None if its joints weren't labelled."""
    sides = [(L_SH, L_EL, L_WR, L_HIP, L_KN, L_AN), (R_SH, R_EL, R_WR, R_HIP, R_KN, R_AN)]
    rng.shuffle(sides)
    for sh, el, wr, hip, kn, an in sides:
        S, E, W = _kp(person, sh), _kp(person, el), _kp(person, wr)
        H, K, A = _kp(person, hip), _kp(person, kn), _kp(person, an)
        if part == "hand" and E is not None and W is not None:
            fore = W - E
            length = np.linalg.norm(fore)
            # The hand lies past the wrist; show it with a little of the forearm.
            start = W - fore * rng.uniform(0.1, 0.5)
            return _capsule(shape, start, W + fore * 0.55, length * 0.45)
        if part == "arm" and S is not None and E is not None and W is not None:
            return _capsule(shape, S + (E - S) * rng.uniform(0.0, 0.5), W + (W - E) * 0.5,
                            np.linalg.norm(E - S) * 0.4)
        if part == "leg" and K is not None and A is not None:
            return _capsule(shape, K + (A - K) * rng.uniform(-0.2, 0.4), A + (A - K) * 0.35,
                            np.linalg.norm(A - K) * 0.35)
    nose, ls, rs = _kp(person, NOSE), _kp(person, L_SH), _kp(person, R_SH)
    if part == "head" and nose is not None and ls is not None and rs is not None:
        width = np.linalg.norm(ls - rs)
        if width < 8:   # side-on: shoulders overlap, no width to size the head by
            return None
        m = np.zeros(shape, np.uint8)
        cv2.circle(m, tuple(int(v) for v in nose), int(width * 0.55), 255, -1)
        if rng.random() < 0.5:   # shoulders showing too
            cv2.line(m, tuple(int(v) for v in ls), tuple(int(v) for v in rs), 255, int(width * 0.35))
        return m
    lh, rh = _kp(person, L_HIP), _kp(person, R_HIP)
    if part == "upper_body" and ls is not None and rs is not None and lh is not None and rh is not None:
        top, bottom = (ls + rs) / 2, (lh + rh) / 2
        cut = top + (bottom - top) * rng.uniform(0.2, 0.7)
        # Everything on the head's side of a line across the torso.
        axis = (bottom - top) / (np.linalg.norm(bottom - top) + 1e-6)
        yy, xx = np.mgrid[:shape[0], :shape[1]]
        return ((((xx - cut[0]) * axis[0] + (yy - cut[1]) * axis[1]) < 0) * 255).astype(np.uint8)
    return None


def _ragged(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    """Roughens the cut edge so the body looks covered, not cropped by a ruler."""
    noise = np.random.default_rng(rng.randrange(1 << 30)).random(mask.shape).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), max(1.0, min(mask.shape) / 40))
    edge = cv2.GaussianBlur(mask.astype(np.float32) / 255, (0, 0), max(1.0, min(mask.shape) / 30))
    return ((edge + (noise - noise.mean()) * 2.0) > 0.5).astype(np.uint8) * 255


def _cutout(person: dict, img: np.ndarray, part: str, rng: random.Random):
    h, w = img.shape[:2]
    body = np.zeros((h, w), np.uint8)
    for poly in person["segmentation"]:
        cv2.fillPoly(body, [np.array(poly, np.int32).reshape(-1, 2)], 255)
    region = _part_region(person, part, (h, w), rng)
    if region is None:
        return None
    vis = cv2.bitwise_and(body, _ragged(region, rng))
    ys, xs = np.nonzero(vis)
    if len(xs) < 150:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    pad = 4
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    return img[y0:y1, x0:x1].copy(), vis[y0:y1, x0:x1].copy()


def _object_cutout(obj: dict, img: np.ndarray, rng: random.Random):
    """A whole decoy object, or (half the time) the part of it showing out of the rubble."""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for poly in obj["segmentation"]:
        cv2.fillPoly(mask, [np.array(poly, np.int32).reshape(-1, 2)], 255)
    ys, xs = np.nonzero(mask)
    if len(xs) < 150:
        return None
    if rng.random() < 0.5:
        # Cut along a random line through the object, as the body parts are cut.
        cx, cy = rng.uniform(xs.min(), xs.max()), rng.uniform(ys.min(), ys.max())
        a = rng.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[:h, :w]
        side = (((xx - cx) * math.cos(a) + (yy - cy) * math.sin(a)) < 0).astype(np.uint8) * 255
        mask = cv2.bitwise_and(mask, _ragged(side, rng))
        ys, xs = np.nonzero(mask)
        if len(xs) < 150:
            return None
    x0, x1, y0, y1 = max(0, xs.min() - 4), min(w, xs.max() + 5), max(0, ys.min() - 4), min(h, ys.max() + 5)
    return img[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1].copy()


def _scene(backgrounds: list[Path], rng: random.Random) -> np.ndarray:
    canvas = np.zeros((CANVAS, CANVAS, 3), np.uint8)
    for r in range(2):
        for c in range(2):
            bg = cv2.imread(str(rng.choice(backgrounds)))
            bh, bw = bg.shape[:2]
            s = TILE / min(bh, bw)
            bg = cv2.resize(bg, (max(TILE, round(bw * s)), max(TILE, round(bh * s))), interpolation=cv2.INTER_AREA)
            oy, ox = rng.randint(0, bg.shape[0] - TILE), rng.randint(0, bg.shape[1] - TILE)
            tile = bg[oy:oy + TILE, ox:ox + TILE]
            if rng.random() < 0.5:
                tile = cv2.flip(tile, rng.choice((0, 1, -1)))
            canvas[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE] = tile
    return canvas


def _paste(canvas: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, rng: random.Random, taken: list):
    # Seen from above, at any heading.
    angle = rng.uniform(0, 360)
    h, w = alpha.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    rgb = cv2.warpAffine(rgb, M, (nw, nh), flags=cv2.INTER_LINEAR)
    alpha = cv2.warpAffine(alpha, M, (nw, nh), flags=cv2.INTER_LINEAR)

    # Drone scale: a hand is a dozen pixels from altitude, a couple of hundred up close.
    target = math.exp(rng.uniform(math.log(12), math.log(170)))
    s = target / max(nw, nh)
    nw, nh = max(4, round(nw * s)), max(4, round(nh * s))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    rgb, alpha = cv2.resize(rgb, (nw, nh), interpolation=interp), cv2.resize(alpha, (nw, nh), interpolation=interp)
    if nw >= CANVAS or nh >= CANVAS:
        return None

    for _ in range(20):
        x, y = rng.randint(0, CANVAS - nw), rng.randint(0, CANVAS - nh)
        if all(x + nw < a or a2 < x or y + nh < b or b2 < y for a, b, a2, b2 in taken):
            break
    else:
        return None

    patch = canvas[y:y + nh, x:x + nw].astype(np.float32)
    person = rgb.astype(np.float32)
    # Dust and lighting: pull the person's colour toward the scene around it.
    pull = rng.uniform(0.1, 0.45)
    person = person * (1 - pull) + patch.mean(axis=(0, 1)) * pull
    if rng.random() < 0.5:
        person = person * (1 - 0.25) + 190 * 0.25 * rng.random()
    a = (alpha.astype(np.float32) / 255)
    # Rubble lying over part of what shows: a blob of the scene pasted back on top.
    if rng.random() < 0.4:
        blob = np.zeros((nh, nw), np.float32)
        cx, cy = rng.uniform(0, nw), rng.uniform(0, nh)
        cv2.ellipse(blob, (int(cx), int(cy)), (max(1, int(nw * rng.uniform(0.15, 0.4))),
                    max(1, int(nh * rng.uniform(0.15, 0.4)))), rng.uniform(0, 180), 0, 360, 1.0, -1)
        a = a * (1 - blob)
    a = cv2.GaussianBlur(a, (3, 3), 0) if min(nw, nh) > 8 else a
    canvas[y:y + nh, x:x + nw] = (patch * (1 - a[..., None]) + person * a[..., None]).clip(0, 255).astype(np.uint8)

    ys, xs = np.nonzero(a > 0.5)
    if len(xs) < 12:   # too little left to label honestly
        return None
    box = (x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1)
    taken.append(box)
    return box


def _split_backgrounds(seed: int) -> tuple[list[Path], list[Path]]:
    train, val = [], []
    for cls in SCENE_CLASSES:
        for f in sorted((AIDER / cls).glob("*")):
            # Stable by name, so re-running never moves a photo across the split.
            (val if int(hashlib.md5(f.name.encode()).hexdigest(), 16) % 100 < 15 else train).append(f)
    return train, val


def build(split: str, coco_split: str, n_images: int, backgrounds: list[Path], seed: int) -> None:
    rng = random.Random(seed)
    people = json.loads((RAW / f"people_{coco_split}.json").read_text())
    objects = json.loads((RAW / f"objects_{split}.json").read_text())
    img_dir, lbl_dir = OUT / "images" / split, OUT / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, np.ndarray] = {}

    def load(folder: str, file: str):
        if file not in cache:
            if len(cache) > 300:
                cache.clear()
            cache[file] = cv2.imread(str(RAW / folder / file))
        return cache[file]

    parts, weights = zip(*PARTS)
    counts = {p: 0 for p in parts}
    negatives = 0

    for i in range(n_images):
        canvas = _scene(backgrounds, rng)
        boxes = []
        n = 0 if rng.random() < 0.25 else rng.choice((1, 1, 1, 2, 2, 3))
        tries = 0
        while len(boxes) < n and tries < n * 6:
            tries += 1
            person = rng.choice(people)
            img = load(f"coco_{coco_split}", person["file"])
            if img is None:
                continue
            part = rng.choices(parts, weights)[0]
            cut = _cutout(person, img, part, rng)
            if cut is None:
                continue
            box = _paste(canvas, *cut, rng, boxes)
            if box:
                counts[part] += 1
        # Decoys: pasted exactly like the people, and never labelled.
        decoys: list = []
        for _ in range(rng.choice((0, 1, 1, 2, 2, 3, 4))):
            obj = rng.choice(objects)
            img = load("coco_objects", obj["file"])
            cut = _object_cutout(obj, img, rng) if img is not None else None
            if cut is not None:
                taken = boxes + decoys
                if _paste(canvas, *cut, rng, taken):
                    decoys.append(taken[-1])
        negatives += not boxes
        name = f"buried_{split}_{i:05d}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), canvas, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(70, 95)])
        (lbl_dir / f"{name}.txt").write_text("".join(
            f"0 {(x0 + x1) / 2 / CANVAS:.6f} {(y0 + y1) / 2 / CANVAS:.6f} {(x1 - x0) / CANVAS:.6f} {(y1 - y0) / CANVAS:.6f}\n"
            for x0, y0, x1, y1 in boxes))
        if i % 500 == 0:
            print(f"{split}: {i}/{n_images}")
    print(f"{split}: {n_images} images, {negatives} with no one, parts {counts}")


def add_real_negatives(split: str, n_visdrone: int, n_fire: int, seed: int) -> None:
    """Real photos with no buried person in them, copied in with empty labels."""
    rng = random.Random(seed)
    img_dir, lbl_dir = OUT / "images" / split, OUT / "labels" / split
    vd = sorted((API / f"data/small_person/images/{split}").glob("vd_*"))
    fire = sorted((API / f"data/fire/images/{split}").glob("*"))
    picked = rng.sample(vd, min(n_visdrone, len(vd))) + rng.sample(fire, min(n_fire, len(fire)))
    for f in picked:
        img = cv2.imread(str(f))
        if img is None:
            continue
        name = f"real_{f.stem}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), img)
        (lbl_dir / f"{name}.txt").write_text("")
    print(f"{split}: {len(picked)} real negatives")


SWIMMER_TEST_TILES = 600   # sds val tiles reserved for testing, never copied in


def swimmer_test_tiles() -> list[Path]:
    return sorted((API / "data/small_person/images/val").glob("sds_*"))[:SWIMMER_TEST_TILES]


def add_swimmers(split: str, n: int, seed: int) -> None:
    """Real partly submerged people, with their labels (already class 0)."""
    rng = random.Random(seed)
    tiles = sorted((API / f"data/small_person/images/{split}").glob("sds_*"))
    if split == "val":
        tiles = tiles[SWIMMER_TEST_TILES:]
    img_dir, lbl_dir = OUT / "images" / split, OUT / "labels" / split
    picked = rng.sample(tiles, min(n, len(tiles)))
    for f in picked:
        label = API / f"data/small_person/labels/{split}/{f.stem}.txt"
        img = cv2.imread(str(f))
        if img is None or not label.exists():
            continue
        cv2.imwrite(str(img_dir / f"swim_{f.stem}.jpg"), img)
        (lbl_dir / f"swim_{f.stem}.txt").write_text(label.read_text())
    print(f"{split}: {len(picked)} swimmer tiles")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("fetch", "fetch-objects", "build", "swimmers"))
    ap.add_argument("--train-images", type=int, default=7000)
    ap.add_argument("--val-images", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    if args.stage == "fetch":
        fetch("train", 3500, args.seed)
        fetch("val", 500, args.seed)
        return
    if args.stage == "fetch-objects":
        fetch_objects(2500, args.seed)
        return
    if args.stage == "swimmers":   # adds to an existing build
        add_swimmers("train", 3000, args.seed)
        add_swimmers("val", 300, args.seed + 1)
        return
    train_bg, val_bg = _split_backgrounds(args.seed)
    print(f"backgrounds: {len(train_bg)} train, {len(val_bg)} val")
    build("train", "train", args.train_images, train_bg, args.seed)
    build("val", "val", args.val_images, val_bg, args.seed + 1)
    add_real_negatives("train", 2000, 1000, args.seed)
    add_real_negatives("val", 200, 100, args.seed + 1)
    add_swimmers("train", 3000, args.seed)
    add_swimmers("val", 300, args.seed + 1)
    (OUT / "buried.yaml").write_text(
        f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/val\nnc: 1\nnames:\n  0: buried_person\n")


if __name__ == "__main__":
    main()
