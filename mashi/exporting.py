import io
import json
import math
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from ufoLib2 import Font

from .predictors import coverage
from .tracing import svg, validate_paths


def glyph_name(sequence):
    return "u" + "_".join(f"{ord(c):04X}" for c in sequence)


def eligible(project):
    return [
        r
        for r in project["regions"]
        if r["active"]
        and r["confirmed"]
        and r["label"]
        and r["vector"]
        and r["provenance"] == "observed"
    ]


def make_ufo(project):
    regions = eligible(project)
    if not regions:
        raise ValueError("Confirm and trace at least one labelled crop before exporting")
    labels = [r["label"] for r in regions]
    if len(set(labels)) != len(labels):
        raise ValueError(
            "Two confirmed crops have the same label. Keep one confirmed variant per label."
        )
    font = Font()
    font.info.familyName = "Mashi Handwriting Experimental"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = 1000
    font.info.ascender, font.info.descender = 1000, -400
    font.info.openTypeOS2TypoAscender, font.info.openTypeOS2TypoDescender = 1000, -400
    font.info.versionMajor, font.info.versionMinor = 0, 1
    font.info.copyright = (
        "Outlines from locally confirmed handwriting. Rights remain with their owners."
    )
    missing = font.newGlyph(".notdef")
    missing.width = 600
    pen = missing.getPen()
    for x, y in [(80, 0), (80, 700), (520, 700), (520, 0)]:
        (pen.moveTo if (x, y) == (80, 0) else pen.lineTo)((x, y))
    pen.closePath()
    font.newGlyph("space").unicodes, font["space"].width = [32], 300
    singles = {r["label"]: glyph_name(r["label"]) for r in regions if len(r["label"]) == 1}
    substitutions, unsupported = [], []
    for region in regions:
        label, vector = region["label"], region["vector"]
        validate_paths(vector["paths"])
        glyph = font.newGlyph(glyph_name(label))
        if len(label) == 1:
            glyph.unicodes = [ord(label)]
        glyph.width = vector["advance"]
        if len(label) == 1 and unicodedata.category(label).startswith("M"):
            glyph.width = 0
        scale, baseline = vector["scale"], vector["baseline"]
        pen = TransformPen(glyph.getPen(), (scale, 0, 0, -scale, 50, baseline * scale))
        for path in vector["paths"]:
            parse_path(path, pen)
        glyph.lib["org.mashi.provenance"] = {
            "state": "observed",
            "region": region["id"],
            "revision": region["revision"],
            "label": label,
            "canonicalImageSHA256": project["image"]["canonical_sha256"],
            "crop": region["box"],
            "vectorEdited": vector["edited"],
        }
        if len(label) > 1:
            if all(c in singles for c in label):
                substitutions.append(
                    (
                        label,
                        "sub " + " ".join(singles[c] for c in label) + " by " + glyph.name + ";",
                    )
                )
            else:
                unsupported.append(label)
    # Whole-sequence observations only, all dependencies verified. No borrowed FEA.
    if substitutions:
        rules = "\n".join(rule for _, rule in sorted(substitutions, key=lambda v: -len(v[0])))
        font.features.text = (
            "languagesystem DFLT dflt;\nlanguagesystem mlym dflt;\nlanguagesystem mlm2 dflt;\n"
            "feature akhn {\n" + rules + "\n} akhn;\n"
        )
    top, bottom = 1000, -400
    for glyph in font:
        bounds_pen = BoundsPen(font)
        glyph.draw(bounds_pen)
        if bounds_pen.bounds:
            x0, y0, x1, y1 = bounds_pen.bounds
            if any(abs(v) > 16000 for v in (x0, y0, x1, y1)):
                raise ValueError(
                    "Font outline exceeds 16,000 units. Reduce scale or path coordinates."
                )
            top, bottom = max(top, math.ceil(y1) + 20), min(bottom, math.floor(y0) - 20)
    font.info.openTypeOS2WinAscent, font.info.openTypeOS2WinDescent = top, -bottom
    report = coverage(project)
    report.update(
        {
            "format_version": 1,
            "experimental": True,
            "encoded_codepoints": [f"U+{ord(c):04X}" for c in singles],
            "sequence_substitutions": [s for s, _ in substitutions],
            "unencoded_sequences": unsupported,
            "warnings": [
                "Not a complete Malayalam text font.",
                "No mark anchors, contextual substitutions or vowel reordering rules.",
                "Multi-codepoint forms need all component codepoints captured separately.",
                "ZWJ/ZWNJ sequences require dedicated shaping work and testing.",
                "Metrics are initial estimates; review baseline, scale and advance.",
            ],
        }
    )
    return font, report


def export_bundle(project, kind):
    font, report = make_ufo(project)
    with tempfile.TemporaryDirectory(prefix="mashi-export-") as directory:
        root = Path(directory)
        font_path = root / "Mashi-Handwriting.ufo"
        font.save(font_path)
        if kind == "ttf":
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fontmake",
                        "-u",
                        str(font_path),
                        "-o",
                        "ttf",
                        "--output-path",
                        str(root / "Mashi-Experimental.ttf"),
                        "--no-production-names",
                    ],
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ValueError(
                    "Font compiler unavailable or timed out. Export UFO for review."
                ) from error
            if result.returncode:
                raise ValueError(
                    "Font compiler rejected these outlines. Export UFO and review geometry."
                )
        (root / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (root / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2))
        (root / "READ-ME.txt").write_text(
            "Mashi experimental export. Actual confirmed handwriting only.\n"
            "Inspect coverage.json before use. This is not a complete Malayalam shaping font.\n"
            "Original photos are not included. project.json contains image hashes and crop metadata.\n"
        )
        svg_dir = root / "svg"
        svg_dir.mkdir()
        for region in eligible(project):
            (svg_dir / (glyph_name(region["label"]) + ".svg")).write_bytes(svg(region["vector"]))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))
        return buffer.getvalue()
