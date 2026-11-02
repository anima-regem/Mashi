"""Real local inference with an original synthetic ring; never a handwriting benchmark."""

import argparse
import io
import json
import os
from pathlib import Path
import uuid
import zipfile

from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--saved-profile",
        action="store_true",
        help="Validate/store a local pointer, then exercise startup without model environment variables",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = (args.output / "data").resolve()
    os.environ["MASHI_DATA_DIR"] = str(root)
    if args.saved_profile:
        from mashi.completion_setup import configure

        os.environ.pop("MASHI_COMPLETION_CHECKPOINT", None)
        os.environ.pop("MASHI_COMPLETION_SHA256", None)
        setup = configure(root, args.checkpoint, args.sha256)
        assert not setup["loaded"]
    else:
        os.environ.update(
            MASHI_COMPLETION_CHECKPOINT=str(args.checkpoint.resolve()),
            MASHI_COMPLETION_SHA256=args.sha256,
        )
    from fastapi.testclient import TestClient
    from mashi.app import create_app

    with TestClient(create_app(root, testing=True)) as client:
        client.headers["x-mashi-token"] = client.get("/api/session").json()["token"]
        initial = client.get("/api/completion/capabilities").json()
        assert not initial["loaded"]
        image = Image.new("RGB", (220, 180), "white")
        ImageDraw.Draw(image).ellipse((40, 25, 170, 155), outline="black", width=12)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        doc = client.post(
            "/api/projects?source=synthetic-fixture", content=buffer.getvalue()
        ).json()
        base = f"/api/projects/{doc['id']}"
        item = doc["regions"][0]
        doc = client.put(
            f"{base}/regions/{item['id']}",
            json={
                "revision": item["revision"],
                "box": item["box"],
                "label": "ക",
                "confirmed": True,
            },
        ).json()
        item = doc["regions"][0]
        doc = client.post(
            f"{base}/regions/{item['id']}/trace", json={"revision": item["revision"]}
        ).json()
        item = doc["regions"][0]
        result = client.post(
            base + "/completion/load",
            json={"revision": doc["revision"], "job_id": str(uuid.uuid4())},
        )
        if result.status_code != 200:
            raise RuntimeError(result.text)
        model = result.json()["model"]
        refs = client.post(
            base + "/completion/references", json={"revision": doc["revision"], "ids": [item["id"]]}
        ).json()["references"]
        targets = [s for s in ["ഖ", "മ", "ഗ"] if s in model["labels"]]
        generated = client.post(
            base + "/completion/generate",
            json={
                "revision": doc["revision"],
                "job_id": str(uuid.uuid4()),
                "ids": [item["id"]],
                "targets": targets,
                "reference_hashes": {r["id"]: r["sha256"] for r in refs},
                "alignment_confirmed": True,
            },
        )
        if generated.status_code != 200:
            raise RuntimeError(generated.text)
        doc = generated.json()
        summaries = [
            {
                "label": r["label"],
                "raster_sha256": r["raster_sha256"],
                "empty": r["empty_prediction"],
                "trace_error": r["trace_error"],
                "vectorized": bool(r["vector"]),
                "provenance": r["provenance"],
                "vectorization": r["vectorization"],
            }
            for r in doc["completion_suggestions"]
        ]
        usable = next(
            (r for r in doc["completion_suggestions"] if r["vector"] and not r["empty_prediction"]),
            None,
        )
        exported = False
        if usable:
            doc = client.post(
                f"{base}/completion/suggestions/{usable['id']}/review",
                json={
                    "revision": doc["revision"],
                    "suggestion_revision": usable["revision"],
                    "state": "accepted",
                },
            ).json()
            normal = client.post(
                base + "/proof/preflight?include_fixture=true",
                json={"revision": doc["revision"], "text": usable["label"]},
            ).json()
            assert not normal["coverage"]["supported"]
            output = client.post(
                base + "/export/ttf?include_fixture=true&include_generated=true",
                json={"revision": doc["revision"], "text": usable["label"]},
            )
            if output.status_code != 200:
                raise RuntimeError(output.text)
            (args.output / "synthetic-generated-font.zip").write_bytes(output.content)
            with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
                coverage = json.loads(archive.read("coverage.json"))
                assert (
                    coverage["generated_font"]
                    and coverage["shaping_validation"]["status"] == "passed"
                )
                assert "FONT-LICENSES/OFL.txt" in archive.namelist()
            exported = True
        report = {
            "synthetic_only": True,
            "setup_mode": "saved-local-profile" if args.saved_profile else "environment",
            "setup_validation": setup if args.saved_profile else None,
            "initially_off": not initial["loaded"],
            "fixture": "original drawn ring assigned a Malayalam label for plumbing, not glyph/handwriting accuracy",
            "project_id": doc["id"],
            "data_directory": str(root),
            "checkpoint_sha256": model["sha256"],
            "format_version": model["format_version"],
            "capabilities": model["capabilities"],
            "template_diagnostics_used": model["template_diagnostics_used"],
            "suggestions": summaries,
            "font_exported": exported,
            "selected_for_export": usable["label"] if usable else None,
            "selection_policy": "first vectorizable candidate, software smoke only; not quality selection",
            "generated_font_license": "OFL-1.1; source notices retained",
        }
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
