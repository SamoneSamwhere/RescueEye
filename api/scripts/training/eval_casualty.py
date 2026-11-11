"""
Replays real clips through the full live path (tracker, stillness, casualty
gate) at the /detect cadence, with and without the casualty-posture model, and
counts the casualties raised. The camera view is set per clip, as the operator
would: straight down for rescue-patrol, angled for the others.

    .venv/Scripts/python.exe scripts/training/eval_casualty.py [--model path.onnx]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_buried import replay  # noqa: E402

CLIPS = {
    # name: (path, camera pitch the operator would set, people really down)
    "rescue-patrol (nadir, 1 lying)": (API / "data/media/210f3df0a39f_rescue-patrol.mp4", -90, True),
    "rescue-patrol, set to angled": (API / "data/media/210f3df0a39f_rescue-patrol.mp4", -35, True),
    "flood roof (standing, kneeling)": (API / "data/media/7aed7e39637d_People_stranded_in_floodwaters_d2ea9e12.mp4", -35, False),
    "demo_feed7 (firefighters)": (API / "data/media/baa22505eb23_demo_feed7.mp4", -35, False),
    "DEMO_FEED10": (API / "data/media/4089f8f8fd08_DEMO_FEED10.mp4", -35, False),
    "vtest (walkers)": (Path("C:/RescueEyeData/evalclips/vtest.avi"), -35, False),
}


def run(label: str) -> None:
    from routers import detect
    from services import casualty
    print(f"\n{label}")
    for name, (path, pitch, _) in CLIPS.items():
        if not path.exists():
            continue
        detect.DEFAULT_GIMBAL_PITCH_DEG = pitch
        clock = [0.0]
        casualty.time.monotonic = lambda: clock[0]
        key = f"eval-{name}"
        stream = detect.stream_state(key)
        frames, boxes, tracks, reasons = 0, 0, set(), Counter()
        for t, bgr in replay(path, max_frames=40):
            clock[0] = 1000.0 + t
            ok, jpg = cv2.imencode(".jpg", bgr)
            r = detect._analyse(jpg.tobytes(), stream, False, None)
            frames += 1
            for d in r["casualties"]:
                boxes += 1
                tracks.add(d.get("track_id"))
                reasons.update(x for x in d.get("casualty_reasons", []) if x.startswith("posture") or x == "partly_buried")
        print(f"  {name:34s} {frames:3d} frames: {boxes:3d} casualty boxes, {len(tracks)} tracks  {dict(reasons)}")
        detect.drop_stream(key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=API / "runs/candidates/casualty_v3_544x960_fp16.onnx")
    ap.add_argument("--victim", type=Path, help="candidate person detector (ONNX); runs the live setup only")
    args = ap.parse_args()
    from services import yolo_model
    yolo_model.load_all()
    if args.victim:
        import onnxruntime as ort
        yolo_model._victim_ort_session = ort.InferenceSession(
            str(args.victim), providers=["DmlExecutionProvider", "CPUExecutionProvider"])
        run(f"Live setup (installed posture model) with person detector {args.victim.name}")
        return
    yolo_model._casualty_ort_session = None
    run("Without the casualty-posture model (keypoint posture only)")
    yolo_model._load_casualty_ort(str(args.model))
    run(f"With {args.model.name}")


if __name__ == "__main__":
    main()
