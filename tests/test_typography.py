"""Engineering fixtures only. None of these rectangles establish Malayalam legibility."""

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from mashi.exporting import export_bundle, export_preflight, make_ufo, preview_project
from mashi.font_metrics import TypographyOptions
from mashi.shaping import (
    CHILLUS,
    CONJUNCTS,
    CONSONANTS,
    INDEPENDENT,
    SIGNS,
    VIRAMA,
    glyph_name,
    shape_preview,
    text_coverage,
)

CORPUS = json.loads((Path(__file__).parent / "fixtures/typography-v1.json").read_text())


def synthetic_typography(labels=None):
    labels = labels or list(dict.fromkeys(CONSONANTS + CHILLUS + INDEPENDENT + SIGNS)) + list(
        CONJUNCTS
    ) + ["കു", "കൂ", "കൃ", "കൄ", "കൢ", "കൣ", "ക്കു", "ൻു"]
    regions = []
    for index, label in enumerate(labels):
        mark = label == VIRAMA
        spacing_sign = len(label) == 1 and label in SIGNS and not mark
        width, height = (40, 40) if mark else ((100, 700) if spacing_sign else (500, 700))
        vector = {
            "paths": [f"M0 0H{width}V{height}H0Z"],
            "scale": 1,
            "baseline": 700,
            "advance": 200 if spacing_sign else 600,
            "edited": False,
            "width": width,
            "height": height,
        }
        regions.append(
            {
                "id": str(index),
                "active": True,
                "confirmed": True,
                "label": label,
                "provenance": "synthetic-fixture",
                "revision": 1,
                "vector": vector,
                "box": [0, 0, width, height],
            }
        )
    return {
        "source_kind": "synthetic-fixture",
        "image": {"canonical_sha256": "synthetic"},
        "regions": regions,
    }


@pytest.fixture(scope="module")
def compiled():
    project = synthetic_typography()
    bundle = zipfile.ZipFile(io.BytesIO(export_bundle(project, "ttf", True)))
    return project, bundle.read("Mashi-Synthetic.ttf"), json.loads(bundle.read("coverage.json"))


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["text"])
def test_harfbuzz_v1_corpus(compiled, case):
    project, data, _ = compiled
    coverage = export_preflight(project, case["text"], True)
    assert coverage["supported"], coverage
    preview = shape_preview(data, case["text"])
    glyphs = preview["lines"][0]["glyphs"]
    assert [g["name"] for g in glyphs] == [
        s if s == "space" else glyph_name(s) for s in case["glyphs"]
    ]
    assert [g["x_advance"] for g in glyphs] == case["advances"]
    assert not preview["has_notdef"]
    assert not preview["diagnostics"], preview


def test_declared_repertoire_and_cmap_are_distinct(compiled):
    _, data, report = compiled
    tt = TTFont(io.BytesIO(data))
    assert tt.getBestCmap()[ord("ക")] == glyph_name("ക")
    assert glyph_name("ക്ക") not in tt.getBestCmap().values()
    assert glyph_name("ക്ക") in tt.getGlyphOrder()
    assert report["shaping_validation"]["status"] == "passed"
    assert report["synthetic_test_export"]
    for text in report["supported_forms"]:
        assert not shape_preview(data, text)["has_notdef"]
    assert not report["shaping_validation"]["diagnostics"]
    assert {r.ScriptTag for r in tt["GSUB"].table.ScriptList.ScriptRecord} == {"DFLT", "mlm2"}


def test_virama_anchor_positions_and_adjustment(compiled):
    project, data, _ = compiled
    mark = shape_preview(data, "ക്")["lines"][0]["glyphs"][1]
    assert (mark["x_offset"], mark["y_offset"], mark["x_advance"]) == (-120, 80, 0)
    assert mark["bounds"] == [530, 740, 570, 780]
    options = TypographyOptions(anchors={"ക": {"top": (450, 900)}})
    preview = preview_project(project, "ക്", True, options=options)
    adjusted = preview["preview"]["lines"][0]["glyphs"][1]
    assert adjusted["bounds"] == [430, 900, 470, 940]
    assert not preview["metrics"]["anchors"]["ക"]["estimated"]


def test_line_metrics_include_positioned_marks():
    project = synthetic_typography(["ക", "്"])
    options = TypographyOptions(
        ascender=800, descender=-100, line_gap=50, anchors={"ക": {"top": (550, 1200)}}
    )
    bundle = zipfile.ZipFile(
        io.BytesIO(export_bundle(project, "ttf", True, options=options, required_text="ക്"))
    )
    tt = TTFont(io.BytesIO(bundle.read("Mashi-Synthetic.ttf")))
    assert tt["hhea"].ascent == tt["OS/2"].sTypoAscender == tt["OS/2"].usWinAscent == 1260
    assert tt["hhea"].descent == tt["OS/2"].sTypoDescender == -tt["OS/2"].usWinDescent == -100
    assert tt["hhea"].lineGap == tt["OS/2"].sTypoLineGap == 50
    assert tt["head"].unitsPerEm == 1000
    assert tt["OS/2"].fsSelection & (1 << 7)


def test_clipping_and_overlap_diagnostics(compiled):
    project, _, _ = compiled
    options = TypographyOptions(anchors={"ക": {"top": (450, 100)}})
    preview = preview_project(project, "ക്", True, options=options)["preview"]
    assert any(p["code"] == "ink_bounds_overlap" for p in preview["diagnostics"])
    # A modified external font is reported too; this does not merely trust UFO metrics.
    _, data, _ = compiled
    tt = TTFont(io.BytesIO(data))
    tt["hhea"].ascent = 750
    buf = io.BytesIO()
    tt.save(buf)
    assert any(
        p["code"] == "vertical_clipping" for p in shape_preview(buf.getvalue(), "ക്")["diagnostics"]
    )


def test_required_text_missing_samples_and_unsupported_grammar():
    project = synthetic_typography(["ക", "ൊ", "ക്ക"])
    report = export_preflight(project, "കൊ ക്ക കു സ്ത്ര", True)
    assert not report["supported"]
    assert {"െ", "ാ", "്", "കു"} <= set(report["required_samples"])
    assert "ക്ക" in report["missing_sequence_components"]
    assert any(p["code"] == "unsupported_conjunct" for p in report["issues"])
    with pytest.raises(ValueError, match="Required text is unsupported"):
        export_bundle(project, "ttf", True, required_text="കൊ")
    font, report = make_ufo(project, True)
    assert glyph_name("ക്ക") in font
    assert "ക്ക" in report["unencoded_sequences"]
    assert "ക്ക" not in report["supported_forms"]
    assert any("outside V1" in warning for warning in report["warnings"])


def test_exact_unicode_and_normalization_are_observational(compiled):
    project, data, _ = compiled
    before = copy.deepcopy(project)
    composed, decomposed = "കൊ", "കൊ"
    first = export_preflight(project, composed, True)
    second = export_preflight(project, decomposed, True)
    assert first["text"] == composed and second["text"] == decomposed
    assert first["codepoints"] != second["codepoints"]
    assert first["normalization"]["nfd"] == decomposed
    assert second["normalization"]["nfc"] == composed
    assert project == before
    assert shape_preview(data, composed)["lines"] == shape_preview(data, decomposed)["lines"]
    assert export_preflight(project, "ന്‍", True)["normalization"]["nfc"] == "ന്‍"
    assert shape_preview(data, "ന്‍")["lines"] != shape_preview(data, "ന്‌")["lines"]


def test_synthetic_and_generated_provenance_is_never_promoted():
    project = synthetic_typography(["ക", "്", "ക്ക"])
    assert export_preflight(project, "ക്ക")["required_samples"]
    with pytest.raises(ValueError, match="Synthetic practice"):
        make_ufo(project)
    project["regions"][2]["provenance"] = "model-generated"
    font, report = make_ufo(project, True)
    assert glyph_name("ക്ക") not in font
    assert not export_preflight(project, "ക്ക", True)["supported"]
    assert report["generated_excluded"] == ["2"]


@pytest.mark.parametrize(
    "options",
    [
        TypographyOptions(family_name=""),
        TypographyOptions(style_name="Bold"),
        TypographyOptions(line_gap=-1),
        TypographyOptions(anchors={"ക": {"top": (float("nan"), 100)}}),
        TypographyOptions(anchors={"ക": {"bottom": (0, 0)}}),
        TypographyOptions(anchors={"ഖ": {"top": (0, 0)}}),
    ],
)
def test_invalid_font_metadata_or_anchor_overrides(options):
    with pytest.raises(ValueError):
        make_ufo(synthetic_typography(["ക"]), True, options=options)


@pytest.mark.parametrize(
    "key,value",
    [("advance", 0), ("advance", float("inf")), ("baseline", float("nan")), ("scale", -1)],
)
def test_invalid_vector_metrics(key, value):
    project = synthetic_typography(["ക"])
    project["regions"][0]["vector"][key] = value
    with pytest.raises(ValueError):
        make_ufo(project, True)


def test_unicode_font_names_have_stable_distinct_postscript_names():
    first, _ = make_ufo(
        synthetic_typography(["ക"]), True, options=TypographyOptions(family_name="മഷി")
    )
    assert first.info.familyName == "Mashi Synthetic Fixture"
    project = synthetic_typography(["ക"])
    project["source_kind"] = "user-upload"
    project["regions"][0]["provenance"] = "observed"
    first, _ = make_ufo(project, options=TypographyOptions(family_name="മഷി"))
    second, _ = make_ufo(project, options=TypographyOptions(family_name="ലിപി"))
    assert first.info.familyName == "മഷി"
    assert first.info.postscriptFontName != second.info.postscriptFontName
    assert first.info.postscriptFontName.isascii() and len(first.info.postscriptFontName) <= 63


@pytest.mark.parametrize(
    "text",
    ["ി", "ക‍", "കിീ", "ൔ", "സ്ത്ര", "ക്ഷ്മ", "ക്ന", "ക്‍", "ക\u2060", "ക്ി", "ക്‌ി", "കംഃ", "കഃം", "ക\tക"],
)
def test_unknown_or_unvalidated_forms_do_not_claim_support(text):
    labels = [r["label"] for r in synthetic_typography()["regions"]]
    assert not text_coverage(text, labels)["supported"]


def test_preview_exposes_missing_glyph_without_font_fallback(compiled):
    _, data, _ = compiled
    result = shape_preview(data, "കX")
    assert result["has_notdef"]
    assert result["text"] == "കX"
    assert any(p["code"] == "notdef" and p["cluster"] == 1 for p in result["diagnostics"])


@pytest.mark.parametrize("text", list(CONJUNCTS) + ["കൄ", "കൢ", "കൣ", "ൻു"])
def test_each_supported_captured_rule_selects_the_observation(compiled, text):
    project, data, _ = compiled
    assert export_preflight(project, text, True)["supported"]
    assert [g["name"] for g in shape_preview(data, text)["lines"][0]["glyphs"]] == [
        glyph_name(text)
    ]


def test_captured_halant_form_applies_after_conjunct_stage():
    project = synthetic_typography(["ക", "്", "ക്", "ക്ക"])
    archive = zipfile.ZipFile(io.BytesIO(export_bundle(project, "ttf", True, required_text="ക് ക്ക")))
    data = archive.read("Mashi-Synthetic.ttf")
    assert [g["name"] for g in shape_preview(data, "ക് ക്ക")["lines"][0]["glyphs"]] == [
        glyph_name("ക്"),
        "space",
        glyph_name("ക്ക"),
    ]


def test_composable_repertoire_without_missing_or_clipped_glyphs(compiled):
    project, data, _ = compiled
    labels = [r["label"] for r in project["regions"]]
    forms = [
        base + suffix
        for base in list(CONSONANTS + CHILLUS) + list(CONJUNCTS)
        for suffix in list(SIGNS) + ["ൊ", "ോ", "ൌ", "്\u200c"]
        if text_coverage(base + suffix, labels)["supported"]
    ]
    assert len(forms) > 500
    preview = shape_preview(data, "\n".join(forms))
    assert not preview["has_notdef"]
    assert not preview["diagnostics"]


@pytest.mark.parametrize(
    "labels,text,expected",
    [
        (["ക", "െ", "ാ"], "കൊ", ["െ", "ക", "ാ"]),
        (["ക", "െ"], "കെ", ["െ", "ക"]),
        (["ൻ", "െ"], "ൻെ", ["െ", "ൻ"]),
    ],
)
def test_small_partial_fonts_do_not_need_unrelated_samples(labels, text, expected):
    bundle = zipfile.ZipFile(
        io.BytesIO(export_bundle(synthetic_typography(labels), "ttf", True, required_text=text))
    )
    preview = shape_preview(bundle.read("Mashi-Synthetic.ttf"), text)
    assert [g["name"] for g in preview["lines"][0]["glyphs"]] == [glyph_name(s) for s in expected]


def test_shaping_dependency_is_reported_honestly(compiled, monkeypatch):
    from mashi.exporting import _validate_ttf

    _, data, report = compiled
    report = copy.deepcopy(report)
    monkeypatch.setitem(__import__("sys").modules, "uharfbuzz", None)
    _validate_ttf(data, report)
    assert report["shaping_validation"]["status"] == "not_run"
    with pytest.raises(ValueError, match="Install the dev extra"):
        _validate_ttf(data, report, require_shaping=True)


def test_unsupported_format_and_duplicate_labels():
    project = synthetic_typography(["ക", "ക"])
    assert export_preflight(project, "ക", True)["duplicate_labels"] == ["ക"]
    with pytest.raises(ValueError, match="same label"):
        make_ufo(project, True)
    with pytest.raises(ValueError, match="Supported export formats"):
        export_bundle(project, "otf", True)
