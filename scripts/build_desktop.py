"""Build a local macOS app from the locked environment, with notices and a file manifest."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def notices(destination):
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda d: d.name.lower()):
        metadata = distribution.metadata
        name = metadata["Name"]
        copied = []
        for file in distribution.files or []:
            # Preserve upstream licence/notice files as supplied, including nested licence dirs.
            if any("license" in p.lower() or p.lower() in {"copying", "notice", "authors"}
                   for p in file.parts):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = destination / name / Path(*[p for p in file.parts if p != ".."])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    copied.append(str(target.relative_to(destination)))
        inventory.append({
            "name": name, "version": distribution.version,
            "license": metadata.get("License-Expression") or metadata.get("License", ""),
            "license_classifiers": [c for c in metadata.get_all("Classifier", [])
                                    if c.startswith("License ::")],
            "notices": copied,
        })
    shutil.copyfile(ROOT / "LICENSE", destination / "Mashi-LICENSE.txt")
    # CPython ships its own PSF and incorporated third-party notices.
    candidates = [Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
                  / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"]
    python_license = next((p for p in candidates if p.is_file()), None)
    if python_license is None:
        raise RuntimeError("Cannot locate CPython LICENSE.txt; do not build without its notices")
    shutil.copyfile(python_license, destination / "Python-LICENSE.txt")
    (destination / "inventory.json").write_text(json.dumps({
        "scope": "All Python distributions in the locked build environment, a superset of runtime",
        "python": platform.python_version(), "architecture": platform.machine(),
        "packages": inventory,
        "external": ["macOS Cocoa/WebKit (OS provided)", "Optional local Tesseract (not bundled)"],
        "assets": "Mashi static UI only. No model weights, training fonts or OCR language data.",
    }, indent=2) + "\n", encoding="utf-8")


def manifest(app):
    files = []
    for path in sorted(app.rglob("*")):
        relative = str(path.relative_to(app))
        if path.is_symlink():
            files.append({"path": relative, "symlink": str(path.readlink())})
        elif path.is_file():
            files.append({"path": relative, "size": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    encoded = json.dumps(files, indent=2) + "\n"
    target = app.parent / "Mashi-files.json"
    target.write_text(encoded, encoding="utf-8")
    return hashlib.sha256(encoded.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("Build on macOS; PyInstaller does not cross-compile a Mac app")
    destination = ROOT / "build" / "desktop-notices"
    if destination.exists():
        shutil.rmtree(destination)
    notices(destination)
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "build" / "pyinstaller-cache"))
    output = args.output_dir.expanduser().resolve()
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(output), "--workpath", str(ROOT / "build" / "pyinstaller"),
        str(ROOT / "desktop" / "Mashi.spec"),
    ], cwd=ROOT, check=True, env=environment)
    app = output / "Mashi.app"
    verified = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True, text=True,
    )
    if verified.returncode:
        raise SystemExit(
            "Local ad-hoc signature verification failed. Build with --output-dir in a local "
            "folder outside cloud sync (for example /tmp/mashi-desktop-dist). "
            "No security metadata was changed.\n" + verified.stderr
        )
    digest = manifest(app)
    print(f"Built {app}\nSHA256 of Mashi-files.json: {digest}")


if __name__ == "__main__":
    main()
