"""Explicitly download the official pinned Malayalam Tesseract data, with hash checks."""

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
ROOT = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{COMMIT}/"
ASSETS = {
    "mal.traineddata": "bd05cbf1b197e7810d2903419aedb06f9ef77bfedf50b358673c1d18d707cdb4",
    "LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
}
MAX_ASSET = 8 * 1024 * 1024


def managed_directory(data_root):
    return Path(data_root) / "ocr" / ("tessdata-" + COMMIT[:12])


def manifest():
    return {
        "repository": "tesseract-ocr/tessdata_fast",
        "commit": COMMIT,
        "license": "Apache-2.0",
        "language": "mal",
        "assets": [
            {"file": name, "url": ROOT + name, "sha256": digest} for name, digest in ASSETS.items()
        ],
    }


def verified(directory):
    """Bound reads and reject links; never repair or overwrite existing user data."""
    directory = Path(directory)
    try:
        if directory.is_symlink() or not directory.is_dir():
            return False
        for name, expected in ASSETS.items():
            path = directory / name
            if path.is_symlink() or not path.is_file():
                return False
            with path.open("rb") as source:
                data = source.read(MAX_ASSET + 1)
            if len(data) > MAX_ASSET or hashlib.sha256(data).hexdigest() != expected:
                return False
        return True
    except OSError:
        return False


def install_data(output):
    """Publish a complete verified directory once. Failure leaves prior data intact."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        if verified(output):
            return manifest()
        raise ValueError("Existing recognition data could not be verified. See recognition help.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mal-setup-", dir=output.parent) as folder:
        staged = Path(folder) / "data"
        staged.mkdir(mode=0o700)
        record = manifest()
        for asset in record["assets"]:
            with urllib.request.urlopen(asset["url"], timeout=45) as response:
                data = response.read(MAX_ASSET + 1)
            if len(data) > MAX_ASSET or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                raise ValueError("Recognition data verification failed. Nothing was installed.")
            (staged / asset["file"]).write_bytes(data)
            asset["bytes"] = len(data)
        (staged / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        # The target is immutable; a concurrent setup must not replace any existing data.
        if output.exists() or output.is_symlink():
            raise ValueError("Recognition setup changed. Check its status before trying again.")
        staged.rename(output)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = managed_directory(os.environ.get("MASHI_DATA_DIR", ".mashi"))
    parser.add_argument(
        "--output", type=Path, default=Path(os.environ.get("MASHI_TESSDATA_DIR", default))
    )
    args = parser.parse_args()
    install_data(args.output)
    print(f"Verified Malayalam OCR data in {args.output}. Install the Tesseract engine separately.")


if __name__ == "__main__":
    main()
