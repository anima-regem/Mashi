# Mashi · മഷി

A local-first, open-source Malayalam handwriting-to-font studio. Photograph a page, correct the crops and labels, preserve the actual ink as closed vector outlines, and export editable font sources.

**This is an experimental first skeleton.** It builds a real SVG/UFO/TTF subset, not a complete Malayalam text font. A small CPU completion research model has been trained and evaluated separately; it is not enabled in the studio and no checkpoint is bundled. See [the experiment](docs/COMPLETION.md) and [coverage and limitations](#font-coverage).

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11–3.13; Python 3.12 is the tested version. The first setup downloads open-source dependencies. After setup, the core workflow works offline without API keys.

```sh
git clone https://github.com/anima-regem/Mashi.git
cd Mashi
uv sync --locked --no-editable --python 3.12
uv run --no-sync mashi
```

Open **http://127.0.0.1:8000**. The server binds only to loopback. Use `uv run --no-sync mashi --port 8001` for another port. No deployment or cloud service is required.

Without uv, create a Python 3.12 virtual environment and `python -m pip install .`, then `python -m mashi`. The uv lockfile is the reproducible installation path; pip uses the pinned direct requirements. This installs a normal package, including the UI assets. After editing source files, repeat `uv sync --locked --no-editable` to rebuild the installed app.

## What works

1. Upload JPEG/PNG/WebP (12 MiB, 16 megapixels maximum), or try the clearly marked synthetic practice page.
2. Review connected-ink proposals. **They are not identified letters.** Draw a crop, edit its exact pixel coordinates, merge checked regions, split at an explicit line, or discard a crop. Detached vowel marks often need merging.
3. Assign the exact Malayalam Unicode sequence and confirm it. Codepoints and joiners are shown and preserved; labels are never normalized silently.
4. Trace the selected pixels with a controllable ink threshold. Inspect the closed contours, including counters. Edit SVG path geometry, baseline, scale and advance width.
5. Export an SVG/UFO ZIP, or compile an experimental TTF ZIP. Each contains `coverage.json`, `project.json`, SVGs and reloadable UFO sources. Photos are not embedded in exports.

Saved edits and original image bytes stay in `.mashi/` in the working directory (gitignored). Restarting preserves projects. Set `MASHI_DATA_DIR` to choose another directory. Back up this directory to preserve originals, canonical pages, SQLite project history and traced outlines. Exports contain metadata, not the original photos; they are not complete project backups. To remove local data, stop Mashi and delete its data directory.

### Prepare a photographed page

Open **Prepare photo** to drag or enter four paper corners, correct perspective, rotate, reduce uneven lighting and preview fixed/adaptive thresholding. Boundary suggestions need visual review. Every adjustment regenerates from the preserved oriented source. Applying creates fresh unconfirmed crop proposals; **Restore previous preparation & crops** returns the exact previous image, labels and outlines. Geometry has forward/inverse transforms and every new crop records source/original polygons. Photometric cleanup is reversible by regenerating from preserved pixels, not by inverting thresholded pixels. Up to 20 earlier preparation states are retained.

Name a page using **Save name**. The last saved page reopens on reload; the local page chooser shows up to 50 named pages. Each upload is still one separate page/project. Multi-page font assembly and variant selection remain on the roadmap.

### Edit and recover an outline

The visual workbench lets you select a contour, drag nodes and Bézier controls, zoom/pan, compare source ink and adjust baseline/advance guides. Focus a point and use arrows (Shift: 10 pixels; Alt: 0.1). Undo/redo keeps up to 50 edits in the current loaded outline session. Save commits geometry and metrics; raw SVG paths remain under Advanced.

Unsaved crop forms and outline drafts stay in this browser's local storage and recover only when their region revision and image hash match. Older drafts are retained for download/review and never overwrite a newer saved state automatically. Browser drafts are not included in a `.mashi/` backup; save them or download their JSON. **Saved crop & outline history** restores an earlier saved state from the same image/provenance, preserving the state it replaces. Whole-project undo (including reversing split/merge/discard) remains future work.

### Optional Malayalam OCR

Install [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html), then explicitly fetch the pinned official [`mal` data](https://github.com/tesseract-ocr/tessdata_fast/blob/87416418657359cb625c412a48b6e1d6d41c29bd/mal.traineddata) from the repository root:

```sh
# macOS engine installation; use your system package manager on Linux.
brew install tesseract
uv run --no-sync python -m mashi.ocr_setup
```

The setup command verifies SHA-256 hashes and preserves the Apache 2.0 licence in `.mashi/ocr/tessdata/`. The app detects this local folder, or uses `MASHI_TESSDATA_DIR` if set, then falls back to system data when no local folder exists. `MASHI_DATA_DIR` also controls the default local OCR location. The studio never installs or downloads models automatically. Reload after setup. Standard Tesseract models work best on printed text and often fail on handwriting.

**Suggest words with OCR** runs the local CLI and adds TSV word boxes with confidence and untouched raw text. A word is not divided by character count. OCR never confirms or assigns a label automatically. Missing OCR produces an actionable message; manual selection and labeling remain available.

The local integration check recognized മലയാളം, മഷി and കേരളം in a clean HarfBuzz-rendered Noto Sans Malayalam fixture. This verifies printed-text data flow, not handwriting accuracy. See [the recorded OCR check](docs/experiments/ocr-smoke-results.json).

### Font coverage

- Only active, confirmed, labelled, traced regions with `observed` provenance are exported. Generated suggestions and unconfirmed crops are excluded.
- Built-in practice pages persist `synthetic-fixture` provenance across reload, crop edits, split/merge and OCR. They are excluded from normal font exports. An explicit test-export checkbox produces a synthetic-labelled ZIP, font family, glyph metadata and SVG metadata; it never claims the practice shapes are actual handwriting.
- The integrated typography V1 backend targets a bounded HarfBuzz `mlm2` repertoire: direct characters/chillus/digits, selected captured conjuncts and attached-vowel forms, legacy chillu aliases, and explicit joiner handling. Every required observed sample must exist. See [the exact repertoire and limits](docs/TYPOGRAPHY.md).
- HarfBuzz reorders pre-base and split vowels. Spacing vowel signs retain positive advance; the visible virama uses zero advance with adjustable estimated `abvm` anchors. These defaults require visual and Malayalam-reader review.
- Backend exact-text preflight reports missing samples and unsupported sequences without normalizing the original input. Verified TTF export checks actual glyph selection, positions and clipping. HarfBuzz is a normal runtime dependency; no test tooling is needed to run the app. The proof-text/preflight UI is the next application increment.
- General contextual consonant forms, mark stacks, historical repertoire and platform qualification remain incomplete. Compilation or passing synthetic tests does not establish reader-level quality or universal Malayalam support.
- Initial baseline and scale are estimates. Outlines need visual review. Perspective/rotation and lighting/adaptive preparation are available, but need review; their synthetic fixture checks do not establish robustness on real handwriting photographs.
- Duplicate confirmed labels must be resolved to one variant before export. Alternate forms and multi-page font assembly are future work.

## Engineering and research

Built with Python/FastAPI, SQLite, Pillow/OpenCV, VTracer **0.6.12**, ufoLib2, fontTools and fontmake. A small plain-JavaScript UI keeps installation simple and avoids external assets, analytics, CDNs and cloud fallback.

The workflow has three distinct stages: **capture** proposes image regions and OCR labels for human correction; **completion** is separate experimental research with explicit generated provenance; **font building** turns confirmed observed outlines into a dependency-checked font subset. Completion is not silently mixed into capture or export.

Extensive completion research now lives in **[Mashi-ML](https://github.com/anima-regem/Mashi-ML)**. Its [application integration contract](https://github.com/anima-regem/Mashi-ML/blob/main/docs/APP_INTEGRATION.md) and [audit](https://github.com/anima-regem/Mashi-ML/blob/main/reports/AUDIT.md) describe the experimental interface and limitations. Weights are not bundled here; no unrestricted generated-font licence is implied. See [Mashi's current roadmap](docs/ROADMAP.md) for implemented, prototype and missing product workflows.

We studied actual sources from Swathanthra Malayalam Computing and Santhosh Thottingal: [Chilanka](https://github.com/smc/Chilanka), [Manjari](https://github.com/santhoshtr/Manjari), and [Rachana](https://github.com/smc/Rachana). The findings separate editable source strokes, closed outlines, Unicode mapping, GSUB, GPOS and compilation. No reference font outlines or feature files are copied into generated fonts.

- [Source research and attribution](docs/RESEARCH.md)
- [Exact reviewed revisions, paths and hashes](docs/source-manifest.json)
- [Architecture, coordinates and security](docs/ARCHITECTURE.md)
- [Missing-letter research plan and provenance](docs/COMPLETION.md)
- [Validation record](docs/VALIDATION.md)

## Check the build

```sh
uv sync --locked --no-editable --extra dev --python 3.12
uv run --no-sync pytest -q
uv run --no-sync ruff check mashi scripts tests
node --check mashi/static/app.js
node --test tests/outline-geometry.test.cjs
```

Tests cover EXIF orientation/hashes, half-open crop bounds, revisions and split/merge ancestry, exact Malayalam/joiner persistence, OCR suggestion handling, counters and orientation, full image-to-TTF export, UFO reload, cmap/contours, selective HarfBuzz shaping, excluded generated forms, local input protections, and completion-model fitting/checkpoint reload.

## Licensing

The application is **MIT** so others can use, study, modify and distribute the studio. Uploaded handwriting remains subject to its owner's rights; Mashi does not assign a licence to your exported artwork. Upstream fonts, models and dependency licences are separate. The reviewed upstream font licence texts are preserved under `docs/research-licenses/` for attribution and research; this does not relicense them under MIT. No third-party font files, model weights or training corpus are bundled.
