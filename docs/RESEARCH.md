# Learning from Malayalam font engineering

Reviewed on 2026-11-01. [source-manifest.json](source-manifest.json) records immutable commits, Git blob identifiers and SHA-256 hashes of every inspected asset. The listed repositories are research references, not endorsements of Mashi.

## From curves to text

[Chilanka](https://github.com/smc/Chilanka/tree/cd1aee086f46c93c734276f971a86732176bf3ad) by Santhosh Thottingal and contributors is a particularly relevant handwriting reference. In `sources/svgs/ക.svg`, ka is an open cubic centreline with round caps and stroke width 130. That drawing is an editing representation, not a font-ready filled contour. The corresponding `sources/Chilanka-Regular.ufo/glyphs/k1.glif` maps U+0D15 and contains three closed contours with cubic on-curve and off-curve points. Simply inserting source SVG path commands into a font would lose the intended stroke thickness and counters.

Mashi therefore traces filled observed ink into closed contours. It does not estimate pen trajectories or reconstruct stroke order from a photograph. Counters, contour direction, simplification, baseline, side bearings and Y-axis conventions all matter separately from recognizing the label.

## A glyph is not a codepoint

Chilanka's `sources/features/lookups.fea` has a substitution from `k1 xx k1` to `k1k1` and another from `k1 u1` to `k1u1`. Conjuncts and vowel combinations are reached through GSUB sequences rather than direct Unicode cmap entries. Its `gpos.fea` specifies distinct base anchors for mark attachment. Replacing its outline geometry while keeping all anchors would misplace marks. Mashi must eventually design and validate anchors against each writer's geometry, not just transplant an entire FEA file.

The first exporter constructs only a small dependency-checked whole-sequence substitution. It preserves raw labels and joiners but does not claim full script shaping. `mlym`/`mlm2` are shaping versions, not orthography settings.

## Compilation and validation

Chilanka's inspected Makefile builds its UFO with fontmake to TTF/OTF, flattens components, uses fontTools for WOFF2, and provides HarfBuzz/FontBakery checks. Its older FontForge-oriented descriptions should not be mistaken for the current inspected build. Mashi follows the UFO → fontmake → TTF route while keeping SVG outlines and provenance available.

[Manjari](https://github.com/santhoshtr/Manjari/tree/ed820d791cc79f08e3602e25f150a371a5a9744b), also by Santhosh Thottingal and contributors, provides a related UFO build with multiple styles. Its build and source structure are useful for a later consistent family rather than generating unrelated forms one letter at a time.

[Rachana](https://github.com/smc/Rachana/tree/1eb2feae74a9245afc16e43799be8c8e9a98e609), designed by Hussain K H with Rachana Aksharavedi, SMC and other contributors, uses an older SFD/FontForge-oriented build. Its README describes an extensive traditional conjunct repertoire. This is evidence that a small set of isolated modern characters is insufficient to promise comprehensive Malayalam typography. Rachana is an engineering/reference repertoire here, not a mandatory runtime dependency.

## Licence record

The exact reviewed texts are preserved in [research-licenses](research-licenses/). Chilanka and Manjari carry SIL OFL 1.1 notices for their project authors. Their specific reviewed headers do not add a Reserved Font Name declaration. Rachana's reviewed notice describes the regular font as dual OFL 1.1 / GPLv3+ with font exception, and the bold font as OFL 1.1. Recheck the exact selected release, asset and notices before any later training or font derivative. These observations do not assign blanket permissions to model outputs.

No source glyphs, font binaries or complete OpenType feature tables from these projects are bundled with this application or silently mixed into a user's export. Attribution and reviewed licence text remain separate from Mashi's MIT application licence.

## Implementation consequences

Keep recognition, geometric tracing, glyph mapping and shaping as separate inspectable stages. Let the user correct whole forms and detached marks. Preserve every source-to-crop-to-vector link. Validate both geometry and real HarfBuzz output. For completion, require a licensed, audited corpus and held-out testing before calling anything trained or faithful to a writer.
