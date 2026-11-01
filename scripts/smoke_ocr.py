"""Render a printed Malayalam fixture with HarfBuzz and exercise local OCR through the API."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from mashi.app import create_app
from mashi.ocr import capabilities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", required=True, type=Path, help="A licensed Malayalam font")
    parser.add_argument("--output", type=Path, default=Path("output/ocr-smoke"))
    args = parser.parse_args()
    if not shutil.which("hb-view") or not capabilities()["available"]:
        raise ValueError("Install hb-view, Tesseract and Malayalam data before this optional check")
    args.output.mkdir(parents=True, exist_ok=True)
    words = ["മലയാളം", "മഷി", "കേരളം"]
    text_path = args.output / "expected.txt"
    text_path.write_text("\n".join(words), encoding="utf-8")
    raster = args.output / "printed-malayalam.png"
    command = [
        "hb-view",
        str(args.font.resolve()),
        "--text-file",
        str(text_path),
        "--font-size=72",
        "--margin=40",
        "--line-space=20",
        "--language=ml",
        "--background=ffffff",
        "--foreground=000000",
        "--output-file",
        str(raster),
    ]
    subprocess.run(command, capture_output=True, check=True, timeout=30)
    app = create_app(args.output / "api-data", testing=True)
    with TestClient(app) as client:
        session = client.get("/api/session").json()
        client.headers["x-mashi-token"] = session["token"]
        upload = client.post("/api/projects?source=synthetic-fixture", content=raster.read_bytes())
        upload.raise_for_status()
        project = upload.json()
        result = client.post(
            f"/api/projects/{project['id']}/ocr", json={"revision": project["revision"]}
        )
        result.raise_for_status()
        proposals = [r for r in result.json()["regions"] if r["source"] == "ocr-word"]
    raw = [r["suggestion"]["raw_text"] for r in proposals]
    report = {
        "date": "2026-11-01",
        "input_kind": "HarfBuzz-rendered printed font fixture, not handwriting",
        "font_sha256": hashlib.sha256(args.font.read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(raster.read_bytes()).hexdigest(),
        "expected_words": words,
        "recognized_words": raw,
        "exact_word_matches": sum(a == b for a, b in zip(words, raw)),
        "expected_word_count": len(words),
        "recognized_word_count": len(raw),
        "all_proposals_unconfirmed": all(not r["confirmed"] and not r["label"] for r in proposals),
        "all_proposals_synthetic": all(r["provenance"] == "synthetic-fixture" for r in proposals),
        "word_suggestions": [r["suggestion"] for r in proposals],
        "ocr_engine": subprocess.check_output(["tesseract", "--version"], text=True).splitlines()[
            0
        ],
        "renderer": subprocess.check_output(["hb-view", "--version"], text=True).splitlines()[0],
        "render_parameters": {"font_size": 72, "margin": 40, "line_space": 20, "language": "ml"},
        "limitations": [
            "One clean printed fixture; no handwriting/noise benchmark.",
            "Word regions only; no inferred character segmentation or automatic confirmation.",
        ],
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
