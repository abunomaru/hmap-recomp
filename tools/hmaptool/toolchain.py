"""External tools: pinned releases, downloaded and checksum-verified on demand.

  nodtool         disc extraction (ISO/WBFS/RVZ/WIA/CISO)   github.com/encounter/nod
  dtk             DOL analysis + function boundaries         github.com/encounter/decomp-toolkit

Set HMAP_NODTOOL / HMAP_DTK to use your own builds instead.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "tools" / "bin"

# SHA-256 of the release assets, recorded when the versions were pinned.
TOOLS = {
    "nodtool": {
        "version": "v2.0.0-alpha.12",
        "url": "https://github.com/encounter/nod/releases/download/{version}/nodtool-{platform}",
        "env": "HMAP_NODTOOL",
        "sha256": {
            "linux-x86_64": "ee8345c004248eb82a86dd0c6068e0fcf3dc75baf68d18fe949bf4589822f5a5",
            "linux-aarch64": "33e801c0e4aee7e714ad84e89521f50e2f79005571b9d4779b695e44ea21ff99",
            "macos-x86_64": "d1e7ba904c2e557fafbd3bf2d9b75a7901a2bf1568c0fb3a505fca0f30b0a833",
            "macos-arm64": "524c0b27c0c4289e435df4474d288ea7e63d6a34814cc7c650231688dd1e53b4",
            "windows-x86_64.exe": "f65de62c44f0ad5d179eff85bd1e92099713ffacbf717f651fb761129a25c7bc",
            "windows-arm64.exe": "463d5f7fd7d753fde05c6772f8114ec6f8ab6eaf054790ed9b95a89ef8c63526",
        },
    },
    "dtk": {
        "version": "v1.8.4",
        "url": "https://github.com/encounter/decomp-toolkit/releases/download/{version}/dtk-{platform}",
        "env": "HMAP_DTK",
        "sha256": {
            "linux-x86_64": "7c86b1994401bde0cad1d308e6c04cccb65e85453ccc5062ac12baab3b03d320",
            "linux-aarch64": "889a551d57916772f21a29c997579e0508f268c96bcbc946a0a66bff029cf97c",
            "macos-x86_64": "84bcab745a070bb970cf4bc0d69ddce9f6a58d5de257999ccc8adfa1567d17c9",
            "macos-arm64": "5ba1fd76adf937847277a1ebe2238b698df0020c3dbbde23ecb126f00fb10353",
            "windows-x86_64.exe": "6a693e95aa4d30acccc673343302a4abdfa3146bd0fb15cb1a2bce924cbc782a",
            "windows-arm64.exe": "6d2567f6017f6add6e493f86feb3c4fd7064a17ca7f972f36f29aa3af3488871",
        },
    },
    "xdelta3": {
        # Windows: the official 3.0.11 build (zip). Linux/macOS: the system package (apt/brew).
        "version": "v3.0.11",
        "url": "https://github.com/jmacd/xdelta-gpl/releases/download/{version}/xdelta3-3.0.11-x86_64.exe.zip",
        "env": "HMAP_XDELTA3",
        "zip_member": "xdelta3-3.0.11-x86_64.exe",
        "sha256": {
            "windows-x86_64.exe": "eca90daab9cd8388ffa17fb4d6808bb0616cc5d37a7682126485dba1c79f86bf",
        },
    },
}


def host_platform() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64" if machine in ("x86_64", "amd64") else machine
    if sys.platform.startswith("linux"):
        return f"linux-{'aarch64' if arch == 'arm64' else arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    if sys.platform == "win32":
        return f"windows-{arch}.exe"
    raise RuntimeError(f"unsupported platform {sys.platform}/{machine}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_path(name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return BIN / f"{name}{suffix}"


def find(name: str) -> Path | None:
    spec = TOOLS[name]
    override = os.environ.get(spec["env"])
    if override:
        return Path(override)
    local = local_path(name)
    if local.exists():
        return local
    on_path = shutil.which(name)
    return Path(on_path) if on_path else None


def install(name: str, force: bool = False) -> Path:
    spec = TOOLS[name]
    target = local_path(name)
    plat = host_platform()
    expected = spec["sha256"].get(plat)
    if expected is None:
        hint = " (install it with your package manager, e.g. apt install xdelta3)" if name == "xdelta3" else ""
        raise RuntimeError(f"no pinned {name} build for {plat}{hint}; or set {spec['env']}")
    marker = target.with_suffix(target.suffix + ".sha256")
    if target.exists() and not force and (sha256(target) == expected or (marker.exists() and marker.read_text().strip() == expected)):
        return target
    url = spec["url"].format(version=spec["version"], platform=plat)
    BIN.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    print(f"downloading {name} {spec['version']} ({plat})")
    with urllib.request.urlopen(url) as response, open(partial, "wb") as out:
        shutil.copyfileobj(response, out)
    actual = sha256(partial)
    if actual != expected:
        partial.unlink()
        raise RuntimeError(f"{name}: checksum mismatch (got {actual}, expected {expected})")
    if spec.get("zip_member"):
        import zipfile
        with zipfile.ZipFile(partial) as archive:
            target.write_bytes(archive.read(spec["zip_member"]))
        partial.unlink()
    else:
        partial.replace(target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    marker.write_text(expected + "\n")
    return target


def require(name: str) -> Path:
    found = find(name)
    if found:
        return found
    return install(name)
