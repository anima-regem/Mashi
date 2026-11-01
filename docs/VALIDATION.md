# Initial skeleton validation

Executed on 2026-11-01 on macOS arm64 with Python 3.12.13. The dependency set is recorded in `uv.lock`.

## Automated checks

`uv run --no-sync pytest -q`: **11 passed**. These verify:

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

The geometry fixtures are synthetic; test labels are assigned to exercise Unicode and font plumbing. These results do not measure Malayalam handwriting OCR accuracy, style fidelity or complete shaping quality.

`uv run --no-sync ruff check mashi tests`, `node --check mashi/static/app.js` and `git diff --check` pass. Dependency deprecation warnings remain in the pinned font compiler stack (`fs`/`pkg_resources`) and Starlette's AnyIO portal alias. The compatible setuptools version is pinned; removing that legacy dependency is future maintenance work.

## Installation and browser smoke test

Built and installed the package through `uv sync --locked --no-editable --extra dev --python 3.12`. Verified import, entrypoint and packaged UI assets from `/tmp`, outside the source tree. Non-editable installation avoids a hidden `.pth` metadata problem in this Mac's environment. The distribution explicitly includes only the `mashi` package and UI assets.

Playwright CLI could not start Google Chrome because it is not installed at the standard path. Used the connected in-app browser instead and exercised the actual loopback service:

1. Open studio; verify local OCR capability notice.
2. Load synthetic practice shapes; review three connected-ink boxes.
3. Assign a test Malayalam label, confirm crop, save, trace ink and see the vector counter.
4. Download `Mashi-ttf.zip` through the UI. Inspect the actual downloaded ZIP: UFO sources, SVG, project metadata, coverage report and compiled TTF; expected U+0D15 cmap entry present.
5. Reload, reopen the saved project and save outline metrics successfully. Fixed a numeric input step mismatch found during this check.
6. Inspect desktop and 390 × 844 mobile layouts; document scroll width is 390 at viewport width 390. Restore the viewport afterward. Browser reports no console errors or warnings.

Local screenshots are in `output/browser/` (gitignored); they contain only synthetic fixture shapes. The test ZIP is in the Mac's Downloads folder. No personal handwriting was used or published. The local studio is the sole running service; no external deployment was made.

## Explicit limits

Tesseract and `mal` are not installed on this Mac, so an actual Malayalam OCR inference was **not** run. The adapter's word-suggestion handling and unavailable-capability path were exercised; recognition accuracy is unknown. A small rendered-font completion model was trained and evaluated separately: see [COMPLETION.md](COMPLETION.md) and the recorded experiment assets. It has no measured real-handwriting accuracy and is not enabled in the studio. Full Malayalam shaping, anchors and typographic quality remain unverified and incomplete. The GitHub workflow runs the same automated checks on Linux; its result is recorded by GitHub separately from these local checks.
