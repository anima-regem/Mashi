# Word recognition and correction

Open **Word recognition** after uploading a page. It checks the installed recognition engine and Malayalam data. **Check again** refreshes readiness without changing your project or downloading anything. Manual crop creation, labeling, tracing and font export remain available when recognition is missing or fails.

If the engine is present but Malayalam data is missing, **Add Malayalam data** explicitly downloads about 5.3 MB from the official Tesseract repository. It sends no photos or project text. The app checks pinned SHA-256 hashes, keeps the Apache 2.0 notice and publishes the complete data directory only after both files verify. Failed download/verification leaves existing data untouched; retry after checking connection and free space. The engine itself is not installed by this button. Follow [Tesseract's official installation guidance](https://tesseract-ocr.github.io/tessdoc/Installation.html) if the engine is absent, then check again.

1. Choose **Suggest word labels**. New proposals are word regions with empty, unconfirmed labels. Existing samples are retained. Save or discard a pending crop correction first.
2. Inspect each proposed rectangle against the photo. **Use suggested text** copies the exact raw text into the label field and clears confirmation. It does not save a label. Correct the text and crop bounds yourself. Discard incorrect proposals; merge detached marks or split a region only after inspecting the ink. A word box is not character segmentation.
3. Confirm the visible form and exact sequence, then **Save label & crop**. Only then trace the saved pixels. Recognition confidence is not a probability that the handwriting was read correctly and is not shown as a percentage.
4. Inspect/edit the resulting outline, save it and build a proof. Export validates the required text again. Save proof and font settings for another session. Unsupported contexts still require more samples or shaping work; collecting an arbitrary word does not implement general Malayalam shaping.

Tesseract is intended primarily for printed text. Handwriting may be missed or misread. Neither the printed checks nor a successful font compilation establishes handwriting accuracy or Malayalam-reader acceptance. Missing-form completion is a separate [optional review workflow](LOCAL_COMPLETION.md).

## Developer setup and diagnostics

The current application source implements these controls. The core development bundle recorded at `f08fd848` predates them and excludes Tesseract/data. PKG-004 remains open until a rebuilt native application qualifies this setup and correction flow. No integrated alpha is released; see the [alpha gates](TASK_BOARD.md#one-integrated-alpha).

```sh
uv run --no-sync python -m mashi.ocr_setup
```

Default verified data lives at `$MASHI_DATA_DIR/ocr/tessdata-874164186573/` (`.mashi` for the source studio). The previous `ocr/tessdata/` location remains a read-compatible fallback. An explicit trusted `MASHI_TESSDATA_DIR` takes precedence; the browser cannot select an arbitrary filesystem path or execute an installer. Setup is disabled for an explicit external directory. Immutable existing managed data is never overwritten: preserve/move an invalid directory for diagnosis before retrying setup. Do not remove project folders or their database.

`GET /api/ocr/status` reports `missing-engine`, `missing-data`, `engine-error`, `data-error` or `ready`. Readiness lists `mal` and verifies the model initializes with `--print-parameters`, rather than assuming a filename proves it loads. All checks are local with bounded subprocess timeouts. `POST /api/ocr/setup` requires the local mutation token and installs only the pinned data at a configured application-owned location. It has a per-instance setup lock. It does not accept a browser-supplied install destination. The two official asset hashes, source commit and license are recorded in the setup manifest; see [the pinned source record](experiments/ocr-source-manifest.json).

OCR uses Tesseract TSV word boxes, as described by the [official CLI documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html). Image paths are canonicalized before invoking the native reader. Only the TSV stream is decoded as UTF-8; native diagnostics are discarded, never substituted into text or returned to the UI. Raw text and joiners are retained without normalization. Empty results do not write a project revision; a changed project rejects late results. Coordinates/confidence/row count and total crop count are bounded before persistence.

Source regressions cover corrupted model load, explicit setup, pinned hashes, interrupted/oversized downloads, existing-directory/symlink refusal, retry, malformed TSV, canonical image aliases, pending/stale edits, exact joiners and correction through actual synthetic font export/reopen. [Validation](VALIDATION.md#recognition-readiness-and-correction) separates the live printed fixture from these software fixtures and from still-missing real handwriting/reader evidence.
