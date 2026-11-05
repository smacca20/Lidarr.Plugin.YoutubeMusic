#!/usr/bin/env python3
"""Download the pinned Lidarr plugin-capable binaries that LidarrReferences.targets
references, into PLUGIN/_temp/lidarr/<version>/.

Adjust LIDARR_VERSION / the artifact layout if the release naming changes.
"""
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIDARR_VERSION = "3.1.3.4968"

NEEDED_DLLS = [
    "Lidarr.Core.dll", "Lidarr.Common.dll", "Lidarr.Http.dll",
    "Lidarr.Api.V1.dll", "NLog.dll", "FluentValidation.dll",
    "Newtonsoft.Json.dll", "System.IO.Abstractions.dll",
]


def download(url: str, dest: str) -> None:
    print(f"[prepare] downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "lidarr-plugin-builder"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as fh:
        fh.write(resp.read())


def prepare() -> int:
    out_dir = os.path.join(ROOT, "_temp", "lidarr", LIDARR_VERSION)
    if all(os.path.exists(os.path.join(out_dir, d)) for d in NEEDED_DLLS):
        print(f"[prepare] binaries already present in {out_dir}")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    archive_url = (
        "https://github.com/Lidarr/Lidarr/releases/download/"
        f"v{LIDARR_VERSION}/Lidarr.{LIDARR_VERSION}.linux-core-x64.tar.gz"
    )
    tmp = os.path.join(ROOT, "_temp", "archive.tar.gz")
    try:
        download(archive_url, tmp)
        with tarfile.open(tmp, "r:*") as tf:
            members = [m for m in tf.getmembers() if os.path.basename(m.name) in NEEDED_DLLS]
            for m in members:
                fh = tf.extractfile(m)
                if fh is None:
                    continue
                with open(os.path.join(out_dir, os.path.basename(m.name)), "wb") as o:
                    o.write(fh.read())
                print(f"[prepare] extracted {os.path.basename(m.name)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[prepare] WARNING: could not fetch the standard archive ({exc}).")
        print("[prepare] Download Lidarr development/nightly binaries manually into "
              f"{out_dir} (need: {', '.join(NEEDED_DLLS)}), or correct the URL in "
              "scripts/prepare-lidarr.py.")
        return 1

    missing = [d for d in NEEDED_DLLS if not os.path.exists(os.path.join(out_dir, d))]
    if missing:
        print(f"[prepare] WARNING: missing after extraction: {missing}")
        return 1
    print("[prepare] Lidarr reference binaries ready.")
    return 0


if __name__ == "__main__":
    sys.exit(prepare())