import io
import json
import math
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from dataclasses import asdict

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from ufoLib2 import Font

from .font_metrics import TypographyOptions, postscript_name, validate_vector_metrics
from .predictors import coverage
from .shaping import (
    CHILLUS,
    CONJUNCTS,
    CONSONANTS,
    INDEPENDENT,
    SINGLE_REPERTOIRE,
    VIRAMA,
    ZWJ,
    ZWNJ,
    feature_text,
    glyph_name,
    make_plan,
    shape_preview,
    text_coverage,
)
from .tracing import svg, validate_paths
from .ml_capture import references_current
from .ml_service import source_terms, LICENSE_ROOT


def regions_metadata(project):
    return [
        {
            key: item[key]
            for key in [
                "id",
                "label",
                "generation",
                "vectorization",
                "review_state",
                "provenance",
                "not_observed_in_photo",
            ]
        }
        for item in project.get("completion_suggestions", [])
    ]


def eligible(project, include_fixture=False, *, include_generated=False):
    fixture = project.get("source_kind") == "synthetic-fixture"
    if fixture and not include_fixture:
        return []
    regions = [
        r
        for r in project["regions"]
        if r["active"]
        and r["confirmed"]
        and r["label"]
        and r["vector"]
        and (
            r["provenance"] == "observed"
            or (fixture and include_fixture and r["provenance"] == "synthetic-fixture")
        )
    ]
    if include_generated:
        candidates = [
            r
            for r in project.get("completion_suggestions", [])
            if r["active"] and r["confirmed"] and r["review_state"] == "accepted" and r["vector"]
        ]
        if not candidates:
            raise ValueError(
                "Accept at least one generated suggestion before choosing a generated-font output"
            )
        for item in candidates:
            terms = source_terms(item["generation"]["model"]["sha256"])
            if (
                not terms["checkpoint_source_known"]
                or item["generation"]["model"]["terms"]["source_manifest_sha256"]
                != terms["source_manifest_sha256"]
            ):
                raise ValueError(
                    "This checkpoint has no verified source-notice mapping for font export"
                )
            if not references_current(project, item):
                raise ValueError(
                    "Generated references changed. Reject and regenerate the affected suggestions."
                )
        regions += candidates
    return regions


def export_preflight(project, text="", include_fixture=False, *, include_generated=False):
    """Cheap read-only coverage for a caller's live preview; never compiles a font.

    Use make_ufo for geometry/metadata validation and preview_project for actual
    shaping. Synthetic practice data is never treated as observed handwriting.
    """
    regions = eligible(project, include_fixture, include_generated=include_generated)
    labels = [r["label"] for r in regions]
    result = text_coverage(text, labels)
    result.update(make_plan(labels))
    result["profile"] = "malayalam-v1"
    result["duplicate_labels"] = sorted({s for s in labels if labels.count(s) > 1})
    result["synthetic_test_export"] = project.get("source_kind") == "synthetic-fixture"
    result["generated_font"] = include_generated
    if result["duplicate_labels"] or not regions:
        result["supported"] = False
    return result


def make_ufo(
    project, include_fixture=False, *, options=None, required_text=None, include_generated=False
):
    options = options or TypographyOptions()
    options.validate()
    fixture = project.get("source_kind") == "synthetic-fixture"
    if fixture and not include_fixture:
        raise ValueError(
            "Synthetic practice shapes are excluded from handwriting exports. Explicitly enable a synthetic test export."
        )
    regions = eligible(project, include_fixture, include_generated=include_generated)
    if not regions:
        raise ValueError("Confirm and trace at least one labelled crop before exporting")
    labels = [r["label"] for r in regions]
    if len(set(labels)) != len(labels):
        raise ValueError(
            "Two confirmed crops have the same label. Keep one confirmed variant per label."
        )
    if set(options.anchors) - set(labels):
        raise ValueError("Anchor overrides reference labels excluded from this export")
    for label in labels:
        if len(label) > 32 or any(
            not (0x0D00 <= ord(c) <= 0x0D7F or c in ZWJ + ZWNJ) for c in label
        ):
            raise ValueError("Use Malayalam labels with optional ZWJ/ZWNJ")
        if label in {ZWJ, ZWNJ}:
            raise ValueError("Joiners are engine controls, not standalone ink samples")
    plan = make_plan(labels)
    required = (
        export_preflight(
            project, required_text, include_fixture, include_generated=include_generated
        )
        if required_text is not None
        else None
    )
    if required is not None and not required["supported"]:
        raise ValueError(
            "Required text is unsupported: " + json.dumps(required["issues"], ensure_ascii=False)
        )
    font = Font()
    font.info.familyName = "Mashi Synthetic Fixture" if fixture else options.family_name
    if include_generated:
        forbidden = {
            "anekmalayalam",
            "anjalioldlipi",
            "dyuthi",
            "gayathri",
            "karumbi",
            "malini",
            "meera",
            "rachana",
            "baloochettan2",
            "chilanka",
            "manjari",
            "notosansmalayalam",
            "notoserifmalayalam",
            "uroob",
        }
        requested = "".join(c for c in options.family_name.lower() if c.isalpha())
        if any(requested.startswith(name) for name in forbidden):
            raise ValueError("Choose a generated font name distinct from the source font families")
        font.info.familyName = (
            "Mashi Synthetic Generated"
            if fixture
            else (
                options.family_name
                if options.family_name.lower().endswith("generated")
                else options.family_name + " Generated"
            )
        )
        font.info.openTypeNameLicense = (LICENSE_ROOT / "OFL.txt").read_text()
        font.info.openTypeNameLicenseURL = "https://openfontlicense.org"
    font.info.styleName = options.style_name
    font.info.postscriptFontName = postscript_name(font.info.familyName, options.style_name)
    font.info.styleMapStyleName = "regular"
    font.info.unitsPerEm = 1000
    font.info.versionMajor, font.info.versionMinor = 0, 2
    font.info.copyright = (
        "Synthetic test geometry; not actual handwriting."
        if fixture
        else "Outlines from locally confirmed image ink. Rights remain with their owners."
    )
    if include_generated:
        notices = []
        for record in source_terms(regions[-1]["generation"]["model"]["sha256"])["notices"]:
            notice = (LICENSE_ROOT / record["notice"]).read_text(encoding="utf-8-sig")
            notices.append(notice.split("SIL OPEN FONT LICENSE")[0].strip()[:2000])
        font.info.copyright = (
            ("Synthetic test inputs; not handwriting. " if fixture else "")
            + "Contains reviewed model-generated geometry and captured contributions. Generated font: SIL OFL-1.1. Source notices:\n"
            + "\n".join(notices)
        )
    missing = font.newGlyph(".notdef")
    missing.width = 600
    pen = missing.getPen()
    for x, y in [(80, 0), (80, 700), (520, 700), (520, 0)]:
        (pen.moveTo if (x, y) == (80, 0) else pen.lineTo)((x, y))
    pen.closePath()
    font.newGlyph("space").unicodes, font["space"].width = [32], options.space_advance
    for control in (ZWJ, ZWNJ):
        font.newGlyph(glyph_name(control)).unicodes = [ord(control)]
        font[glyph_name(control)].width = 0
    singles = {r["label"]: glyph_name(r["label"]) for r in regions if len(r["label"]) == 1}
    bounds = {}
    for region in regions:
        label, vector = region["label"], region["vector"]
        validate_paths(vector["paths"])
        validate_vector_metrics(vector, spacing=label != VIRAMA)
        glyph = font.newGlyph(glyph_name(label))
        if len(label) == 1:
            glyph.unicodes = [ord(label)]
        glyph.width = 0 if label == VIRAMA else round(vector["advance"])
        scale, baseline = vector["scale"], vector["baseline"]
        pen = TransformPen(glyph.getPen(), (scale, 0, 0, -scale, 50, baseline * scale))
        for path in vector["paths"]:
            parse_path(path, pen)
        bounds_pen = BoundsPen(font)
        glyph.draw(bounds_pen)
        if bounds_pen.bounds is None:
            raise ValueError(f"Label {label!r} has no ink bounds")
        bounds[label] = bounds_pen.bounds
        if any(abs(v) > 16000 for v in bounds[label]):
            raise ValueError("Font outline exceeds 16,000 units. Reduce scale or path coordinates.")
        glyph.lib["org.mashi.provenance"] = {
            "state": "model-generated"
            if region["provenance"] == "model-generated"
            else ("synthetic-fixture" if fixture else region["provenance"]),
            "inputKind": project.get("source_kind", "user-upload"),
            "region": region["id"],
            "revision": region["revision"],
            "label": label,
            "canonicalImageSHA256": project["image"]["canonical_sha256"],
            "crop": region["box"],
            "vectorEdited": vector["edited"],
        }
        if region["provenance"] == "model-generated":
            glyph.lib["org.mashi.provenance"]["canonicalImageSHA256"] = region["raster_sha256"]
            glyph.lib["org.mashi.provenance"]["referencePageSHA256"] = project["image"][
                "canonical_sha256"
            ]
            glyph.lib["org.mashi.provenance"]["coordinateSpace"] = "generated-canvas"
            glyph.lib["org.mashi.provenance"]["generation"] = region["generation"]
            glyph.lib["org.mashi.provenance"]["vectorization"] = region["vectorization"]
            glyph.lib["org.mashi.provenance"]["reviewState"] = region["review_state"]
            glyph.lib["org.mashi.provenance"]["notObservedInPhoto"] = True
    bases, mark = {}, None
    anchor_report = {}
    for label, (x0, y0, x1, y1) in bounds.items():
        default = None
        if label == VIRAMA:
            name, default = "_top", ((x0 + x1) / 2, y0)
        elif label in CONSONANTS + CHILLUS + INDEPENDENT or label in CONJUNCTS:
            name, default = "top", (x1, y1 + options.mark_gap)
        if default:
            overrides = options.anchors.get(label, {})
            if set(overrides) - {name}:
                raise ValueError(f"Label {label!r} accepts only the {name} anchor")
            point = tuple(overrides.get(name, default))
            # Integer anchor positions match the generated GPOS, diagnostics and metrics.
            point = tuple(round(v) for v in point)
            font[glyph_name(label)].appendAnchor({"name": name, "x": point[0], "y": point[1]})
            anchor_report[label] = {
                "name": name,
                "point": point,
                "estimated": name not in overrides,
            }
            if label == VIRAMA:
                mark = point
            else:
                bases[glyph_name(label)] = point
        elif options.anchors.get(label):
            raise ValueError(f"Label {label!r} has no V1 anchor role")
    font.features.text = feature_text(plan, bases, mark)
    top, bottom = max(options.ascender, 720), options.descender
    for _, y0, _, y1 in bounds.values():
        top, bottom = max(top, math.ceil(y1) + 20), min(bottom, math.floor(y0) - 20)
    # Include the POSITIONED mark extent, rather than just its nominal glyph bounds.
    if mark:
        _, my0, _, my1 = bounds[VIRAMA]
        for _, by in bases.values():
            top = max(top, math.ceil(by - mark[1] + my1) + 20)
            bottom = min(bottom, math.floor(by - mark[1] + my0) - 20)
    if top > 16000 or bottom < -16000:
        raise ValueError("Positioned marks exceed supported vertical metrics; adjust anchors/scale")
    for key, value in {
        "ascender": top,
        "descender": bottom,
        "openTypeOS2TypoAscender": top,
        "openTypeOS2TypoDescender": bottom,
        "openTypeOS2TypoLineGap": options.line_gap,
        "openTypeHheaAscender": top,
        "openTypeHheaDescender": bottom,
        "openTypeHheaLineGap": options.line_gap,
        "openTypeOS2WinAscent": top,
        "openTypeOS2WinDescent": -bottom,
    }.items():
        setattr(font.info, key, value)
    font.info.openTypeOS2Selection = [7]  # USE_TYPO_METRICS; hhea matches.
    supported_forms = [
        s
        for s in sorted(set(labels) | {r["sequence"] for r in plan["rules"]})
        if text_coverage(s, labels, plan)["supported"]
    ]
    report = coverage(project)
    report.update(
        {
            "format_version": 2,
            "experimental": True,
            "shaping_profile": "malayalam-v1",
            "input_kind": project.get("source_kind", "user-upload"),
            "synthetic_test_export": fixture,
            "synthetic_included": [
                r["id"] for r in regions if r["provenance"] == "synthetic-fixture"
            ]
            if fixture
            else [],
            "fixtures_excluded": [] if fixture else report["fixtures_excluded"],
            "encoded_codepoints": [f"U+{ord(c):04X}" for c in singles],
            "engine_controls": ["U+200C", "U+200D"],
            "sequence_substitutions": [r["sequence"] for r in plan["rules"]],
            "shaping_plan": plan,
            "unencoded_sequences": plan["unencoded_sequences"],
            "unsupported_single_codepoints": sorted(set(singles) - SINGLE_REPERTOIRE),
            "supported_forms": supported_forms,
            "required_text": required,
            "typography_options": asdict(options),
            "font_family": font.info.familyName,
            "generated_font": include_generated,
            "included_generated": [
                r["id"] for r in regions if r["provenance"] == "model-generated"
            ],
            "generated_excluded": [
                r["id"] for r in project.get("completion_suggestions", []) if r not in regions
            ]
            + [
                r["id"]
                for r in project["regions"]
                if r["provenance"] not in {"observed", "synthetic-fixture"}
            ],
            "generated_font_terms": source_terms(regions[-1]["generation"]["model"]["sha256"])
            if include_generated
            else None,
            "metrics": {
                "units_per_em": 1000,
                "ascender": top,
                "descender": bottom,
                "line_gap": options.line_gap,
                "anchors": anchor_report,
            },
            "warnings": [
                "Partial Malayalam V1 font; supported_forms is conditional on these captured samples.",
                "Only mlm2 shaping is tested; mlym is not a traditional/modern style selector.",
                "Virama anchors are geometry estimates unless overridden; reader review is required.",
                "Attached vowels need observed base+vowel forms; arbitrary contextual forms are unsupported.",
                "Exact Unicode is preserved. HarfBuzz may canonically decompose text during shaping.",
                "Per-crop baseline/scale/advance remain user-controlled 1000-UPM font units.",
            ],
        }
    )
    if plan["unencoded_sequences"] or report["unsupported_single_codepoints"]:
        report["warnings"].append(
            "Some captured forms are outside V1 or lack input samples; see shaping_plan."
        )
    return font, report


def _compile(font_path, output):
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
                str(output),
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
        raise ValueError("Font compiler rejected these outlines. Export UFO and review geometry.")


def _validate_ttf(data, report, *, require_shaping=False):
    with TTFont(io.BytesIO(data)) as tt:
        cmap = tt.getBestCmap()
        if any(
            cmap.get(int(cp[2:], 16)) != glyph_name(chr(int(cp[2:], 16)))
            for cp in report["encoded_codepoints"]
        ):
            raise ValueError("Compiled font cmap does not match the captured codepoints")
        if (
            tt["hhea"].ascent != report["metrics"]["ascender"]
            or tt["hhea"].descent != report["metrics"]["descender"]
        ):
            raise ValueError("Compiled font line metrics do not match preflight")
    try:
        corpus = "\n".join(report["supported_forms"])
        preview = shape_preview(data, corpus)
        if preview["has_notdef"] or any(
            p["code"] == "vertical_clipping" for p in preview["diagnostics"]
        ):
            raise ValueError("Declared V1 forms produce missing glyphs or clipped marks")
        expected = {r["sequence"]: glyph_name(r["output"]) for r in report["shaping_plan"]["rules"]}
        for text, line in zip(report["supported_forms"], preview["lines"]):
            if text in expected and [g["name"] for g in line["glyphs"]] != [expected[text]]:
                raise ValueError(f"Shaping did not select the captured form for {text!r}")
        report["shaping_validation"] = {
            "status": "passed",
            "engine": preview["engine"],
            "forms_tested": report["supported_forms"],
            "diagnostics": preview["diagnostics"],
        }
        if report["required_text"] is not None:
            required = shape_preview(data, report["required_text"]["text"])
            if required["has_notdef"] or any(
                p["code"] == "vertical_clipping" for p in required["diagnostics"]
            ):
                raise ValueError("Required text produces missing glyphs or clipped marks")
            report["required_preview"] = required
    except ValueError as error:
        if "HarfBuzz unavailable:" not in str(error) or require_shaping:
            raise
        report["shaping_validation"] = {"status": "not_run", "reason": str(error)}
        report["warnings"].append(str(error))


def preview_project(project, text, include_fixture=False, *, options=None, include_generated=False):
    """Backend live preview boundary; caller can cache by project revision/options.

    Returns coverage and real HarfBuzz glyph positions. Unsupported text is still
    shaped for inspection, with diagnostics; no substitute font masks missing ink.
    """
    preflight = export_preflight(
        project, text, include_fixture, include_generated=include_generated
    )
    font, report = make_ufo(
        project, include_fixture, options=options, include_generated=include_generated
    )
    with tempfile.TemporaryDirectory(prefix="mashi-preview-") as directory:
        root = Path(directory)
        font.save(root / "preview.ufo")
        _compile(root / "preview.ufo", root / "preview.ttf")
        data = (root / "preview.ttf").read_bytes()
        _validate_ttf(data, report, require_shaping=True)
        from .shaping import proof_outlines

        preview = shape_preview(data, text)
        return {
            "coverage": preflight,
            "preview": preview,
            "drawing": proof_outlines(data, preview),
            "metrics": report["metrics"],
        }


def export_bundle(
    project,
    kind,
    include_fixture=False,
    *,
    options=None,
    required_text=None,
    include_generated=False,
):
    if kind not in {"ufo", "ttf"}:
        raise ValueError("Supported export formats are ufo and ttf")
    font, report = make_ufo(
        project,
        include_fixture,
        options=options,
        required_text=required_text,
        include_generated=include_generated,
    )
    fixture = project.get("source_kind") == "synthetic-fixture"
    with tempfile.TemporaryDirectory(prefix="mashi-export-") as directory:
        root = Path(directory)
        stem = (
            ("Mashi-Synthetic-Generated" if fixture else "Mashi-Generated")
            if include_generated
            else ("Mashi-Synthetic" if fixture else "Mashi-Handwriting")
        )
        font_path = root / (stem + ".ufo")
        font.save(font_path)
        if kind == "ttf":
            output = root / (
                (
                    stem
                    if include_generated
                    else ("Mashi-Synthetic" if fixture else "Mashi-Experimental")
                )
                + ".ttf"
            )
            _compile(font_path, output)
            _validate_ttf(output.read_bytes(), report, require_shaping=required_text is not None)
        else:
            report["shaping_validation"] = {
                "status": "not_run",
                "reason": "UFO source export; compile and shape before use",
            }
        (root / "coverage.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "project.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "READ-ME.txt").write_text(
            (
                "SYNTHETIC TEST INPUT. Not actual handwriting.\n"
                if fixture and include_generated
                else ""
            )
            + (
                "GENERATED FONT. Contains accepted model-generated geometry, not reconstructed handwriting. SIL OFL-1.1 and retained source notices apply. Checkpoint distribution remains unresolved; no weights included.\n"
                if include_generated
                else "SYNTHETIC TEST EXPORT. Practice geometry, not actual handwriting.\n"
                if fixture
                else "Mashi experimental export. Confirmed observed image ink only.\n"
            )
            + "Inspect coverage.json before use. Partial Malayalam V1, not a complete language font.\n"
            "Read docs/TYPOGRAPHY.md in the source repository for repertoire and limitations.\n"
            "Original photos are not included. project.json contains image hashes and crop metadata.\n",
            encoding="utf-8",
        )
        if include_generated:
            notices = root / "FONT-LICENSES"
            notices.mkdir()
            for source in LICENSE_ROOT.iterdir():
                if source.is_file():
                    payload = source.read_bytes()
                    (notices / source.name).write_bytes(payload)
            (root / "GENERATED-PROVENANCE.json").write_text(
                json.dumps(
                    {
                        "font_license": "OFL-1.1",
                        "sources": [
                            r
                            for r in regions_metadata(project)
                            if r["id"] in report["included_generated"]
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        svg_dir = root / "svg"
        svg_dir.mkdir()
        for region in eligible(project, include_fixture, include_generated=include_generated):
            (svg_dir / (glyph_name(region["label"]) + ".svg")).write_bytes(
                svg(region["vector"], region["provenance"], generation=region.get("generation"))
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))
        return buffer.getvalue()
