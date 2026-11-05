"""
How the partly-buried-person detector behaves on real footage, run the way the
live API runs it (DirectML, with the body detectors alongside).

The synthetic val split says whether it finds composited body parts. This
says what it costs on real video with no buried people in it: every box that
survives here would be raised as a casualty. It also counts boxes that land
on whole people the body detectors missed, and times the extra pass.

Run in the API venv:
    .venv/Scripts/python.exe scripts/training/eval_buried.py --model runs/candidates/buried_736x1280_fp16.onnx
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
CLIPS = {
    "rescue-patrol (nadir, 1 lying casualty + walkers)": API / "data/media/210f3df0a39f_rescue-patrol.mp4",
    "demo_feed7 (burning barn)": API / "data/media/e448df79167e_demo_feed7.mp4",
    # (demo_feed8 in the media library is the same file as rescue-patrol.)
    "DEMO_FEED10": API / "data/media/4089f8f8fd08_DEMO_FEED10.mp4",
    "demo_feed (flood, boat)": API / "data/media/7333187ceb29_demo_feed.mp4",
    "vtest (pedestrians walking)": Path("C:/RescueEyeData/evalclips/vtest.avi"),
}
UAV_SAR = API / "data/raw/downloads/uav_sar"
THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)


def frames_of(path: Path, n: int):
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or n
    for idx in np.linspace(0, total - 1, n).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, bgr = cap.read()
        if ok:
            # The live stream is served at 1280 wide.
            if bgr.shape[1] > 1280:
                bgr = cv2.resize(bgr, (1280, round(bgr.shape[0] * 1280 / bgr.shape[1])), interpolation=cv2.INTER_AREA)
            yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    cap.release()


def replay(path: Path, every_s: float = 3.0, max_frames: int = 80):
    """(video time, frame) at the live /detect cadence, in order, so tracking works as it does live."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, round(fps * every_s))
    idx = 0
    for _ in range(max_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, bgr = cap.read()
        if not ok:
            break
        if bgr.shape[1] > 1280:
            bgr = cv2.resize(bgr, (1280, round(bgr.shape[0] * 1280 / bgr.shape[1])), interpolation=cv2.INTER_AREA)
        yield idx / fps, bgr
        idx += step
    cap.release()


def pipeline(conf: float) -> None:
    """Each clip through the full live path (tracker, casualty gate) at one frame per 3 s."""
    from routers import detect
    from services import casualty
    detect.BURIED_CONF = conf
    print(f"\nFull pipeline, buried conf >= {conf}: casualties raised from a partly buried box")
    for name, path in CLIPS.items():
        if not path.exists():
            continue
        clock = [0.0]
        casualty.time.monotonic = lambda: clock[0]
        stream = detect.stream_state(f"eval-{name}")
        frames = alerts = 0
        tracks: set[int] = set()
        for t, bgr in replay(path):
            clock[0] = 1000.0 + t
            ok, jpg = cv2.imencode(".jpg", bgr)
            r = detect._analyse(jpg.tobytes(), stream, False, None)
            frames += 1
            for d in r["casualties"]:
                if "partly_buried" in d.get("casualty_reasons", []):
                    alerts += 1
                    tracks.add(d.get("track_id"))
        print(f"  {name}: {frames} frames, {alerts} partly-buried casualty boxes, {len(tracks)} distinct tracks")
        detect.drop_stream(f"eval-{name}")


def swimmers() -> None:
    """
    Recall on real partly hidden people: SeaDronesSee swimmers, only head and
    arms above water, in the val tiles prepare_buried_dataset.py never copies in.
    """
    from routers import detect
    from scripts.training.prepare_buried_dataset import swimmer_test_tiles
    detect.BURIED_CONF = 0.1
    preds: list[tuple[float, bool]] = []
    n_gt = 0
    tiles = swimmer_test_tiles()
    for f in tiles:
        img = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]
        gt = []
        for line in (f.parent.parent.parent / "labels/val" / f"{f.stem}.txt").read_text().splitlines():
            _, x, y, bw, bh = map(float, line.split())
            gt.append([(x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h])
        n_gt += len(gt)
        used: set[int] = set()
        for d in sorted(detect._run_buried(img), key=lambda d: -d["confidence"]):
            b = d["bbox"]
            box = [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]]
            best, bi = 0.0, -1
            for i, g in enumerate(gt):
                ix = max(0, min(box[2], g[2]) - max(box[0], g[0]))
                iy = max(0, min(box[3], g[3]) - max(box[1], g[1]))
                union = (box[2] - box[0]) * (box[3] - box[1]) + (g[2] - g[0]) * (g[3] - g[1]) - ix * iy
                if i not in used and union > 0 and ix * iy / union > best:
                    best, bi = ix * iy / union, i
            if best >= 0.3:
                used.add(bi)
            preds.append((d["confidence"], best >= 0.3))
    print(f"\nReal swimmers (SeaDronesSee, held out): {len(tiles)} tiles, {n_gt} people")
    for t in (0.3, 0.5):
        hits = [p for p in preds if p[0] >= t]
        tp = sum(p[1] for p in hits)
        print(f"  conf>={t}: found {tp}/{n_gt} ({tp / max(n_gt, 1):.0%}), {len(hits) - tp} other boxes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pipeline", type=float, metavar="CONF",
                    help="also replay each clip through the full live path at this buried conf")
    ap.add_argument("--frames", type=int, default=60, help="frames sampled per clip")
    ap.add_argument("--crops", help="folder to save crops of surviving boxes, for a look by eye")
    args = ap.parse_args()

    from services import yolo_model
    yolo_model.load_all()
    yolo_model._load_buried_ort(args.model)
    from routers import detect
    detect.BURIED_CONF = min(THRESHOLDS)

    crops_dir = Path(args.crops) if args.crops else None
    if crops_dir:
        crops_dir.mkdir(parents=True, exist_ok=True)

    sources = {name: frames_of(p, args.frames) for name, p in CLIPS.items() if p.exists()}
    sar = sorted(UAV_SAR.glob("**/frames/*.jpg"))[:args.frames]
    sources["UAV-SAR (wilderness, whole people)"] = (detect._decode_jpeg(f.read_bytes()) for f in sar)

    times: list[float] = []
    for name, frames in sources.items():
        raw = {t: 0 for t in THRESHOLDS}
        kept = {t: 0 for t in THRESHOLDS}
        n = 0
        for frame in frames:
            n += 1
            bodies, _, _ = detect._run_victim(frame)
            t0 = time.perf_counter()
            parts = detect._run_buried(frame)
            times.append((time.perf_counter() - t0) * 1000)
            survivors = detect._partly_buried(parts, bodies)
            for t in THRESHOLDS:
                raw[t] += sum(p["confidence"] >= t for p in parts)
                kept[t] += sum(p["confidence"] >= t for p in survivors)
            if crops_dir:
                for i, p in enumerate(survivors):
                    b = p["bbox"]; pad = 30
                    crop = frame[max(0, b["y"] - pad):b["y"] + b["h"] + pad, max(0, b["x"] - pad):b["x"] + b["w"] + pad]
                    tag = name.split()[0]
                    cv2.imwrite(str(crops_dir / f"{tag}_{n:03d}_{i}_{p['confidence']:.2f}.jpg"),
                                cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        print(f"\n{name}: {n} frames")
        for t in THRESHOLDS:
            print(f"  conf>={t}: {raw[t]:4d} boxes, {kept[t]:4d} not on a seen body "
                  f"({kept[t] / max(n, 1):.2f}/frame) -> would be raised as casualties")
    if times:
        print(f"\nextra pass: median {np.median(times):.0f} ms, p90 {np.percentile(times, 90):.0f} ms "
              f"over {len(times)} frames")
    swimmers()
    if args.pipeline is not None:
        pipeline(args.pipeline)


if __name__ == "__main__":
    main()
