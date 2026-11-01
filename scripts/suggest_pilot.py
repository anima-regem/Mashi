"""Generate separate, unconfirmed research suggestions from a saved local Mashi page."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from mashi.completion import SDFCompletionModel, normalize_ink
from mashi.exporting import glyph_name
from mashi.store import Store
from mashi.tracing import svg, trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", required=True, help="Local project ID, visible in project.json"
    )
    parser.add_argument("--data-dir", type=Path, default=Path(".mashi"))
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("output/experiments/sdf-pilot/model.npz")
    )
    parser.add_argument("--output", type=Path, default=Path("output/pilot-suggestions"))
    parser.add_argument(
        "--sequences", help="Comma-separated single letters; default: missing inventory"
    )
    args = parser.parse_args()
    model = SDFCompletionModel.load(args.checkpoint)
    store = Store(args.data_dir)
    project = store.get(args.project)
    candidates = [
        r
        for r in project["regions"]
        if r["active"]
        and r["confirmed"]
        and r["provenance"] == "observed"
        and r["label"] in model.labels
    ]
    if len({r["label"] for r in candidates}) != len(candidates):
        raise ValueError("Keep one confirmed observation per sequence before fitting style")
    with Image.open(store.asset(project["id"], "page.png")) as page:
        observations = {r["label"]: normalize_ink(page.crop(r["box"])) for r in candidates}
    prediction, weights = model.predict(observations)
    sequences = (
        args.sequences.split(",")
        if args.sequences
        else [c for c in model.labels if c not in observations]
    )
    if any(c not in model.labels or c in observations for c in sequences):
        raise ValueError("Request only missing single letters in this checkpoint's inventory")
    args.output.mkdir(parents=True, exist_ok=True)
    suggestions = []
    for sequence in sequences:
        mask = prediction[model.labels.index(sequence)] >= 0
        if not mask.any():
            continue
        image = Image.fromarray(np.uint8(~mask) * 255).convert("RGB")
        raster_name = glyph_name(sequence) + "-MODEL-GENERATED.png"
        image.save(args.output / raster_name)
        # Tiny 64px masks can produce degenerate spline segments. Resample only
        # generated research masks, recording the operation in their manifest.
        enlarged = image.resize((256, 256), Image.Resampling.BICUBIC)
        vector = trace(enlarged, 180)
        filename = glyph_name(sequence) + "-MODEL-GENERATED.svg"
        (args.output / filename).write_bytes(svg(vector))
        suggestions.append(
            {
                "label": sequence,
                "provenance": "model-generated",
                "confirmed": False,
                "file": filename,
                "raw_raster": raster_name,
                "raster_postprocess": "64px SDF threshold at 0; bicubic 4x; trace threshold 180",
                "vector": vector,
                "uncertainty": "uncalibrated",
                "source": "sdf-pilot-v1",
                "not_observed_in_photo": True,
            }
        )
    manifest = {
        "project_id": project["id"],
        "project_revision": project["revision"],
        "canonical_image_sha256": project["image"]["canonical_sha256"],
        "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "observations": [{k: r[k] for k in ["id", "label", "revision", "box"]} for r in candidates],
        "style_weights": weights.tolist(),
        "suggestions": suggestions,
        "status": "research-only; needs human review; not imported or accepted by the studio",
        "license_note": "Preserve corpus/checkpoint font licence lineage; no unrestricted output licence is assigned.",
    }
    (args.output / "suggestions.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"Wrote {len(suggestions)} model-generated suggestions to {args.output}. None were accepted."
    )


if __name__ == "__main__":
    main()
