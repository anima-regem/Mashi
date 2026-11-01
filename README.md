# Mashi · മഷി

A local-first, open-source Malayalam handwriting-to-font studio. Photograph a page, correct the crops and labels, preserve the actual ink as closed vector outlines, and export editable font sources.

**This is an experimental first skeleton.** It builds a real SVG/UFO/TTF subset, not a complete Malayalam text font. No missing-letter completion model has been trained or bundled. See [coverage and limitations](#font-coverage).

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11–3.13; Python 3.12 is the tested version. The first setup downloads open-source dependencies. After setup, the core workflow works offline without API keys.

```sh
git clone https://github.com/anima-regem/Mashi.git
cd Mashi
uv sync --locked --no-editable --extra dev --python 3.12
uv run --no-sync mashi
```

Open **http://127.0.0.1:8000**. The server binds only to loopback. Use `uv run --no-sync mashi --port 8001` for another port. No deployment or cloud service is required.

Without uv, create a Python 3.12 virtual environment and `python -m pip install '.[dev]'`, then `python -m mashi`. The uv lockfile is the reproducible installation path; pip uses the pinned direct requirements. This installs a normal package, including the UI assets. After editing source files, repeat `uv sync --locked --no-editable --extra dev` to rebuild the installed app.

## What works

1. Upload JPEG/PNG/WebP (12 MiB, 16 megapixels maximum), or try the clearly marked synthetic practice page.
2. Review connected-ink proposals. **They are not identified letters.** Draw a crop, edit its exact pixel coordinates, merge checked regions, split at an explicit line, or discard a crop. Detached vowel marks often need merging.
3. Assign the exact Malayalam Unicode sequence and confirm it. Codepoints and joiners are shown and preserved; labels are never normalized silently.
4. Trace the selected pixels with a controllable ink threshold. Inspect the closed contours, including counters. Edit SVG path geometry, baseline, scale and advance width.
5. Export an SVG/UFO ZIP, or compile an experimental TTF ZIP. Each contains `coverage.json`, `project.json`, SVGs and reloadable UFO sources. Photos are not embedded in exports.

Edits and original image bytes stay in `.mashi/` in the working directory (gitignored). Restarting preserves projects. Set `MASHI_DATA_DIR` to choose another directory. Back up this directory to preserve originals, canonical pages, SQLite project history and traced outlines. Exports contain metadata, not the original photos; they are not complete project backups. To remove local data, stop Mashi and delete its data directory.

### Optional Malayalam OCR

Install [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) and the [`mal` language data](https://github.com/tesseract-ocr/tessdata_fast/blob/main/mal.traineddata), then restart Mashi. `tesseract --list-langs` must include `mal`. Mashi performs no automatic installation or download. Standard Tesseract models work best on printed text and often fail on handwriting.

**Suggest words with OCR** runs the local CLI and adds TSV word boxes with confidence and untouched raw text. A word is not divided by character count. OCR never confirms or assigns a label automatically. Missing OCR produces an actionable message; manual selection and labeling remain available.

### Font coverage

- Only active, confirmed, labelled, traced regions with `observed` provenance are exported. Generated suggestions and unconfirmed crops are excluded.
- One codepoint maps to a cmap entry. A multi-codepoint observation is an unencoded glyph unless all of its component codepoints were also captured separately; then a small, self-contained `akhn` substitution is built for `mlym`/`mlm2`/DFLT.
- The tested conjunct is `ക്ക` with separately captured `ക` and `്`. Atomic chillu `ൻ` is also tested. These tests use synthetic outlines and verify plumbing, not handwriting recognition or typographic quality.
- No complete contextual substitution system, mark anchors, vowel positioning/reordering, traditional conjunct inventory, or joiner-sensitive shaping is implemented. Combining-mark widths are zero, but positioning still needs design. Whole-word labels are useful records, not a promise that a font can shape them.
- Initial baseline and scale are estimates. Outlines need visual review. Fixed thresholding needs clean, light paper; deskew, perspective correction and robust shadow removal are future work.
- Duplicate confirmed labels must be resolved to one variant before export. Alternate forms and multi-page font assembly are future work.

## Engineering and research

Built with Python/FastAPI, SQLite, Pillow/OpenCV, VTracer **0.6.12**, ufoLib2, fontTools and fontmake. A small plain-JavaScript UI keeps installation simple and avoids external assets, analytics, CDNs and cloud fallback.

We studied actual sources from Swathanthra Malayalam Computing and Santhosh Thottingal: [Chilanka](https://github.com/smc/Chilanka), [Manjari](https://github.com/santhoshtr/Manjari), and [Rachana](https://github.com/smc/Rachana). The findings separate editable source strokes, closed outlines, Unicode mapping, GSUB, GPOS and compilation. No reference font outlines or feature files are copied into generated fonts.

- [Source research and attribution](docs/RESEARCH.md)
- [Exact reviewed revisions, paths and hashes](docs/source-manifest.json)
- [Architecture, coordinates and security](docs/ARCHITECTURE.md)
- [Missing-letter research plan and provenance](docs/COMPLETION.md)
- [Validation record](docs/VALIDATION.md)

## Check the build

```sh
uv run --no-sync pytest -q
uv run --no-sync ruff check mashi tests
node --check mashi/static/app.js
```

Tests cover EXIF orientation/hashes, half-open crop bounds, revisions and split/merge ancestry, exact Malayalam/joiner persistence, OCR suggestion handling, counters and orientation, full image-to-TTF export, UFO reload, cmap/contours, selective HarfBuzz shaping, excluded generated forms, and local input protections.

## Licensing

The application is **MIT** so others can use, study, modify and distribute the studio. Uploaded handwriting remains subject to its owner's rights; Mashi does not assign a licence to your exported artwork. Upstream fonts, models and dependency licences are separate. The reviewed upstream font licence texts are preserved under `docs/research-licenses/` for attribution and research; this does not relicense them under MIT. No third-party font files, model weights or training corpus are bundled.
