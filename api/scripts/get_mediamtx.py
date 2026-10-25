"""
Downloads MediaMTX, the always-on drone video receiver (services/drone_ingest.py),
into api/bin/mediamtx/. The download is checked against the release's published
SHA-256 before anything is unpacked.

    cd api
    .venv/Scripts/python.exe -m scripts.get_mediamtx
"""
from __future__ import annotations

import hashlib
import io
import platform
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "v1.21.2"
BASE = f"https://github.com/bluenviron/mediamtx/releases/download/{VERSION}"
DEST = Path(__file__).resolve().parent.parent / "bin" / "mediamtx"


def asset_name() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    if sys.platform == "win32":
        return f"mediamtx_{VERSION}_windows_{arch}.zip"
    system = "darwin" if sys.platform == "darwin" else "linux"
    return f"mediamtx_{VERSION}_{system}_{arch}.tar.gz"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as res:
        return res.read()


def main() -> int:
    name = asset_name()
    print(f"Downloading {name} ...")
    data = fetch(f"{BASE}/{name}")
    sums = fetch(f"{BASE}/checksums.sha256").decode()
    expected = next((line.split()[0] for line in sums.splitlines() if line.strip().endswith(name)), None)
    actual = hashlib.sha256(data).hexdigest()
    if expected is None or expected.lower() != actual:
        print(f"Checksum mismatch for {name} - not installing.")
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    binary = "mediamtx.exe" if sys.platform == "win32" else "mediamtx"
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            (DEST / binary).write_bytes(z.read(binary))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            member = t.extractfile(binary)
            if member is None:
                print("Binary not found in the archive.")
                return 1
            (DEST / binary).write_bytes(member.read())
            (DEST / binary).chmod(0o755)
    print(f"Installed {DEST / binary}. Restart the API to start drone ingest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
