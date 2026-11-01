# Mashi delivery roadmap

Baseline: `075a88ec` (15 automated tests). Status is evidence of implemented behavior, not an aspiration. Updated at each completed milestone.

| Area | Implemented | Prototype / limitation | Missing |
| --- | --- | --- | --- |
| Capture | Bounded raster upload, EXIF/alpha handling, hashes, crop drawing/coordinates, split/merge, exact sequence confirmation, local Malayalam OCR; perspective corners, rotation, illumination/adaptive preview and apply/restore with source polygons | OCR verified only on one clean printed fixture; preparation tested with synthetic transforms/lighting; connected ink is not letter segmentation | Real-photo quality evaluation and reliable automatic line deskew |
| Outline | Actual ink tracing, closed contours/counters, SVG paths and metrics, pre-retrace snapshots | Editing requires raw path JSON | Visual nodes/Bézier handles, zoom/pan, raster comparison, edit undo/redo |
| Projects | SQLite persistence, names, recent 50 named pages, last-page reopen, optimistic revisions, visible preparation/crop restore | One uploaded page per project; other history is inspectable in JSON | Unsaved edit recovery, general history restore, multi-page single-font assembly, variant/duplicate selection, backup/import, batch work |
| Completion | Audited small CPU SDF pilot, checkpoint and held-out results | Separate CLI research; rendered isolated forms, no measured handwriting fidelity | Extensive training and explicit reviewed integration, owned by the separate ML task |
| Font building | SVG/UFO/experimental TTF subset, provenance and dependency checks | Full Malayalam positioning/shaping incomplete | Shaping/export milestone owned by a separate branch/task |
| Privacy | Loopback, Host/Origin/token checks, local data, no cloud fallback | Same-user local processes remain trusted | Packaging/distribution hardening after product workflows settle |

## Capture/editor milestone in progress

1. **Photo preparation — delivered.** Immutable original/oriented source; preview/apply perspective, rotation, illumination and thresholding; forward/inverse transforms and source/original crop polygons; fresh unconfirmed crops and exact prior-state restore. Synthetic perspective/rotated/uneven-light fixtures, inverse mapping, noisy-upload fallback and upload → prepare → crop → trace → export regression pass. Browser verified corner persistence, apply/restore, naming and last-page reopen. Evidence: `output/browser/photo-preparation.jpg`. No real handwriting-photo quality claim.
2. **Visual outline editing.** Select on-curve nodes and cubic/quadratic controls, drag or keyboard-nudge them, zoom/pan, compare the raster and outline, and adjust baseline/advance. Keep raw geometry under Advanced. Maintain closed contours and counter orientation. Acceptance: pointer and keyboard edits, undo/redo, save/reopen equality, ring-counter retention and a browser export flow.
3. **Project continuity.** Name/reopen a page and recover the last project plus unsaved edits safely; stale drafts must not overwrite newer server revisions. Acceptance: reload/recovery and stale-draft rejection, keyboard-labelled controls and mobile fit.

Each increment gets a coherent tested commit and CI verification. Preserve the existing `regions[].box` (working pixel coordinates) and `vector.paths/baseline/scale/advance` export interface; add source provenance alongside it. No model retraining, silent generated-glyph acceptance, external deployment or paid service is part of this milestone.

## Subsequent work

Multi-page font assembly; guided capture sheets; reviewed batch operations; project backup/import; visible general history restore; local handwriting-specific OCR evaluation; explicit completion review; shaping integration; packaging and distribution. These remain missing until implemented and tested. Synthetic fixtures test software mechanics and are never handwriting validation.
