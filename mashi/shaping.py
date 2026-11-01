"""Bounded Malayalam V1 shaping plan and read-only text diagnostics.

No outlines or feature source are borrowed. HarfBuzz owns Unicode reordering.
This module deliberately rejects forms outside its tested grammar.
"""

import io
import unicodedata

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

VIRAMA, ZWJ, ZWNJ = "\u0d4d", "\u200d", "\u200c"
CONSONANTS = "കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറ"
CHILLUS = "ൺൻർൽൾൿ"
INDEPENDENT = "അആഇഈഉഊഋഌഎഏഐഒഓഔൠൡ"
SPACING_SIGNS = "ാംഃിീെേൈൗ"  # Unicode mark category does not imply zero advance.
ATTACHED_VOWELS = "ുൂൃൄൢൣ"  # Require an observed base+vowel sample in V1.
SPLIT_VOWELS = {"ൊ": "ൊ", "ോ": "ോ", "ൌ": "ൌ"}
SIGNS = SPACING_SIGNS + ATTACHED_VOWELS + VIRAMA + "ൊോൌ"
SINGLE_REPERTOIRE = set(CONSONANTS + CHILLUS + INDEPENDENT + SIGNS + "൦൧൨൩൪൫൬൭൮൯")
CONJUNCTS = ("ക്ക", "ങ്ങ", "ച്ച", "ഞ്ഞ", "ട്ട", "ണ്ണ", "ത്ത", "ന്ന", "പ്പ", "മ്മ", "ല്ല", "ക്ഷ", "റ്റ", "ൻ്റ")
LEGACY_CHILLUS = dict(zip("ണനരലള", "ൺൻർൽൾ", strict=True))
DEPENDENT_VOWELS = SIGNS.replace(VIRAMA, "").replace("ം", "").replace("ഃ", "")


def glyph_name(sequence):
    return "u" + "_".join(f"{ord(c):04X}" for c in sequence)


def sequence_kind(label):
    if label in CONJUNCTS:
        return "akhn"
    if len(label) > 1 and label[-1] in ATTACHED_VOWELS:
        if label[:-1] in CONSONANTS + CHILLUS or label[:-1] in CONJUNCTS:
            return "psts"
    if len(label) == 2 and label[0] in CONSONANTS and label[1] == VIRAMA:
        return "haln"
    return None


def make_plan(labels):
    """Only emit rules whose real input and output glyphs exist in this font."""
    labels = set(labels)
    singles = {s for s in labels if len(s) == 1}
    rules, unsupported, dependencies = [], [], {}
    # One lookup per stage; longest inputs first prevents prefix ligatures eating input.
    for label in sorted(labels, key=lambda s: (-len(s), s)):
        if len(label) < 2:
            continue
        kind = sequence_kind(label)
        inputs = [label[:-1], label[-1]] if kind == "psts" else list(label)
        missing = [s for s in inputs if s not in labels or (len(s) > 1 and s not in CONJUNCTS)]
        if kind == "psts" and label[:-1] in CONJUNCTS:
            missing += [s for s in label[:-1] if s not in singles]
        if kind and not missing:
            rules.append({"sequence": label, "feature": kind, "inputs": inputs, "output": label})
        else:
            unsupported.append(label)
            dependencies[label] = list(dict.fromkeys(missing))
    for base, chillu in LEGACY_CHILLUS.items():
        if {base, VIRAMA, chillu} <= labels:
            rules.insert(
                0,
                {
                    "sequence": base + VIRAMA + ZWJ,
                    "feature": "akhn",
                    "inputs": [base, VIRAMA, ZWJ],
                    "output": chillu,
                },
            )
    return {
        "rules": rules,
        "unencoded_sequences": unsupported,
        "missing_sequence_components": dependencies,
    }


def feature_text(plan, bases, virama_anchor=None):
    sections = []
    for stage in ("akhn", "psts", "haln"):
        rules = [r for r in plan["rules"] if r["feature"] == stage]
        if rules:
            lines = [
                "sub "
                + " ".join(glyph_name(s) for s in r["inputs"])
                + " by "
                + glyph_name(r["output"])
                + ";"
                for r in rules
            ]
            sections.append(f"feature {stage} {{\n" + "\n".join(lines) + f"\n}} {stage};")
    if virama_anchor and bases:
        x, y = virama_anchor
        lines = [f"markClass {glyph_name(VIRAMA)} <anchor {round(x)} {round(y)}> @top;"]
        lines += [
            f"pos base {name} <anchor {round(p[0])} {round(p[1])}> mark @top;"
            for name, p in sorted(bases.items())
        ]
        sections.append(lines[0] + "\nfeature abvm {\n" + "\n".join(lines[1:]) + "\n} abvm;")
    if not sections:
        return ""
    return "languagesystem DFLT dflt;\nlanguagesystem mlm2 dflt;\n" + "\n".join(sections) + "\n"


def text_coverage(text, labels, plan=None):
    """Exact text in/out. NFC/NFD are informative only, never replacements."""
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError("Preview text must be a string of at most 10,000 codepoints")
    labels = set(labels)
    plan = plan or make_plan(labels)
    enabled = {r["sequence"] for r in plan["rules"]}
    issues, missing = [], []

    def issue(code, start, sequence, samples=()):
        issues.append(
            {
                "code": code,
                "index": start,
                "sequence": sequence,
                "required_samples": list(dict.fromkeys(samples)),
            }
        )
        missing.extend(samples)

    # Parse only the supported V1 grammar; unknown combinations get diagnostics.
    i = 0
    while i < len(text):
        start, c = i, text[i]
        if c in " \n":
            i += 1
            continue
        if c not in SINGLE_REPERTOIRE:
            issue("unsupported_character", i, c)
            i += 1
            continue
        if c in SIGNS:
            issue("orphan_sign", i, c)
            i += 1
            continue
        if c not in labels:
            issue("missing_codepoint", i, c, [c])
        i += 1
        base, dead = c, False
        if c in CONSONANTS + CHILLUS:
            # Consume conjunct or explicit visible-halant / legacy chillu.
            while i < len(text) and text[i] == VIRAMA:
                dead = True
                if VIRAMA not in labels:
                    issue("missing_codepoint", i, VIRAMA, [VIRAMA])
                i += 1
                if i < len(text) and text[i] == ZWJ:
                    seq = base + VIRAMA + ZWJ
                    if base not in LEGACY_CHILLUS or seq not in enabled:
                        samples = [LEGACY_CHILLUS[base]] if base in LEGACY_CHILLUS else []
                        issue("unsupported_joiner_sequence", start, seq, samples)
                    i += 1
                    base = LEGACY_CHILLUS.get(base, base)
                    dead = False
                    break
                if i < len(text) and text[i] == ZWNJ:
                    i += 1  # Explicit visible halant; intentionally no conjunct.
                    break
                if i < len(text) and text[i] in CONSONANTS + CHILLUS:
                    base += VIRAMA + text[i]
                    if text[i] not in labels:
                        issue("missing_codepoint", i, text[i], [text[i]])
                    i += 1
                    dead = False
                else:
                    break
            if VIRAMA in base and base not in enabled:
                issue(
                    "missing_conjunct" if base in CONJUNCTS else "unsupported_conjunct",
                    start,
                    base,
                    [base] if base in CONJUNCTS else [],
                )
            if i < len(text) and text[i] in DEPENDENT_VOWELS and not dead:
                sign = text[i]
                components = SPLIT_VOWELS.get(sign, sign)
                # Already decomposed split vowels are consumed as one dependent vowel.
                if i + 1 < len(text) and sign in "െേ" and text[i + 1] in "ാൗ":
                    candidate = text[i : i + 2]
                    if candidate in SPLIT_VOWELS.values():
                        components = candidate
                if sign in ATTACHED_VOWELS and base + sign not in enabled:
                    supported_kind = sequence_kind(base + sign)
                    issue(
                        "missing_vowel_form" if supported_kind else "unsupported_vowel_form",
                        start,
                        base + sign,
                        [base + sign] if supported_kind else [],
                    )
                for part in components:
                    if part not in labels:
                        issue("missing_vowel_component", i, part, [part])
                i += len(components) if text[i : i + len(components)] == components else 1
        # Anusvara and visarga are spacing syllable modifiers, not combining anchors.
        if i < len(text) and text[i] in "ംഃ":
            if text[i] not in labels:
                issue("missing_codepoint", i, text[i], [text[i]])
            i += 1
    return {
        "text": text,
        "codepoints": [f"U+{ord(c):04X}" for c in text],
        "normalization": {
            "policy": "preserve",
            "nfc": unicodedata.normalize("NFC", text),
            "nfd": unicodedata.normalize("NFD", text),
        },
        "supported": not issues,
        "issues": issues,
        "required_samples": list(dict.fromkeys(missing)),
    }


def shape_preview(font_bytes, text):
    """HarfBuzz positions and ink bounds for an already exported TTF; no fallback font.

    Clusters are Unicode scalar indexes, not UTF-8 byte offsets. Multiline text is
    returned as separate lines. Ink intersection is a review hint, not legibility proof.
    """
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError("Preview text must be a string of at most 10,000 codepoints")
    try:
        import uharfbuzz as hb
    except ImportError as error:
        raise ValueError(
            "HarfBuzz unavailable: reinstall Mashi's locked runtime dependencies for verified preview"
        ) from error
    tt = TTFont(io.BytesIO(font_bytes))
    font = hb.Font(hb.Face(font_bytes))
    font.scale = (tt["head"].unitsPerEm,) * 2
    lines, problems = [], []
    for line_number, line in enumerate(text.split("\n")):
        buf = hb.Buffer()
        buf.add_codepoints([ord(c) for c in line])
        buf.direction, buf.script, buf.language = "ltr", "Mlym", "ml"
        hb.shape(font, buf)
        x, y, glyphs = 0, 0, []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
            name = tt.getGlyphName(info.codepoint)
            ext = font.get_glyph_extents(info.codepoint)
            bounds = None
            if ext and (ext.width or ext.height):
                left, top = x + pos.x_offset + ext.x_bearing, y + pos.y_offset + ext.y_bearing
                bounds = [left, top + ext.height, left + ext.width, top]
                if bounds[1] < tt["hhea"].descent or bounds[3] > tt["hhea"].ascent:
                    problems.append(
                        {"code": "vertical_clipping", "line": line_number, "glyph": name}
                    )
                if glyphs and glyphs[-1]["bounds"]:
                    old = glyphs[-1]["bounds"]
                    if max(old[0], bounds[0]) < min(old[2], bounds[2]) and max(
                        old[1], bounds[1]
                    ) < min(old[3], bounds[3]):
                        problems.append(
                            {"code": "ink_bounds_overlap", "line": line_number, "glyph": name}
                        )
            if info.codepoint == 0:
                problems.append({"code": "notdef", "line": line_number, "cluster": info.cluster})
            glyphs.append(
                {
                    "name": name,
                    "cluster": info.cluster,
                    "x_advance": pos.x_advance,
                    "y_advance": pos.y_advance,
                    "x_offset": pos.x_offset,
                    "y_offset": pos.y_offset,
                    "bounds": bounds,
                }
            )
            x, y = x + pos.x_advance, y + pos.y_advance
        lines.append({"glyphs": glyphs, "advance": x})
    tt.close()
    return {
        "text": text,
        "engine": "HarfBuzz " + hb.version_string(),
        "lines": lines,
        "diagnostics": problems,
        "has_notdef": any(p["code"] == "notdef" for p in problems),
    }


def proof_outlines(font_bytes, preview):
    """Draw exactly the positioned glyphs from the compiled font, without fallback.

    Paths stay font-up. The browser flips Y explicitly for each placement. A
    shared path dictionary preserves counters and bounds response/DOM growth.
    """
    with TTFont(io.BytesIO(font_bytes)) as font:
        glyphs, paths, lines = font.getGlyphSet(), {}, []
        top, bottom = font["hhea"].ascent + 40, font["hhea"].descent - 40
        line_advance = font["hhea"].ascent - font["hhea"].descent + font["hhea"].lineGap
        overall_left, overall_right = 0, 100
        for line in preview["lines"]:
            x, y, placed = 0, 0, []
            left, right = 0, line["advance"]
            for glyph in line["glyphs"]:
                name = glyph["name"]
                if name not in paths:
                    pen = SVGPathPen(glyphs)
                    glyphs[name].draw(pen)
                    paths[name] = pen.getCommands()
                placed.append(
                    {"name": name, "x": x + glyph["x_offset"], "y": y + glyph["y_offset"]}
                )
                if glyph["bounds"]:
                    left = min(left, glyph["bounds"][0])
                    right = max(right, glyph["bounds"][2])
                x, y = x + glyph["x_advance"], y + glyph["y_advance"]
            overall_left, overall_right = min(overall_left, left), max(overall_right, right)
            lines.append(
                {
                    "glyphs": placed,
                    "baseline_offset": len(lines) * line_advance,
                    "view_box": [left - 40, -top, max(100, right - left + 80), top - bottom],
                }
            )
        if sum(map(len, paths.values())) > 2_000_000:
            raise ValueError("Proof outlines are too complex; reduce the project subset")
        return {
            "paths": paths,
            "lines": lines,
            "family_name": font["name"].getDebugName(1),
            "line_advance": line_advance,
            "view_box": [
                overall_left - 40,
                -top,
                overall_right - overall_left + 80,
                top - bottom + max(0, len(lines) - 1) * line_advance,
            ],
        }
