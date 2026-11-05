#!/usr/bin/env python3
"""Download the pinned Lidarr plugin-capable binaries that LidarrReferences.targets
references, into PLUGIN/_temp/lidarr/<version>/.

The asset name follows Lidarr's develop-release scheme: Lidarr.develop.<ver>.<rid>.
Published SHA-256 digests are checked so libraries cannot be tampered with in cache.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import PurePosixPath

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "3.1.3.4968"

# Published digests for https://github.com/Lidarr/Lidarr/releases/tag/v3.1.3.4968
SHA256 = {
    "linux-core-x64": "8e14e5a2e9a89f7cb7a281434a7484d1b9632fc52f2cc06bb03a5102714dddd1",
    "linux-core-arm64": "e5c89688850885bc7becd779e668bbf423ca3fe37986704b70d9e9b217ea9e44",
    "osx-core-x64": "3143137d84cf8a06b4efda544af88c360247256993d05af05bb7a725ef3e96ed",
    "osx-core-arm64": "7fbebd4e5a5b01a8489a5dc733d7bb40c6881a42ccc87d32ace72640257bb725",
    "windows-core-x64": "4bd64517008f319d37d4d4585146a474ac2ff2d0183b1b751661f89f2b434280",
}

REQUIRED = {
    "Lidarr.Core.dll", "Lidarr.Common.dll", "Lidarr.Http.dll", "Lidarr.Api.V1.dll",
    "NLog.dll", "FluentValidation.dll", "Newtonsoft.Json.dll", "System.IO.Abstractions.dll",
}


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_assemblies(archive: str, destination: str) -> int:
    """Copy only top-level Lidarr/*.dll assemblies into destination."""
    found = set()
    if archive.endswith(".zip"):
        bundle = zipfile.ZipFile(archive)
        handles = [(PurePosixPath(m.filename), m) for m in bundle.infolist()]
    else:
        tarball = tarfile.open(archive, "r:gz")
        handles = [(PurePosixPath(m.name), m) for m in tarball]  # type: ignore[assignment]

    for path, member in handles:
        if len(path.parts) != 2 or path.parts[0] != "Lidarr" or path.suffix != ".dll":
            continue
        if path.name in found:
            raise ValueError(f"Duplicate assembly: {path}")
        if archive.endswith(".zip"):
            if member.is_dir() or member.file_size > 100 * 1024 * 1024:
                raise ValueError(f"Invalid or oversized assembly: {path}")
            with bundle.open(member) as src, open(os.path.join(destination, path.name), "wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            if not member.isfile() or member.size > 100 * 1024 * 1024:
                raise ValueError(f"Invalid or oversized assembly: {path}")
            with tarball.extractfile(member) as src, open(os.path.join(destination, path.name), "wb") as dst:
                shutil.copyfileobj(src, dst)
        found.add(path.name)

    missing = REQUIRED - found
    if missing:
        raise ValueError(f"Required Lidarr assemblies missing: {', '.join(sorted(missing))}")
    return len(found)


def prepare() -> int:
    system = {"Darwin": "osx", "Linux": "linux", "Windows": "windows"}.get(_system())
    machine = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(_machine(), "")
    rid = f"{system}-core-{machine}"
    if rid not in SHA256:
        print(f"[prepare] unsupported host: {rid}")
        return 1

    cache = os.path.join(ROOT, "_temp", "lidarr")
    os.makedirs(cache, exist_ok=True)
    suffix = ".zip" if rid.startswith("windows-") else ".tar.gz"
    name = f"Lidarr.develop.{VERSION}.{rid}{suffix}"
    url = f"https://github.com/Lidarr/Lidarr/releases/download/v{VERSION}/{name}"
    archive = os.path.join(cache, name)

    if not os.path.exists(archive):
        print(f"[prepare] downloading {url}", flush=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            download = os.path.join(tmp, name)
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Lidarr.Plugin.YoutubeMusic"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(download, "wb") as dst:
                shutil.copyfileobj(resp, dst)
            if sha256_of(download) != SHA256[rid]:
                raise ValueError("SHA-256 mismatch for the downloaded Lidarr archive")
            shutil.move(download, archive)

    if sha256_of(archive) != SHA256[rid]:
        raise ValueError("SHA-256 mismatch for the cached Lidarr archive")

    destination = os.path.join(cache, VERSION)
    if os.path.islink(destination):
        raise ValueError("Refusing to replace a symlink at the reference directory")
    staged = tempfile.mkdtemp(dir=cache)
    try:
        count = extract_assemblies(archive, staged)
        if os.path.exists(destination):
            shutil.rmtree(destination)
        os.replace(staged, destination)
    finally:
        if os.path.exists(staged):
            shutil.rmtree(staged)
    print(f"[prepare] extracted {count} verified Lidarr {VERSION} assemblies to {destination}")
    return 0


def _system() -> str:
    import platform
    return platform.system()


def _machine() -> str:
    import platform
    return platform.machine()


if __name__ == "__main__":
    try:
        sys.exit(prepare())
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"[prepare] failed: {exc}", file=sys.stderr)
        sys.exit(1)