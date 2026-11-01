# Font projects, samples and backups

One font project can hold up to 20 photographed pages. **Add page** appends to the open project; **Projects** returns to the project chooser. Switch pages with the Page selector and give each sheet a useful name. The project name identifies the saved work; the font family name is a separate typography setting.

## Samples used by the font

Every page retains its own image, preparation, crops, outlines and history. Preparing or restoring one page never prepares or restores another. Crop merging is restricted to the open page. Coordinates always refer to that page's current image; the source/original polygons and transforms remain attached to the sample.

An eligible, unique exact sequence is used automatically. When there are alternatives, **Font samples** requires an explicit choice. Alternatives remain editable in their original pages. The choice binds to page ID, sample ID, sample revision and vector hash. Editing or removing an explicitly chosen form clears the choice and blocks its use until another choice is saved. Removing an automatically used unique sample also requires an explicit replacement; Mashi never silently switches to an alternative. Editing the same unique, unchosen sample keeps that sample identity but invalidates the previous proof through the project revision.

Coverage, proof and export share the same resolver. Excluded synthetic/generated samples do not become eligible by being selected. Choosing a generated variant can therefore block an observed-only export until an observed variant is chosen again. Accepted generated forms retain their own page's reference checks, model/source obligations and generated origin. A generated output still requires its separate explicit export option. Alternatives are not emitted as OpenType stylistic alternates.

Exact labels remain separate, including different joiners and decomposed sequences. No normalization is applied. **Save proof and font settings** saves exact proof text, family, line metrics, spacing and anchor overrides with the project, across pages and restarts. A fresh proof is required after saved project changes. Unsaved browser drafts are page/sample/image/revision bound; proof drafts are shared by the font project and are superseded by a newer saved typography revision.

Completion references currently come from the open page only. Missing-target checks look across every page. The optional model remains off until explicitly loaded; project import never loads or embeds a model.

## Editable backup

**Project backup → Back up project** downloads a `.mashi.zip` file. It includes source photographs, current and referenced historical page images, all captured and generated samples, saved editing histories, sample choices, exact labels, model provenance/source notices and saved typography. Review before sharing: photographs and pending/rejected generated geometry are intentionally included in this editable backup. Model weights, executable code, browser drafts, OCR installations and unused/unreferenced asset files are excluded. Save or separately download unsaved drafts first.

**Import backup** validates the archive and opens a fresh font project. It preserves page/sample IDs inside the new project, image bytes/hashes, coordinate transforms and histories; it never overwrites the existing project. Imported provenance records are assertions from the archive, not independent proof of authorship or source rights. Existing generated-font rights gates still apply, and unknown-source geometry cannot enter a generated font merely because it was imported.

A font-export ZIP has a different purpose. Its `project.json` contains only selected exported current forms and source-page metadata; no photographs, alternatives or editing histories. It cannot be imported as an editable project backup.

The editable format is `mashi-editable-project`, archive version 1. It contains exact stored `project.json`, a SHA-256/byte-count manifest, bounded raster assets and the application's packaged source notices. The importer rejects unknown formats/schemas; traversal/absolute/duplicate/case-colliding paths; directories, symlinks/special files, encryption and unsupported compression; missing/unexpected files, wrong hashes and references; oversized/complex JSON, unsafe/open vector paths, invalid metrics/transforms and invalid/oversized rasters. ZIP directories are counted before allocation and each inflate read is limited to 64 KiB. No `extractall`, pickle, imported scripts or model execution is used.

Hashes detect corruption; they do not authenticate the sender. Version-1 imports require the current packaged source-notice catalog. A later catalog change will need an explicit compatibility migration.

Limits: 256 MiB compressed archive, 512 MiB declared/retained expanded data, 64 MiB per raster member, 4,096 members, 16 MiB project JSON, 16 megapixels per raster and 12 MiB per original upload. JSON also has depth/node/string limits. Very large histories may need fewer pages/samples to fit. One backup/import operation runs at a time. Validation happens in a staging directory; assets are published under a fresh UUID and the SQLite insert is committed atomically. On POSIX, files/directories are synced before that insert. A process/power interruption between asset publication and SQLite commit may leave an inaccessible orphan asset directory; it does not replace or partially import a visible project. Automatic orphan cleanup is not implemented.

## Existing single-page projects

Schema 2 stores `pages[]`, shared `typography`/`proof_text`, `sample_choices`, `selection_required` and project history. The API projects the explicitly selected page at its former root fields for existing capture/editor code, and carries `page_id`, page name and page revision. Page operations require a page ID when a project has several pages. The project revision covers changes on every page and invalidates cached proof results.

Opening/listing a schema-1 project creates only an in-memory view; reads do not save a schema change. Before its first successful edit, Mashi writes an exact legacy JSON plus referenced-assets recovery archive to `.migrations/<project-id>/<legacy-json-sha256>.mashi.zip`, syncs it, then performs an optimistic SQLite compare-and-swap. The project records both legacy-document and recovery-archive hashes. Backup failure prevents the migration write. Repeating the save does not migrate again, and a damaged existing recovery archive is rejected. Original IDs, image files and histories are preserved. Unsupported future schemas are rejected without writes.

Old synthetic projects may contain historical snapshots made before the demo-origin correction. Those historical claims remain intact for recovery, but cannot be restored as observed handwriting on a synthetic page. Current synthetic samples remain synthetic and excluded from ordinary font output.

Quit older Mashi processes before editing the same data folder with this version. Earlier versions cannot read schema 2. Import the recovery archive into this version to recover a separate project; the exact legacy JSON/assets remain available for deliberate offline recovery. This is not an automatic downgrade or a whole-project undo feature. The archive is a recovery copy of the first migration state, not a continuously updated backup.

## Acceptance and remaining limits

Automated checks cover exact legacy recovery/idempotence and failure, separate page transforms/restoration, explicit/stale choices, actual compiled metrics/selected provenance, generated exclusion and own-page references, backup round trips, future schemas, unsafe archives and bounded decompression. Browser QA uses original synthetic drawings to test upload/add/switch/prepare/trace/choose/proof/export/backup/import and responsive keyboard flows. These checks do not validate Malayalam legibility, handwriting capture quality or model style fidelity.

Page deletion/reordering, OpenType alternates, guided batch capture, general project undo and real-writer/reader validation remain future work. Native application bundles require a separate rebuild to receive this source milestone.
