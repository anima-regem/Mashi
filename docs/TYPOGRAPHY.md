# Malayalam typography V1

This milestone supplies a bounded shaping backend and export preflight. It does **not** establish that an exported handwriting font is linguistically or visually finished. Use the exact-text coverage result and the exported `coverage.json`, then review actual handwriting with Malayalam readers. Synthetic rectangles exercise the font machinery without claiming letterform quality.

## Repertoire and evidence

V1 targets HarfBuzz's `mlm2` Malayalam shaping path. `mlm2` and `mlym` are engine versions, not traditional/modern orthography selectors. Old `mlym` clients, CoreText, Windows applications and browser/platform combinations have not been qualified. The engine, rather than application string rewriting, performs visual vowel reordering.

Every form below is conditional on confirmed, traced, eligible samples being present. A codepoint, Unicode sequence and glyph are different objects. The existing broad predictor inventory is a capture wish list, **not** a shaping support claim.

Normal eligibility uses observed ink, with a separate synthetic-test opt-in. The optional [local completion adapter](LOCAL_COMPLETION.md) adds a distinct `include_generated=True` choice for accepted proposals with current references and verified source terms. Those forms retain generated provenance and OFL output terms; they must meet the same sequence dependencies, geometry, metrics and actual HarfBuzz checks. They do not extend this repertoire or establish letterform quality.

| Input class | V1 behavior | Required samples |
| --- | --- | --- |
| Independent vowels | Direct cmap | `അആഇഈഉഊഋഌഎഏഐഒഓഔൠൡ` as needed |
| Consonants | Direct cmap | `കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറ` as needed |
| Atomic chillus | Direct cmap | `ൺൻർൽൾൿ` as needed |
| Malayalam digits | Direct cmap | `൦൧൨൩൪൫൬൭൮൯` as needed |
| Right-side vowel signs | Positive advance, following base | Base and `ാ`, `ി`, `ീ`, or `ൗ` |
| Left-side vowel signs | HarfBuzz reorders sign before base | Base and `െ`, `േ`, or `ൈ` |
| Split vowel signs | HarfBuzz splits and reorders; accepts composed or decomposed input | `ൊ` needs `െ` + `ാ`; `ോ` needs `േ` + `ാ`; `ൌ` needs `െ` + `ൗ`, plus base |
| Attached vowel forms | Captured base+vowel substitution in `psts` | Base, vowel sign, and observed combined form for `ുൂൃൄൢൣ`; base can be a consonant, atomic chillu or supported conjunct |
| Visible chandrakala | Zero-advance virama with adjustable `abvm` mark-to-base anchors | Base and `്`; optionally an observed consonant+virama form, selected later by `haln` |
| Conjuncts | Observed full conjunct in `akhn` | `ക്ക ങ്ങ ച്ച ഞ്ഞ ട്ട ണ്ണ ത്ത ന്ന പ്പ മ്മ ല്ല ക്ഷ റ്റ ൻ്റ`, each plus all constituent codepoints |
| Legacy chillus | Exact `<base, virama, ZWJ>` selects the captured atomic chillu | `ണ→ൺ ന→ൻ ര→ർ ല→ൽ ള→ൾ`, plus base and virama |
| ZWNJ | Blocks conjunct; explicit visible virama remains | Nominal consonants and virama; engine supplies invisible control glyph |
| Syllable modifiers | Positive advance after base/vowel | `ം` or `ഃ` |
| Space and newline | Generated space advance; preview returns separate lines | No handwriting sample |

Standalone signs are encodable source glyphs, but are not declared valid standalone text. A captured `ൊ` alone does not make `കൊ` work without the split components: coverage asks for those components explicitly. Multi-codepoint samples do not get cmap entries; they get a GSUB rule only when their input glyphs exist and their sequence fits V1. Unsupported sequence observations remain in the UFO for inspection and appear in `unencoded_sequences`. Individual unsupported block characters may remain encoded, with an explicit warning; they never become supported text merely because they have cmap entries.

The machine-readable repertoire is the constants in `mashi/shaping.py`. `coverage.json.supported_forms` lists validated individual observations and generated legacy aliases for that particular export; it is not an enumeration of every composable phrase. `export_preflight(project, exact_text)` determines coverage for a proposed phrase.

## Backend interfaces for integration

Existing calls `make_ufo(project, include_fixture=False)` and `export_bundle(project, kind, include_fixture=False)` remain usable. New arguments are keyword-only. Supported archive formats remain `ufo` and `ttf`.

```python
from mashi.exporting import export_preflight, preview_project, export_bundle
from mashi.font_metrics import TypographyOptions

# Cheap: no compiler, file writes, normalization or project mutation.
coverage = export_preflight(project, "കൊക്ക്")
# coverage: text, exact codepoints, normalization {policy: preserve, nfc, nfd},
# supported, issues [{code, index, sequence, required_samples}], required_samples,
# rules, missing_sequence_components, unencoded_sequences, duplicate_labels.

options = TypographyOptions(
    family_name="My Malayalam Handwriting",
    ascender=1000, descender=-400, line_gap=100, space_advance=300,
    anchors={"ക": {"top": (550, 740)}, "്": {"_top": (70, 660)}},
)
# Compiler + real HarfBuzz positions. Cache by project revision and options;
# debounce callers, and run compilation off the request/UI event loop.
preview = preview_project(project, "കൊക്ക്", options=options)
# {coverage, metrics, preview: {text, engine, lines, diagnostics, has_notdef}}
# Each glyph: name, cluster, x/y_advance, x/y_offset, bounds.
# Coordinates are 1000-UPM, font-up. Clusters are Unicode scalar indexes,
# relative to each line, not UTF-8 bytes or JavaScript UTF-16 offsets.

# Reject missing/unsupported required text BEFORE export. TTF then verifies
# cmap, metrics, actual captured-form selection, .notdef and vertical bounds.
archive_bytes = export_bundle(project, "ttf", options=options,
                              required_text="കൊക്ക്")
```

Application integration makes pinned `uharfbuzz==0.49.0` a normal runtime dependency. The ordinary locked installation supports preview and verified TTF text without test tooling. If HarfBuzz is absent, ordinary TTF export records `shaping_validation.status = not_run` and a warning. `preview_project` and TTF export with `required_text` fail clearly rather than pretending to have verified shaping. UFO archives always record shaping as `not_run`; their preflight is coverage and geometry validation only.

Application integration now provides a proof panel, exact-text coverage, revision/options/text caching and required-text exports; see [PROOFING.md](PROOFING.md). `preview_project` also returns a `drawing` with paths extracted from the same compiled TTF and the actual HarfBuzz placements. The browser draws those paths with an explicit Y flip, without a substitute system font. Missing-glyph, overlap and clipping diagnostics remain separate from sample availability. Proof text/options persist per page in browser storage; exports retain the exact text/options and effective metrics. The shaping functions still do not mutate the region/vector schema. Synthetic examples require explicit inclusion and retain synthetic identity throughout.

Issue codes beginning `missing_` contain capturable `required_samples`. `unsupported_conjunct`, `unsupported_vowel_form`, `unsupported_joiner_sequence` (except the five supported legacy targets), `unsupported_character` and `orphan_sign` need a text change or future engineering; do not promise they can be fixed by collecting an arbitrary whole word. A legacy-chillu missing target is reported in its required samples. Duplicate labels must be resolved by keeping one confirmed variant. No empty project has supported font coverage.

## Metrics, geometry and diagnostics

The documented tracing transform is unchanged: `x_font = x_crop * scale + 50`, `y_font = (baseline - y_crop) * scale`. Crop coordinates remain canonical oriented image pixels; baseline remains crop pixels, scale is font units/pixel, advance is font units. This module uses a single 1000-UPM system; it never independently rescales glyph ink or invents outlines. It validates finite/ranged metrics, closed outline paths, nonempty ink bounds and positive rounded advances for spacing glyphs. Advances are rounded to integer font units for compilation.

Unicode mark category alone is insufficient for spacing decisions. Only the visible V1 virama has zero advance. The spacing vowel signs keep positive advances; attached vowels require their complete observed form. Default virama anchors are `base.top = (ink_right, ink_top + mark_gap)` and `virama._top = (ink_center_x, ink_bottom)`. These are adjustable geometry estimates, not calligraphic knowledge. Anchor overrides use exact labels and font-unit pairs. Unsupported names/roles and excluded labels fail validation. UFO anchors and GPOS use identical integer coordinates.

Ascender, descender, hhea, OS/2 typo and Windows metrics include both nominal ink and the maximum positioned virama extent, with 20 units of padding. USE_TYPO_METRICS is set; line gaps match. Metrics expand beyond requested bounds when necessary rather than clipping ink. Extreme outlines or positioned marks beyond ±16,000 units are rejected. The preview detects missing glyphs and vertical ink outside hhea bounds; adjacent ink bounding-box intersection is a review hint. Bounds intersection can be intentional and is not contour-level collision detection. Reports do not infer reader legibility from an absence of diagnostics.

V1 exports one Regular style; alternate weights/styles are rejected. Family/style names are bounded and reject controls; display names preserve Unicode and the PostScript name is sanitized to valid ASCII with a deterministic digest when needed to avoid collisions. Synthetic family identity cannot be replaced with a handwriting family through options. Real outlines keep the existing rights/provenance notice; this milestone grants no rights to handwriting the user does not own.

## Test corpus and limits of validation

`tests/fixtures/typography-v1.json` contains exact Unicode proof strings and expected glyph identities/advances. `tests/test_typography.py` creates original, deliberately rectangular synthetic ink. It is MIT-licensed application test data, not a copied font. Cases cover all supported conjunct rules, all attached-vowel rule types, five legacy chillus, atomic chillus, explicit ZWNJ, pre-base and split vowels, exact normalized/decomposed input preservation, mark offsets, intentional anchor adjustment, clipping/overlap diagnostics, line metrics, excluded model-generated ink, synthetic safeguards, missing components, duplicate labels and invalid metadata/geometry.

The automatic TTF gate shapes every declared supported observation, checks no unexpected `.notdef` or vertical clipping, and checks that every captured-sequence rule actually selects its intended output. The corpus verifies positions and advances too. Compilation alone is not a pass for script correctness.

Not yet validated or implemented: general `pref/rphf/blwf/pstf` contextual consonant forms; arbitrary multi-consonant sequences (including `സ്ത്ര`); dot reph and above/below mark stacks; mark-to-mark attachment; historical chillus/archaic signs/fractions; arbitrary joiner placement; legacy `ന്ര` equivalence and the ambiguous `<na, virama, ZWJ, rra>` stacked interpretation; cross-script text, punctuation, tab/CR layout; traditional-versus-reformed stylistic alternatives; kerning/reader-tuned spacing; cross-platform qualification. The ambiguous legacy sequence follows the simple chillu-plus-following-consonant interpretation and is not claimed equivalent to stacked `ൻ്റ`. No universal Malayalam support is claimed. OTF/WOFF2 remain deferred so the milestone stays focused on validated UFO/TTF behavior.

## Engineering sources and licensing

Consulted 2026-11-01; sources inform engineering, not bundled output geometry:

- [Unicode 17, section 12.9](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-12/): Malayalam encoding, vowel forms, current/legacy chillus and joiner distinctions.
- [Microsoft Malayalam OpenType development](https://learn.microsoft.com/en-us/typography/script-development/malayalam): shaping stages and feature responsibilities. V1 uses only the tested subset.
- [SMC Chilanka lookups](https://github.com/smc/Chilanka/blob/master/sources/features/lookups.fea): examples of captured conjunct/CV lookups and staged features.
- [SMC Chilanka GPOS](https://github.com/smc/Chilanka/blob/master/sources/features/gpos.fea): geometry-specific mark anchors, demonstrating why one generic borrowed anchor is insufficient.
- [SMC Chilanka source glyph](https://github.com/smc/Chilanka/blob/master/sources/Chilanka-Regular.ufo/glyphs/k1.glif): closed cubic UFO contour representation, inspected without copying it.
- [SMC Chilanka Makefile](https://github.com/smc/Chilanka/blob/master/Makefile): UFO/fontmake builds and HarfBuzz proofing.
- [Santhosh Thottingal's Manjari](https://github.com/santhoshtr/Manjari): broader font engineering/coverage reference, OFL 1.1. Existing local licence records are in `docs/research-licenses/`.

No SMC/Santhosh font outline, anchor coordinate set or feature file is copied into this implementation or its fixtures. Rules are generated from captured labels and the bounded documented Unicode grammar, not transplanted wholesale from those fonts. If future work imports their actual assets/rules, preserve the corresponding licence/copyright notices and check reserved-font-name and derivative-font obligations first. Existing repository licence records remain unchanged.

## Remaining typography roadmap

1. Collect licence-cleared real handwriting proof pages with Malayalam readers; tune sample baselines, spacing and anchors, and retain reader verdicts separately from automated checks.
2. Add specific contextual forms only alongside captured samples, explicit dependencies and expected HarfBuzz glyph/position tests. Prioritize `സ്ത്ര`, common post-base forms and modern legacy spelling compatibility.
3. Add upper/lower mark and mark-stack classes, then qualify clipping/collision behavior with dense real text.
4. Qualify browser/CoreText/Windows rendering against the same Unicode corpus; expand the repertoire only when those checks and reader review pass.
5. Add OTF/WOFF2 with round-trip shaping tests when export demand justifies the extra format surface.

## Validation snapshot (2026-11-01)

Local validation on Python 3.12.13 / HarfBuzz 11.0.1: **107 passed**, no failures or skips. The existing 15 application tests are included. Ruff, `node --check mashi/static/app.js`, and `git diff --check` passed. Five dependency deprecation warnings remain (Starlette/anyio and fontmake's fs/pkg_resources dependency); no project failure was suppressed. Commands used the existing pinned Mashi dependency environment read-only, with this isolated checkout as the working directory. No dependency or lockfile changes were made. [Draft PR #1](https://github.com/anima-regem/Mashi/pull/1) carries the GitHub CI results; match the check run to the reviewed branch commit.

Reader validation, platform rendering comparisons, historical repertoire and OTF/WOFF2 checks were **not run**. Their absence is a limitation, not a pass.
