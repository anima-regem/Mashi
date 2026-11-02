# Mashi · മഷി

A local-first, open-source Malayalam handwriting-to-font studio. Photograph a page, correct the crops and labels, preserve the actual ink as closed vector outlines, and export editable font sources.

**[Product task board →](docs/TASK_BOARD.md)** — priorities, acceptance checks, verified work, blockers and the next implementation task.

**This remains a research-stage studio.** It builds a real SVG/UFO/TTF subset, not a complete Malayalam text font. Optional local completion now has an explicit alignment/review workflow; it stays off until a configured checkpoint is loaded. No weights are bundled and no handwriting accuracy is established. See [local completion](docs/LOCAL_COMPLETION.md), [the preserved pilot](docs/COMPLETION.md) and [coverage limits](#font-coverage).

Source completion setup can validate and save a pointer to an existing external checkpoint, with missing-runtime/error/retry states and no automatic activation. [Availability and alpha blockers](docs/COMPLETION_AVAILABILITY.md) distinguish this working source path from native setup, useful handwriting results and permitted model delivery.

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
5. Enter exact proof text, check required samples and build its compiled preview. Review actual glyphs, missing forms and spacing; adjust the font name, metrics or anchors if needed.
6. Export an SVG/UFO ZIP or TTF ZIP with that proof text and settings. Each contains `coverage.json`, `project.json`, SVGs and reloadable UFO sources. Photos are not embedded in exports.
7. Add more pages to the same font project, choose between sample variants, and save an editable `.mashi.zip` backup. **Project backups include source photographs** and import into a fresh project.

Saved edits and original image bytes stay in `.mashi/` in the working directory (gitignored). Restarting preserves projects. Set `MASHI_DATA_DIR` to choose another directory. Use **Project backup** for a portable editable project; copying the entire data folder while Mashi is stopped is also possible. Font exports contain metadata, not the original photos; they are not complete project backups. To remove local data, stop Mashi and delete its data directory.

### Prepare a photographed page

Open **Prepare photo** to drag or enter four paper corners, correct perspective, rotate, reduce uneven lighting and preview fixed/adaptive thresholding. Boundary suggestions need visual review. Every adjustment regenerates from the preserved oriented source. Applying creates fresh unconfirmed crop proposals; **Restore previous preparation & crops** returns the exact previous image, labels and outlines. Geometry has forward/inverse transforms and every new crop records source/original polygons. Photometric cleanup is reversible by regenerating from preserved pixels, not by inverting thresholded pixels. Up to 20 earlier preparation states are retained.

Name the font project using **Save name**, then add/switch/rename individual sheets. Up to 20 pages share one font's exact sequence choices and saved typography. Duplicate eligible samples require an explicit variant choice in **Font samples**; changing that chosen sample requires choosing again. The last page reopens on reload, and **Projects** lists up to 50 saved font projects. See [projects, migration and editable backups](docs/PROJECTS_BACKUPS.md). Older projects migrate only on their first edit, after an exact recovery backup; quit older processes before sharing a data folder with this version.

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

In the studio, **Word recognition → Check again** distinguishes a missing engine, missing Malayalam data and a ready model. If only data is missing, **Add Malayalam data** explicitly fetches the pinned official assets without sending photos. **Use suggested text** copies a proposal for correction; labels remain unconfirmed until saved. See [recognition setup and correction](docs/RECOGNITION.md).

The setup command verifies SHA-256 hashes and preserves the Apache 2.0 licence in `.mashi/ocr/tessdata-874164186573/`. The prior `ocr/tessdata/` folder remains readable. `MASHI_TESSDATA_DIR` overrides data discovery; `MASHI_DATA_DIR` controls the application's default folder. No automatic downloads or engine installation occur. Standard Tesseract models work best on printed text and often fail on handwriting. A rebuilt native package still needs recognition qualification.

**Suggest words with OCR** runs the local CLI and adds TSV word boxes with confidence and untouched raw text. A word is not divided by character count. OCR never confirms or assigns a label automatically. Missing OCR produces an actionable message; manual selection and labeling remain available.

The local integration check recognized മലയാളം, മഷി and കേരളം in a clean HarfBuzz-rendered Noto Sans Malayalam fixture. This verifies printed-text data flow, not handwriting accuracy. See [the recorded OCR check](docs/experiments/ocr-smoke-results.json).

### Font coverage

- Normal exports include only active, confirmed, labelled, traced observed ink. Generated suggestions and unconfirmed crops are excluded. A separate explicit generated-font choice includes reviewed accepted proposals under OFL-1.1 with source notices; their generated provenance never becomes observed.
- Built-in practice pages persist `synthetic-fixture` provenance across reload, crop edits, split/merge and OCR. They are excluded from normal font exports. An explicit test-export checkbox produces a synthetic-labelled ZIP, font family, glyph metadata and SVG metadata; it never claims the practice shapes are actual handwriting.
- The integrated typography V1 backend targets a bounded HarfBuzz `mlm2` repertoire: direct characters/chillus/digits, selected conjuncts and attached-vowel forms, legacy chillu aliases, and explicit joiner handling. Every required eligible sample must exist; generated samples require the separate reviewed-output option. See [the exact repertoire and limits](docs/TYPOGRAPHY.md).
- HarfBuzz reorders pre-base and split vowels. Spacing vowel signs retain positive advance; the visible virama uses zero advance with adjustable estimated `abvm` anchors. These defaults require visual and Malayalam-reader review.
- The proof panel reports missing samples and unsupported sequences without normalizing the original input. Its drawing uses paths and positions from the actual compiled font, with no fallback font. UI TTF export requires a current supported preview; the server rechecks revision, proof text, settings, glyph selection and clipping. See [proofing and concurrency behavior](docs/PROOFING.md).
- General contextual consonant forms, mark stacks, historical repertoire and platform qualification remain incomplete. Compilation or passing synthetic tests does not establish reader-level quality or universal Malayalam support.
- Initial baseline and scale are estimates. Outlines need visual review. Perspective/rotation and lighting/adaptive preparation are available, but need review; their synthetic fixture checks do not establish robustness on real handwriting photographs.
- Duplicate confirmed labels require an explicit selected sample across pages. Coverage, proof and export use the same selection. Alternatives stay editable; they are not exported as OpenType stylistic alternates.

## Engineering and research

Built with Python/FastAPI, SQLite, Pillow/OpenCV, VTracer **0.6.12**, ufoLib2, fontTools and fontmake. A small plain-JavaScript UI keeps installation simple and avoids external assets, analytics, CDNs and cloud fallback.

The workflow has three distinct stages: **capture** proposes image regions and OCR labels for human correction; **completion** proposes missing appearances from aligned confirmed references; **font building** creates a dependency-checked subset. Optional completion has separate load, alignment, generation and per-candidate review controls. It never runs automatically or silently enters ordinary exports. The published model underperforms nearest-font retrieval on rendered-font tests; real handwriting quality is unmeasured. [Setup, provenance and output terms](docs/LOCAL_COMPLETION.md).

Extensive completion research now lives in **[Mashi-ML](https://github.com/anima-regem/Mashi-ML)**. Its [application integration contract](https://github.com/anima-regem/Mashi-ML/blob/main/docs/APP_INTEGRATION.md) and [audit](https://github.com/anima-regem/Mashi-ML/blob/main/reports/AUDIT.md) describe the experimental interface and limitations. Weights are not bundled here; no unrestricted generated-font licence is implied. See [Mashi's current roadmap](docs/ROADMAP.md) for implemented, prototype and missing product workflows.

We studied actual sources from Swathanthra Malayalam Computing and Santhosh Thottingal: [Chilanka](https://github.com/smc/Chilanka), [Manjari](https://github.com/santhoshtr/Manjari), and [Rachana](https://github.com/smc/Rachana). The findings separate editable source strokes, closed outlines, Unicode mapping, GSUB, GPOS and compilation. No reference font outlines or feature files are copied into generated fonts.

- [Source research and attribution](docs/RESEARCH.md)
- [Exact reviewed revisions, paths and hashes](docs/source-manifest.json)
- [Architecture, coordinates and security](docs/ARCHITECTURE.md)
- [Missing-letter research plan and provenance](docs/COMPLETION.md)
- [Validation record](docs/VALIDATION.md)

## Check the build

```sh
uv sync --locked --no-editable --extra dev --extra completion --python 3.12
uv run --no-sync pytest -q
uv run --no-sync ruff check mashi scripts tests
node --check mashi/static/app.js
node --test tests/*.test.cjs
```

Tests cover EXIF orientation/hashes, half-open crop bounds, revisions and split/merge ancestry, exact Malayalam/joiner persistence, OCR suggestion handling, counters and orientation, full image-to-TTF export, UFO reload, cmap/contours, selective HarfBuzz shaping, excluded generated forms, local input protections, and completion-model fitting/checkpoint reload.

## Licensing

The application is **MIT** so others can use, study, modify and distribute the studio. Uploaded handwriting remains subject to its owner's rights; Mashi does not assign a licence to your exported artwork. Upstream fonts, models and dependency licences are separate. The reviewed upstream font licence texts are preserved under `docs/research-licenses/` for attribution and research; this does not relicense them under MIT. No third-party font files, model weights or training corpus are bundled.
