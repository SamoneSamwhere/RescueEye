"""
How well each posture signal separates lying from upright people under an
angled camera: the keypoint torso angle vs the casualty-posture model, on
Okutama-Action's test videos (filmed at 45-90 degrees, never trained on).
For every labelled person the person detector finds, both readings are taken
the way the live gate takes them.

    YOLO_AUTOINSTALL=false .venv/Scripts/python.exe scripts/training/eval_posture_signal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
DATA = Path("C:/RescueEyeData/casualty")
PITCH = -35.0
# Posture alone must reach this to raise a casualty (CASUALTY_MIN_SCORE / 0.8);
# with a full stillness window, 0.25 is enough.
ALONE, WITH_STILLNESS = 0.69, 0.25


def main() -> None:
    from routers import detect
    from services import casualty, yolo_model
    yolo_model.load_all()
    yolo_model._load_casualty_ort(str(API / "runs/candidates/casualty_v3_544x960_fp16.onnx"))
    rows = []   # (truly down, keypoint posture or None, model down or None)
    for img in sorted((DATA / "images/test").glob("ok_*.jpg"))[::2]:
        frame = cv2.imread(str(img))
        h, w = frame.shape[:2]
        dets, _, poses = detect._run_victim(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        model = detect._run_posture_model(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        for line in (DATA / "labels/test" / f"{img.stem}.txt").read_text().splitlines():
            c, x, y, bw, bh = map(float, line.split())
            gt = {"x": (x - bw / 2) * w, "y": (y - bh / 2) * h, "w": bw * w, "h": bh * h}
            det = max(dets, key=lambda d: detect._iou(gt, d["bbox"]), default=None)
            if det is None or detect._iou(gt, det["bbox"]) < 0.3:
                continue
            kp = detect._keypoints_for(det["bbox"], poses)
            kp_post = casualty.posture_from_keypoints(kp, det["bbox"], PITCH)[0] if kp is not None else None
            rows.append((int(c) == 1, kp_post, detect._model_down_for(det["bbox"], model)))
    for label, idx in (("keypoint torso angle", 1), ("casualty-posture model", 2)):
        print(f"\n{label}:")
        for truth, name in ((True, "lying"), (False, "upright")):
            sub = [r for r in rows if r[0] == truth]
            have = [r[idx] for r in sub if r[idx] is not None]
            alone = sum(v >= ALONE for v in have)
            still = sum(v >= WITH_STILLNESS for v in have)
            print(f"  {name:8s} {len(sub):5d} found by the detector, {len(have):5d} with a reading: "
                  f"{alone} ({100 * alone / max(1, len(sub)):.0f}%) >= {ALONE} alone, "
                  f"{still} ({100 * still / max(1, len(sub)):.0f}%) >= {WITH_STILLNESS} with stillness")


if __name__ == "__main__":
    main()
