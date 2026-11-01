"""Fit/evaluate the tiny SDF model on audited fonts; no network or paid compute."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from mashi.completion import GRID, SDFCompletionModel, distance_field, normalize_ink

INVENTORY = list("അആഇഈഉഊഋഎഏഐഒഓഔകഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറൺൻർൽൾൿ")


def rasterize(path, label):
    font = ImageFont.truetype(str(path), 160)
    box = font.getbbox(label)
    image = Image.new("L", (box[2] - box[0] + 8, box[3] - box[1] + 8), 255)
    ImageDraw.Draw(image).text((4 - box[0], 4 - box[1]), label, font=font, fill=0)
    return normalize_ink(image)


def iou(a, b):
    return float(np.logical_and(a, b).sum() / max(1, np.logical_or(a, b).sum()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/pilot-corpus"))
    parser.add_argument("--output", type=Path, default=Path("output/experiments/sdf-pilot"))
    args = parser.parse_args()
    manifest_bytes = (args.corpus / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    records = manifest["fonts"]
    train = [r for r in records if r["split"] == "train"]
    test = [r for r in records if r["split"] == "test"]
    if {r["lineage_group"] for r in train} & {r["lineage_group"] for r in test}:
        raise ValueError("Train/test lineage leakage")
    cmaps, masks = [], []
    for record in records:
        path = args.corpus / record["file"]
        expected = next(a["sha256"] for a in record["assets"] if a["path"].endswith(path.name))
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Font hash mismatch: " + record["family"])
        with TTFont(path) as font:
            cmaps.append(font.getBestCmap())
    labels = [c for c in INVENTORY if all(ord(c) in cmap for cmap in cmaps)]
    for record in records:
        masks.append(np.stack([rasterize(args.corpus / record["file"], c) for c in labels]))
    fields = np.stack([[distance_field(mask) for mask in font_masks] for font_masks in masks])
    train_indices = [i for i, r in enumerate(records) if r["split"] == "train"]
    start = time.perf_counter()
    model = SDFCompletionModel.fit(labels, fields[train_indices], rank=2, ridge=0.1)
    training_seconds = time.perf_counter() - start
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "model.npz"
    checkpoint_hash = model.save(checkpoint)
    (args.output / "corpus-manifest.json").write_bytes(manifest_bytes)
    licenses = args.output / "licenses"
    licenses.mkdir(exist_ok=True)
    for record in records:
        (licenses / (record["family"] + "-OFL.txt")).write_bytes(
            (args.corpus / record["license_file"]).read_bytes()
        )
    loaded = SDFCompletionModel.load(checkpoint)
    # Fixed observations chosen without inspecting held-out results.
    anchor_labels = [c for c in list("അഇഉഎഒകചടതപ") if c in labels]
    results = []
    for index, record in enumerate(records):
        if record["split"] != "test":
            continue
        observed = {c: masks[index][labels.index(c)] for c in anchor_labels}
        predictions, weights = loaded.predict(observed)
        per_glyph = []
        for j, label in enumerate(labels):
            if label in observed:
                continue
            per_glyph.append(
                {
                    "sequence": label,
                    "codepoint": f"U+{ord(label):04X}",
                    "predicted_iou": iou(predictions[j] >= 0, masks[index][j]),
                    "mean_baseline_iou": iou(model.mean[j] >= 0, masks[index][j]),
                    "predicted_sdf_mae": float(np.abs(predictions[j] - fields[index, j]).mean()),
                    "mean_baseline_sdf_mae": float(np.abs(model.mean[j] - fields[index, j]).mean()),
                }
            )
        metrics = {
            key: float(np.mean([g[key] for g in per_glyph]))
            for key in (
                "predicted_iou",
                "mean_baseline_iou",
                "predicted_sdf_mae",
                "mean_baseline_sdf_mae",
            )
        }
        results.append(
            {
                "family": record["family"],
                "observed_sequences": anchor_labels,
                "held_out_glyphs": len(per_glyph),
                "style_weights": weights.tolist(),
                "metrics": metrics,
                "per_glyph": per_glyph,
            }
        )
        # Visual geometry inspection artifact, not a specimen of actual handwriting.
        preview = Image.new("RGB", (GRID * 3, GRID * min(12, len(per_glyph))), "white")
        for row, glyph in enumerate(per_glyph[:12]):
            j = labels.index(glyph["sequence"])
            for col, mask in enumerate([masks[index][j], model.mean[j] >= 0, predictions[j] >= 0]):
                tile = Image.fromarray(np.uint8(~mask) * 255).convert("RGB")
                preview.paste(tile, (col * GRID, row * GRID))
        preview.save(args.output / (record["family"] + "-target-mean-prediction.png"))
    report = {
        "experiment": "sdf-pilot-v1",
        "date": "2026-11-01",
        "trained": True,
        "model": "Paired-glyph SDF mean + shared rank-2 font-style PCA; ridge inference",
        "training_families": [r["family"] for r in train],
        "test_families": [r["family"] for r in test],
        "grid": GRID,
        "inventory": labels,
        "excluded_inventory": [c for c in INVENTORY if c not in labels],
        "training_font_count": len(train),
        "rank": len(model.basis),
        "ridge": model.ridge,
        "seed": None,
        "deterministic": "NumPy symmetric eigendecomposition; fixed anchor set",
        "training_seconds": training_seconds,
        "checkpoint_sha256": checkpoint_hash,
        "corpus_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evaluation": results,
        "limitations": [
            "Only three training font families and one held-out family.",
            "Rendered isolated letters, not human handwriting or photographs.",
            "Per-glyph bounding-box alignment removes baseline/spacing information.",
            "No conjuncts, dependent marks, font shaping, or writer-consent corpus.",
            "No validation tuning or broad quality claims; mean baseline may outperform.",
            "Checkpoint derives from OFL font geometry; keep source licence lineage.",
            "Not connected to the studio UI or enabled for user exports.",
        ],
    }
    (args.output / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "trained": True,
                "checkpoint": str(checkpoint),
                "training_seconds": training_seconds,
                "inventory_size": len(labels),
                "evaluation": [r["metrics"] for r in results],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
