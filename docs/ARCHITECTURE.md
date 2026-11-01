# First vertical slice

`mashi/imaging.py` validates and orients raster bytes, composites transparency on white and proposes connected ink. `ocr.py` wraps a local optional Tesseract process. `store.py` stores project documents in SQLite with atomic project revision checks. `app.py` exposes the loopback API. `tracing.py` isolates dark pixels, traces alpha-masked ink, flattens tracer translations and validates geometry. `exporting.py` converts those same paths to UFO glyphs and invokes fontmake for TTF. `predictors.py` defines the completion boundary and an honest unavailable state.

## Coordinates and lineage

- Keep original bytes and their SHA-256. Decode and EXIF-orient once. Store a separate SHA-256 for the RGB canonical PNG, the original dimensions and orientation, and the ordered transformation log.
- Every region uses **canonical oriented image pixels**, top-left origin, half-open `[x0,y0,x1,y1)` bounds. Display resizing affects only the canvas. There is currently no deskew/perspective transform to reverse.
- Each region has a random ID, independent revision, active flag, exact label, confirmation, source, provenance, optional OCR word suggestion and optional vector. SQLite retains inactive split/merge parents, discarded regions and before-edit snapshots. Stale region revisions are rejected.
- Splitting creates two unconfirmed, unlabelled children. Merging creates an unconfirmed, unlabelled bounding-box union. A bounding-box union can include neighboring ink; the user must inspect and correct it. Neither operation reuses a possibly misleading vector or inferred label.
- Crop edits invalidate traced vectors. Label changes are explicitly saved with confirmation. Re-tracing replaces the active vector; earlier edit snapshots remain in history. Concurrent project updates use optimistic revision checks.
- Geometry is local crop coordinates. Export applies `x_font = x_crop * scale + 50`, `y_font = (baseline - y_crop) * scale`. The explicit Y flip maps image-down to font-up. The baseline remains adjustable in crop pixels; scale is font units per pixel; advance is font units. UPM is 1,000.
- Trace provenance includes threshold, VTracer version and edited status. Font glyph libs include region/revision, exact sequence, canonical image hash, crop and edit status.

## Unicode and shaping

Labels accept Malayalam block codepoints plus ZWJ/ZWNJ, up to 32 codepoints. No normalization is performed. The UI exposes the exact sequence. OCR text is a separate untouched suggestion; user correction is required even if recognition appears plausible. A connected component, codepoint, grapheme cluster and font glyph are different entities.

Confirmed single-codepoint forms receive cmap entries. Whole-sequence observations may receive an `akhn` rule only when all referenced input glyphs exist. Longer sequences are ordered first. Every emitted glyph reference is locally constructed and validated. No complete FEA is borrowed from a reference font. `mlym` and `mlm2` identify shaping-system versions; they do not select traditional versus modern orthography.

The current exporter cannot infer correct mark anchors, contextual forms or all script-specific reordering. Its coverage report is the source of truth; successful font compilation alone is insufficient evidence of usable Malayalam shaping.

## Local security and privacy

The provided CLI binds `127.0.0.1`. Host validation allows localhost/127.0.0.1, same-origin checks reject external Origins, and every mutation needs a random process token read from the same-origin session endpoint. There is no permissive CORS. CSP restricts resources to this app, disallows embedding and plugins, and the app loads no remote scripts, fonts or analytics. No cloud provider is called by the application. Loopback is not a defence against other programs running as the same local user.

Byte and decoded-pixel limits apply before tracing. Only JPEG/PNG/WebP rasters are accepted. Storage paths use generated UUIDs and internal filenames; supplied paths and filenames are never opened. No uploaded SVG is accepted. Vector edits accept a bounded list of SVG geometry strings, validated as closed finite contours; markup, scripts, external references and foreign objects cannot pass. XML exports are built with ElementTree. OCR and font compilation use argument lists, never shell interpolation, with timeouts.

`.mashi/`, photos, environments, caches and model checkpoints are excluded from Git. ZIP exports contain glyph geometry and project metadata, including labels, coordinates, hashes and edit history; users should review that metadata before sharing. There is no telemetry, automatic cloud fallback or API-key requirement. A future BYOK feature must ask for explicit image-upload opt-in before sending photographs anywhere.
