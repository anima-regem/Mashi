# Mashi delivery roadmap

Baseline: `075a88ec` (15 automated tests). Status is evidence of implemented behavior, not an aspiration. Updated at each completed milestone.

| Area | Implemented | Prototype / limitation | Missing |
| --- | --- | --- | --- |
| Capture | Bounded raster upload, EXIF/alpha handling, hashes, crop drawing/coordinates, split/merge, exact sequence confirmation, local Malayalam OCR; perspective corners, rotation, illumination/adaptive preview and apply/restore with source polygons | OCR verified only on one clean printed fixture; preparation tested with synthetic transforms/lighting; connected ink is not letter segmentation | Real-photo quality evaluation and reliable automatic line deskew |
| Outline | Actual ink tracing, closed contours/counters; visual cubic/quadratic nodes/handles, zoom/pan, raster comparison, metric guides, session undo/redo, Advanced paths | No real-writer usability benchmark; no visual node insertion/deletion or automatic smoothing | Larger-contour usability work and typographic review |
| Projects | SQLite persistence, names, recent 50 named pages, last-page reopen; crop/outline draft recovery with stale-state protection; visible preparation and saved-region history restore | One uploaded page per project; undo/redo stack lasts for the loaded editor session | General whole-project undo, multi-page single-font assembly, variant/duplicate selection, backup/import, batch work |
| Completion | Audited small CPU SDF pilot; extensive research and reproducibility work published separately in [Mashi-ML](https://github.com/anima-regem/Mashi-ML) | Separate experimental CLI; no measured handwriting fidelity; local weights are not bundled or blanket-cleared for redistribution | Explicit reviewed application integration and writer evaluation |
| Font building | Reviewed typography V1 backend merged: bounded mlm2 repertoire, anchors/metrics, exact-text preflight and HarfBuzz validation APIs | Reader/platform/contextual coverage incomplete; proof text is not yet wired into the UI | Cached proof preview/preflight controls, final-export proof gating, reader review, broader shaping |
| Privacy | Loopback, Host/Origin/token checks, local data, no cloud fallback | Same-user local processes remain trusted | Packaging/distribution hardening after product workflows settle |

## Completed capture/editor milestone

1. **Photo preparation — delivered.** Immutable original/oriented source; preview/apply perspective, rotation, illumination and thresholding; forward/inverse transforms and source/original crop polygons; fresh unconfirmed crops and exact prior-state restore. Synthetic perspective/rotated/uneven-light fixtures, inverse mapping, noisy-upload fallback and upload → prepare → crop → trace → export regression pass. Browser verified corner persistence, apply/restore, naming and last-page reopen. Evidence: `output/browser/photo-preparation.jpg`. No real handwriting-photo quality claim.
2. **Visual outline editing — delivered.** Pointer/key edits, node/control selection, zoom/pan, raster comparison, metric guides, 50-step session undo/redo and Advanced paths. Geometry tests preserve counter grouping/winding and closing handles. Browser verified dragging, repeated key edits/focus, undo/redo equality, decimal metrics, save/reopen and TTF export with a retained counter. Evidence: `output/browser/visual-outline-editor.jpg` and `output/editor-smoke/report.json`.
3. **Project continuity — delivered within the single-page scope.** Last-page/name reopening, unsaved crop/outline draft recovery, stale crop draft rejection after a concurrent save, downloadable drafts and visible saved-region restore. Browser verified a 390 px layout without horizontal overflow and no console diagnostics. Evidence: `output/browser/visual-outline-mobile.jpg`. Multi-page assembly and general project undo remain missing.

Each increment gets a coherent tested commit and CI verification. Preserve the existing `regions[].box` (working pixel coordinates) and `vector.paths/baseline/scale/advance` export interface; add source provenance alongside it. No model retraining, silent generated-glyph acceptance, external deployment or paid service is part of this milestone.

## Subsequent work

Cached exact-text proof preview and required-text export controls; multi-page font assembly; guided capture sheets; reviewed batch operations; project backup/import; visible general history restore; local handwriting-specific OCR evaluation; explicit completion review; packaging and distribution. These remain missing until implemented and tested. Synthetic fixtures test software mechanics and are never handwriting validation.
