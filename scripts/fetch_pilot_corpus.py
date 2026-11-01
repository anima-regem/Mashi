"""Explicit network acquisition for the research pilot; never invoked by the app."""

import argparse
import base64
import hashlib
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

COMMIT = "6c1dbe27dcf7d817d4b62cec033ba77fa8e2a5ec"
SOURCES = [
    ("chilanka", "Chilanka-Regular.ttf", "train", "smc-chilanka"),
    ("manjari", "Manjari-Regular.ttf", "train", "smc-manjari"),
    ("gayathri", "Gayathri-Regular.ttf", "train", "smc-gayathri"),
    ("notosansmalayalam", "NotoSansMalayalam[wdth,wght].ttf", "test", "noto-malayalam"),
]


def fetch(path, via_gh):
    endpoint = f"repos/google/fonts/contents/{urllib.parse.quote(path)}?ref={COMMIT}"
    if via_gh:
        result = subprocess.run(["gh", "api", endpoint], capture_output=True, check=True)
        metadata = json.loads(result.stdout)
    else:
        request = urllib.request.Request(
            "https://api.github.com/" + endpoint, headers={"User-Agent": "Mashi-research-pilot"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            metadata = json.load(response)
    content = base64.b64decode(metadata["content"])
    return content, {
        "path": path,
        "blob_sha": metadata["sha"],
        "sha256": hashlib.sha256(content).hexdigest(),
        "url": metadata["html_url"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/pilot-corpus"))
    parser.add_argument(
        "--via-gh", action="store_true", help="Use existing gh public-read authentication"
    )
    args = parser.parse_args()
    records = []
    for family, filename, split, lineage in SOURCES:
        folder = args.output / family
        folder.mkdir(parents=True, exist_ok=True)
        assets = []
        for name in [filename, "OFL.txt", "METADATA.pb", "upstream_info.md"]:
            content, record = fetch(f"ofl/{family}/{name}", args.via_gh)
            (folder / name).write_bytes(content)
            assets.append(record)
        print(family, split, (folder / "OFL.txt").read_text().splitlines()[0])
        records.append(
            {
                "family": family,
                "file": f"{family}/{filename}",
                "split": split,
                "lineage_group": lineage,
                "repository": "google/fonts",
                "commit": COMMIT,
                "license": "OFL-1.1",
                "license_file": f"{family}/OFL.txt",
                "assets": assets,
            }
        )
    manifest = {
        "schema": 1,
        "acquired": "2026-11-01",
        "fonts": records,
        "split_policy": "Family-lineage separation; only Regular per family. Noto held out.",
        "validation_split": None,
        "hyperparameter_selection": "Fixed a priori; no tuning.",
        "license_note": "Keep each OFL/copyright notice; respect reserved names and OFL derivative conditions. No unrestricted output licence is inferred.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
