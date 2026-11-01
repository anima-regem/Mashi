"""Explicitly download the official pinned Malayalam Tesseract data, with hash checks."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
ROOT = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{COMMIT}/"
ASSETS = {
    "mal.traineddata": "bd05cbf1b197e7810d2903419aedb06f9ef77bfedf50b358673c1d18d707cdb4",
    "LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ.get("MASHI_DATA_DIR", ".mashi")) / "ocr" / "tessdata"
    parser.add_argument(
        "--output", type=Path, default=Path(os.environ.get("MASHI_TESSDATA_DIR", default))
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for name, expected in ASSETS.items():
        target = args.output / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            data = target.read_bytes()
        else:
            with urllib.request.urlopen(ROOT + name, timeout=45) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Official OCR asset size/hash mismatch: " + name)
            target.write_bytes(data)
        records.append({"file": name, "url": ROOT + name, "bytes": len(data), "sha256": expected})
    manifest = {
        "repository": "tesseract-ocr/tessdata_fast",
        "commit": COMMIT,
        "license": "Apache-2.0",
        "language": "mal",
        "assets": records,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified Malayalam OCR data in {args.output}. Install the Tesseract engine separately.")


if __name__ == "__main__":
    main()
