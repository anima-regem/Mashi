# Mashi delivery roadmap

Baseline: `075a88ec` (15 automated tests). Status is evidence of implemented behavior, not an aspiration. Updated at each completed milestone.

| Area | Implemented | Prototype / limitation | Missing |
| --- | --- | --- | --- |
| Capture | Bounded raster upload, EXIF/alpha handling, hashes, crop drawing/coordinates, split/merge, exact sequence confirmation, local Malayalam OCR; perspective corners, rotation, illumination/adaptive preview and apply/restore with source polygons | OCR verified only on one clean printed fixture; preparation tested with synthetic transforms/lighting; connected ink is not letter segmentation | Real-photo quality evaluation and reliable automatic line deskew |
| Outline | Actual ink tracing, closed contours/counters; visual cubic/quadratic nodes/handles, zoom/pan, raster comparison, metric guides, session undo/redo, Advanced paths | No real-writer usability benchmark; no visual node insertion/deletion or automatic smoothing | Larger-contour usability work and typographic review |
| Projects | SQLite persistence; up to 20 pages per font, named pages/projects and last-page reopen; explicit sample choices shared by coverage/proof/export; saved typography; editable backup/fresh-ID import; exact legacy recovery; page-aware crop/outline drafts and saved-region restore | Undo/redo stack lasts for the loaded editor session; no page deletion/reorder or OpenType alternates; archive limits apply | General whole-project undo, guided batch work, real-writer workflow validation |
| Completion | Optional configured local format-2/3 loading, canonical reference review, real inference, per-candidate edit/accept/reject, retained lineage and explicit generated-font output | Published model underperforms retrieval; no measured writer fidelity; weights remain local/unclassified for redistribution; low-res pixel fallback may be blocky | Real-writer alignment/style/reader evaluation and improved learned quality |
| Font building | Bounded mlm2 backend; exact-text sample checks and compiled-outline proof UI; revision/options/text cache; name/metrics/anchor controls; proof-gated TTF export | Reader/platform/contextual coverage incomplete; cancel ignores results but does not stop a running compiler | Reader review and broader shaping |
| Privacy | Loopback, Host/Origin/token checks, local data, no cloud fallback | Same-user local processes remain trusted | Packaging/distribution hardening after product workflows settle |

## Completed capture/editor milestone

1. **Photo preparation — delivered.** Immutable original/oriented source; preview/apply perspective, rotation, illumination and thresholding; forward/inverse transforms and source/original crop polygons; fresh unconfirmed crops and exact prior-state restore. Synthetic perspective/rotated/uneven-light fixtures, inverse mapping, noisy-upload fallback and upload → prepare → crop → trace → export regression pass. Browser verified corner persistence, apply/restore, naming and last-page reopen. Evidence: `output/browser/photo-preparation.jpg`. No real handwriting-photo quality claim.
2. **Visual outline editing — delivered.** Pointer/key edits, node/control selection, zoom/pan, raster comparison, metric guides, 50-step session undo/redo and Advanced paths. Geometry tests preserve counter grouping/winding and closing handles. Browser verified dragging, repeated key edits/focus, undo/redo equality, decimal metrics, save/reopen and TTF export with a retained counter. Evidence: `output/browser/visual-outline-editor.jpg` and `output/editor-smoke/report.json`.
3. **Project continuity — delivered within the single-page scope.** Last-page/name reopening, unsaved crop/outline draft recovery, stale crop draft rejection after a concurrent save, downloadable drafts and visible saved-region restore. Browser verified a 390 px layout without horizontal overflow and no console diagnostics. Evidence: `output/browser/visual-outline-mobile.jpg`. Multi-page assembly and general project undo remain missing.

Each increment gets a coherent tested commit and CI verification. Preserve the existing `regions[].box` (working pixel coordinates) and `vector.paths/baseline/scale/advance` export interface; add source provenance alongside it. No model retraining, silent generated-glyph acceptance, external deployment or paid service is part of this milestone.

## Subsequent work

Guided capture sheets; reviewed batch operations; page deletion/reordering; OpenType alternate forms; visible general history restore; local handwriting-specific OCR evaluation; improved completion/writer evaluation; packaging and distribution updates. These remain missing until implemented and tested. Synthetic fixtures test software mechanics and are never handwriting validation.

## Multi-page projects and editable backup milestone

Delivered page-local capture/preparation/history, shared revision-bound variants and typography, and `.mashi.zip` backup/import with source-image disclosure and bounded staged validation. Old projects remain read-only until the first edit creates an exact recovery archive and atomically saves schema 2. Selection changes invalidate proof; alternatives and generated provenance stay separate. See [PROJECTS_BACKUPS.md](PROJECTS_BACKUPS.md) for acceptance criteria, migration and remaining limits. This source milestone needs its own native rebuild/QA; it does not update an already-built application bundle.

## Local completion review milestone

The bridge is off by default and has no automatic network/training/template substitution. It accepts only a configured hash-bound checkpoint and bounded supported inputs, runs isolated workers, previews baseline-aware reference alignment, preserves per-suggestion provenance and keeps normal exports observed-only. Explicit generated-font outputs retain OFL/source notices and a distinct generated identity. Actual old/full and template-free checkpoints generated matching three-target smoke rasters; GUI review/edit and a generated TTF download were tested with synthetic data. See [LOCAL_COMPLETION.md](LOCAL_COMPLETION.md) and the validation record. This is software integration evidence, not handwriting accuracy. The independently built desktop artifact pinned to `1c5a8c16` predates these additions and needs separate rebuild/native QA before claiming them in that artifact.

## Proof/export and interface milestone

Exact Unicode preflight, actual compiled glyph drawings, font settings and required-text export are delivered; see [PROOFING.md](PROOFING.md). Cache keys include project ID/revision, exact text, options and fixture inclusion. Late or canceled results cannot replace current review state. Crop creation and OCR now require project revisions; pixel requests can bind to expected hashes, and the client swaps raster and metadata together. The prior stale-preparation bug is reproduced and regression-tested. Promotional hero/taglines, version/local badges and filler footer are removed; functional navigation replaces the decorative workflow strip. Advanced shaping diagnostics are disclosed on demand.
