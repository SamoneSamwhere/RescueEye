"""
Real aerial frames of people lying down, relabelled for the person detector.

The person (victim) detector finds only about a quarter of the lying people in
Okutama-Action under an angled camera, and the casualty-posture model can
only judge the people it finds. Okutama's frames are real drone footage with
both upright and lying people labelled (prepared earlier into
C:/RescueEyeData/casualty by prepare_casualty_dataset.py, classes
upright/down/partial). Here every Okutama box becomes class 0 "person", so the
detector learns that a body lying on the ground is a person too.

Only the Okutama frames ("ok_" prefix) are used. The VisDrone frames in that
folder are already in data/small_person, and the pasted "buried" composites
taught earlier models to find "anything pasted" - not wanted here.

Images are hard-linked (same drive, no extra space); labels are rewritten.
Okutama's test split is kept out of training: it is the before/after test.

    .venv-train/Scripts/python.exe scripts/training/prepare_lying_person.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

SRC = Path("C:/RescueEyeData/casualty")
DST = Path("C:/RescueEyeData/person_lying")
API = Path(__file__).resolve().parents[2]
SMALL = API / "data/small_person"
YAML = API / "data/small_person_lying.yaml"


def main() -> None:
    for split in ("train", "val", "test"):
        (DST / "images" / split).mkdir(parents=True, exist_ok=True)
        (DST / "labels" / split).mkdir(parents=True, exist_ok=True)
        n = boxes = 0
        for label in sorted((SRC / "labels" / split).glob("ok_*.txt")):
            images = list((SRC / "images" / split).glob(label.stem + ".*"))
            if not images:
                continue
            img = images[0]
            out_img = DST / "images" / split / img.name
            if not out_img.exists():
                try:
                    os.link(img, out_img)
                except OSError:
                    shutil.copy2(img, out_img)
            lines = []
            for line in label.read_text().splitlines():
                parts = line.split()
                if len(parts) == 5:
                    lines.append("0 " + " ".join(parts[1:]))
            (DST / "labels" / split / label.name).write_text("\n".join(lines) + ("\n" if lines else ""))
            n += 1
            boxes += len(lines)
        print(f"{split}: {n} frames, {boxes} person boxes")

    YAML.write_text(
        "# small_person + real lying people (Okutama). Built by prepare_lying_person.py.\n"
        f"train:\n  - {(SMALL / 'images/train').as_posix()}\n  - {(DST / 'images/train').as_posix()}\n"
        f"val:\n  - {(SMALL / 'images/val').as_posix()}\n  - {(DST / 'images/val').as_posix()}\n"
        "nc: 1\nnames:\n  0: person\n"
    )
    print("Wrote", YAML)


if __name__ == "__main__":
    main()
