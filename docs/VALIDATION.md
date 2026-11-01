# Initial skeleton validation

Executed on 2026-11-01 on macOS arm64 with Python 3.12.13. The dependency set is recorded in `uv.lock`.

## Automated checks

The initial published commit `03e9b7b` passed **9 tests** in GitHub CI. The preserved pilot commit `6f2eb73` passed **11 tests** in GitHub CI. This continuation passes **15 tests** locally using `uv run --no-sync pytest -q`; its remote CI result is recorded separately by GitHub. These verify:

- JPEG EXIF orientation, asymmetric pixel orientation and both image hashes;
- corrected half-open crop bounds, stale revision rejection, split/merge ancestry and discarded parent state;
- exact Malayalam sequences including ZWJ/ZWNJ persisted without normalization;
- OCR TSV word suggestions retained as untouched, unconfirmed suggestions;
- traced ring counter retention, foreground/background separation and asymmetric shape orientation;
- a full upload → correct label → trace → edit metrics → compile TTF ZIP flow;
- UFO reopening, expected cmap, actual contour counts, baseline/Y flip, saved state and absence of photos in the export;
- exclusion of generated and unconfirmed forms and reporting of unencoded sequence dependencies;
- HarfBuzz substitution of `ക്ക`, direct atomic chillu `ൻ`, and disclosure of missing GPOS mark anchors;
- rejected invalid Hosts/Origins/tokens, oversized requests, unsafe SVG markup, open/nonfinite contours and out-of-page crops.
- real model fitting, style inference, checkpoint reload without pickle, and counter-preserving research normalization.
- persistent synthetic fixture provenance across split/merge, OCR, trace and reload; rejection of default fixture font exports and explicit labelling of test fonts, SVGs and metadata;
- preservation of the latest edited outline/metrics in a `before-retrace` history snapshot;
- explicit local tessdata configuration and actionable rejection of malformed/non-TSV OCR output.

The geometry fixtures are synthetic; test labels are assigned to exercise Unicode and font plumbing. These results do not measure Malayalam handwriting OCR accuracy, style fidelity or complete shaping quality.

`uv run --no-sync ruff check mashi tests`, `node --check mashi/static/app.js` and `git diff --check` pass. Dependency deprecation warnings remain in the pinned font compiler stack (`fs`/`pkg_resources`) and Starlette's AnyIO portal alias. The compatible setuptools version is pinned; removing that legacy dependency is future maintenance work.

## Installation and browser smoke test

Built and installed the package through `uv sync --locked --no-editable --extra dev --python 3.12`. Verified import, entrypoint and packaged UI assets from `/tmp`, outside the source tree. Non-editable installation avoids a hidden `.pth` metadata problem in this Mac's environment. The distribution explicitly includes only the `mashi` package and UI assets.

Playwright CLI could not start Google Chrome because it is not installed at the standard path. Used the connected in-app browser instead and exercised the actual loopback service:

1. Open studio; verify local OCR capability notice (initially unavailable; installed and tested during the continuation below).
2. Load synthetic practice shapes; review three connected-ink boxes.
3. Assign a test Malayalam label, confirm crop, save, trace ink and see the vector counter.
4. Download `Mashi-ttf.zip` through the UI. Inspect the actual downloaded ZIP: UFO sources, SVG, project metadata, coverage report and compiled TTF; expected U+0D15 cmap entry present.
5. Reload, reopen the saved project and save outline metrics successfully. Fixed a numeric input step mismatch found during this check.
6. Inspect desktop and 390 × 844 mobile layouts; document scroll width is 390 at viewport width 390. Restore the viewport afterward. Browser reports no console errors or warnings.

Local screenshots are in `output/browser/` (gitignored); they contain only synthetic fixture shapes. The test ZIP is in the Mac's Downloads folder. No personal handwriting was used or published. The local studio is the sole running service; no external deployment was made.

## Explicit limits

The continuation installed official Homebrew Tesseract **5.5.4** and pinned official `tessdata_fast` Malayalam data at commit `87416418657359cb625c412a48b6e1d6d41c29bd`, verified by SHA-256. The model and licence remain in the gitignored `.mashi/ocr/tessdata/`; a reproducible explicit setup script, [source manifest](experiments/ocr-source-manifest.json), Apache licence and [actual smoke-test results](experiments/ocr-smoke-results.json) are published.

`scripts/smoke_ocr.py` rendered മലയാളം, മഷി and കേരളം using HarfBuzz **15.0.0**, Noto Sans Malayalam default axes, 72 px text, 40 px margin and 20 px line space. The fixture font hash matches the audited pilot corpus. It uploaded this as a synthetic fixture and ran OCR through the local FastAPI endpoint: **3/3 expected printed words matched exactly**, with confidence values and half-open word boxes preserved. Every proposal remained unlabelled/unconfirmed and synthetic. This is one clean printed fixture; no handwriting/noise accuracy is established. `tessedit_create_tsv=1` is set explicitly so local language-only data folders need no separate `configs/tsv` file.

The original known local practice project was corrected to synthetic provenance during this continuation. Legacy projects created before source tagging cannot be classified safely from an unknown image alone; recreate older practice pages rather than assume they are handwriting. The browser check reopened the corrected project, displayed its persistent synthetic banner and blocked a font export while synthetic opt-in was unchecked. Local OCR capability appeared available and browser diagnostics were clear. Evidence is saved in `output/browser/studio-provenance.jpg`.

The small rendered-font completion pilot remains unchanged: see [COMPLETION.md](COMPLETION.md). No further corpus training was run during this continuation. It has no measured real-handwriting accuracy and is not enabled in the studio. At this historical checkpoint, shaping and anchors were incomplete; the later bounded typography integration is recorded below.

## Capture/editor increment: photo preparation

21 Python tests pass after adding synthetic perspective+rotation sampling, inverse transform/EXIF mapping, uneven-light adaptive cleanup with a retained ring counter, exact preparation restore, names/reopen metadata, noisy-upload manual fallback and prepared-image → trace → UFO export. The browser verified numeric corner edits persist, rotated preview/apply creates unconfirmed crops, restore recovers the prior labelled outline, and a named last page reopens after reload. Evidence: `output/browser/photo-preparation.jpg`. Source images stay immutable; cleanup is regenerated from source while geometric coordinate maps remain invertible. These fixtures are software checks, not handwriting-photo validation. Visual node editing is the next increment.

## Capture/editor increment: visual editing and recovery

23 Python tests and four Node geometry tests pass. The new cases verify saved-region history restoration, stale/cross-crop rejection, outer/counter grouping and winding, relative/smooth Bézier conversion, closing-anchor continuity and unsafe/open geometry rejection. Browser checks exercised a real Bézier-handle pointer drag; repeated arrow edits with focus retained; exact undo/redo; unsaved outline/crop recovery after reload; rejection of an older crop draft after a concurrent API save; decimal metric save/reopen; saved-history restoration; and zoom/pan without geometry changes. A synthetic TTF export retained two contours, an empty counter and filled ink at checked points. Evidence: `output/editor-smoke/report.json`, `output/browser/visual-outline-editor.jpg`, `output/browser/visual-outline-mobile.jpg`. The 390 px layout has document width 390, and browser diagnostics were empty. No real handwriting validation or model training was performed for this increment.

This checkpoint is published as `a850a9964a4e50145ef3498a76b3d72d4caeaa8b`; [its exact CI run](https://github.com/anima-regem/Mashi/actions/runs/41309842438) passed. The earlier photo-preparation checkpoint `6028659fb43fa227cb29a987be91ac920dc9cd65` also [passed CI](https://github.com/anima-regem/Mashi/actions/runs/41307290746).

## Application and reviewed typography integration

Merged reviewed typography commit `a9403fe7db5f6180e6d25be52fd16efa5b4e7edc` while preserving the capture/editor work. The combined checkout passes **115 Python tests and four Node geometry tests**, Ruff and diff checks. The original typography branch's 107-test result is historical, not the combined application's count. Five dependency deprecation warnings remain. See [TYPOGRAPHY.md](TYPOGRAPHY.md) for the bounded repertoire, actual HarfBuzz checks and limits; these tests do not establish universal Malayalam support or reader-level quality.

HarfBuzz is a pinned normal runtime dependency. A separate non-editable installation at `/tmp/mashi-runtime-venv`, without the dev extra, imported Mashi and `uharfbuzz==0.49.0` from `/tmp`, verified the packaged visual editor asset and confirmed pytest was absent. The installed `python -m mashi.ocr_setup` command verified the already-downloaded official Malayalam assets outside the source checkout. This setup command is now packaged with Mashi; it no longer depends on a checkout-only `scripts` module. No new OCR download or model training was needed for these checks.

The exact-text preflight/positioned-preview APIs are integrated as backend functions. Their proof-text UI, preview cache and final-export required-text controls remain the next application increment. Existing exports run the backend's supported-observation validation; they do not establish coverage for arbitrary user proof text that has not been supplied.
