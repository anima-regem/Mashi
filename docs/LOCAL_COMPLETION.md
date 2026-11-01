# Optional local completion

The studio can propose missing appearances with the existing Mashi-ML PCA model. This is an opt-in research adapter, not handwriting reconstruction. The published model underperforms nearest-font retrieval on rendered-font evaluation (macro IoU 0.3862 versus 0.4070); real handwriting accuracy is unmeasured. Review every result. No checkpoint, source font binary or template geometry is bundled, downloaded or trained by the studio.

## Setup and use

Install the optional pinned runtime once, then configure an existing checkpoint and its approved SHA-256 outside the browser:

```sh
uv sync --locked --no-editable --extra completion --python 3.12
MASHI_COMPLETION_CHECKPOINT="/absolute/path/inference-only-v3.npz" \
MASHI_COMPLETION_SHA256="your-approved-64-character-sha256" \
uv run --no-sync mashi
```

Dependency installation uses PyPI. Runtime inference stays offline. The browser cannot submit a filesystem path or upload a checkpoint; it can only choose the configured profile. Nothing loads automatically. Open **Suggestions for missing forms**, select the configured checkpoint and press **Load local checkpoint**. **Turn completion off**, cancellation or server restart disables inference. Saved proposals remain distinguishable from captured forms.

1. Choose up to 20 confirmed, traced references with distinct exact labels supported by the loaded inventory. Generated forms cannot be references.
2. Set the saved baseline and scale in the outline editor, preview the aligned reference canvases, and confirm them. Vectors are interpreted in the shared 1000-UPM font coordinate system and rasterized at 32 px/em onto 96×64 with baseline y=45. Ink is horizontally centered; width/advance remain separate metadata. Crops are never stretched to fit. Initial tracing metrics are estimates, not calibrated physical em measurements; adjust them before confirming alignment. Out-of-canvas inputs are rejected.
3. Enter 1–8 supported missing sequences, separated by commas, or copy supported missing samples from the proof check. Spaces around separators are removed; sequence codepoints and joiners are otherwise retained and displayed. Observed targets and existing non-rejected proposals cannot be overwritten.
4. Generate, compare each candidate with its aligned references, then accept, edit or reject it. Editing uses the existing visual outline workbench and resets review to pending. Acceptance changes review status only: provenance stays `model-generated` and `not_observed_in_photo: true`. Predictions may be empty, fragmented or unsuitable for tracing; these cannot be accepted. Capture a form manually when completion is unhelpful.
5. Normal proof/export continues to exclude all generated forms. **Include accepted generated glyphs in an OFL font** is a separate explicit choice. Rebuild the proof with that choice before TTF export. Changed reference crops invalidate generated font eligibility; reject and regenerate affected proposals.

VTracer converts a prediction's own raster into editable curves. If it cannot produce safe finite closed paths at this low resolution, an explicitly recorded `pixel-boundary/v1` fallback retains exact pixel edges and counters without smoothing. It can be visibly blocky. The canonical raster stays immutable; editable geometry uses its tight ink crop with an explicit translation, baseline `45 − crop_top` and unchanged 31.25 units/pixel. Removing the model's centering padding avoids inventing a large left bearing. A 50-unit left bearing and advance derived from reference metrics/ink width, bounded to 100–5000 units, are editable estimates, not predictions. No per-output height rescaling is performed.

## Adapter, profiles and limits

The adapter follows [Mashi-ML's pinned contract](https://github.com/anima-regem/Mashi-ML/blob/7b3f65680fb66be27a4c57593848fef75b884e76/docs/APP_INTEGRATION.md). Original PCA/mean arithmetic is adapted from that commit's MIT `model.py`; its notice is packaged as `licenses/ml/ENGINE-MIT.txt`. This avoids installing the original research project's incompatible full Python/rendering stack. SciPy 1.16.3 supplies the same EDT/SDF operation; existing application NumPy/Pillow/font pins remain unchanged. No fitting or model selection runs here.

Format 2 and template-free format 3 (`pca-inference-v1`) are supported. Capability flags reflect the payload: format 3 disables template capabilities. The studio exposes only PCA/mean and never loads template arrays or performs template substitution, even for format 2. A template method or template-diagnostic configuration is rejected. No residual is presented as a confidence probability.

The source registry binds these existing artifacts:

| Profile | SHA-256 |
| --- | --- |
| Original format 2 | `0165690674d47818bd66055cf66f7b8861bdbb557f964bea56154b33180ea045` |
| Existing template-free format 3 | `b5975fc1e9923e2ef460ebe2084c2c12e485008ddae17d5914ac06e2c7226d95` |

These are identities, not download links or redistribution permission. Unknown structurally valid checkpoints can be inspected locally, but have unclassified source terms and are blocked from font export. Adding a new exportable source requires a reviewed hash-bound source/notice record in application code, not a browser checkbox. Template removal does not clear learned-array rights.

Checkpoint validation checks the approved file hash, a 96 MiB compressed limit, 512 MiB total expanded limit, unique known ZIP members, bounded NPY headers, non-object dtypes, exact 96×64 array dimensions, finite float32 means/bases, label inventory, configuration and capability consistency. Loading uses `allow_pickle=False`; templates are inspected as headers only. One owned worker runs at a time, with BLAS threads limited to one and a 45-second deadline. Cancellation terminates only that request's worker. Project revision is checked before import; canceled late proposals stay rejected. The core manual workflow remains available if configuration, dependencies, loading, inference or tracing fails.

Generation metadata retains engine/adapter version, checkpoint hash/profile/capabilities/configuration, request/project revision, exact sequence, reference IDs/revisions/labels, vector and PNG hashes, crop/source polygons, canonical transform and rasterization/vectorization methods. Reference rasters remain local project assets for comparison. No source photograph or checkpoint is embedded in font ZIPs. Unsaved generated outline drafts also retain generated lineage.

## Generated-font terms

The [official OFL FAQ 1.25–1.26](https://openfontlicense.org/ofl-faq/) distinguishes generated font software from graphical output: fonts produced from OFL training inputs remain under OFL. This is separate from the unresolved classification/redistribution question for model weights. It is not a blanket prohibition on training.

Generated-font exports use OFL-1.1, retain the eight training-family notices and complete pinned corpus/source manifest, embed font licence/copyright metadata, and include `GENERATED-PROVENANCE.json`. Their filenames and effective family identify them as generated; source-family names are rejected as a conservative naming policy. Accepted generated glyphs retain their provenance in UFO glyph libs, SVG metadata and coverage/project reports. Synthetic tests retain synthetic identity as well. Generated SVG download requires accepted geometry with a known source mapping and embeds the source licence texts. Review rights in your own captured contributions before distributing the combined OFL font. The application licence remains MIT; it does not relicense model-derived fonts or weights.

## Reproduce the software smoke

```sh
uv sync --locked --no-editable --extra dev --extra completion --python 3.12
uv run --no-sync python -m scripts.smoke_completion \
  --checkpoint /absolute/path/to/approved.npz \
  --sha256 APPROVED_SHA256 --output output/new-completion-smoke
```

The output directory must be new. This runs actual inference with an original synthetic ring assigned a Malayalam label solely to test plumbing. It records every candidate, uses the first vectorizable one for a synthetic generated-font export, and preserves failures. It is not a glyph, handwriting or readability benchmark. Tests create their own tiny contract arrays; CI contains no learned checkpoint. Real-writer alignment, style fidelity and Malayalam-reader evaluation remain missing. The desktop artifact built from `1c5a8c16` predates this integration; no updated native bundle is claimed by these source/browser checks.
