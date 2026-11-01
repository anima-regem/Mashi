# Missing-letter completion: research boundary

**Current application integration:** the optional [Mashi-ML review workflow](LOCAL_COMPLETION.md) now uses the separate extensive experiment's existing format-2/3 checkpoints. It remains off by default, preserves generated lineage and requires explicit review/output choices. No retraining or weight redistribution occurred during application integration. The smaller pilot below is preserved historical research, not the runtime model or a handwriting benchmark.

**Status: a small CPU research pilot was trained on 2026-11-01.** It is separate from the studio UI; no checkpoint or font binaries are bundled in Git and no automatic completion is enabled in the app. This is preliminary rendered-font training, not extensive training or evidence of handwriting fidelity.

The implemented model in `mashi/completion.py` learns per-form signed-distance means and shared rank-2 font-style axes with PCA, then infers style weights from observed forms by ridge regression. Training used Chilanka, Manjari and Gayathri Regular: 3 families × 55 isolated forms. Noto Sans Malayalam was held out by family, with 10 forms observed and 45 withheld. Mean foreground IoU on those 45 forms was **0.703976**, versus **0.690513** for the mean-shape baseline; normalized SDF MAE was **0.063110**, versus **0.070922**. One held-out family is insufficient for broad quality claims.

The exact font revision, assets, hashes, split and licence paths are recorded in [the pilot corpus manifest](experiments/pilot-corpus-manifest.json); [the results](experiments/sdf-pilot-results.json) contain per-form metrics and the checkpoint hash. Exact reviewed licence texts are under `research-licenses/Pilot-*-OFL.txt`. The full local corpus is `data/pilot-corpus/`; the actual checkpoint and accompanying notices are `output/experiments/sdf-pilot/model.npz` and neighboring files. Both directories are gitignored. Reviewed OFL headers contain no additional Reserved Font Name declarations; preserve the notices and audit any later assets or outputs separately.

To reproduce after normal setup, run `uv run --no-sync python -m scripts.fetch_pilot_corpus` (explicit network download), followed by `uv run --no-sync python -m scripts.train_pilot` (local CPU only). The optional `--via-gh` acquisition flag uses existing authorized public-read GitHub access. To generate separate research suggestions from a confirmed local page, run `uv run --no-sync python -m scripts.suggest_pilot --project YOUR_PROJECT_ID --sequences അ,ഖ`. This command wrote two unconfirmed, `model-generated` SVG/raster suggestions in a synthetic-project smoke test. It does not modify or accept forms in the studio.

The pilot masks are isolated letters rendered at 160 px and normalized into a centered 52 px box on a 64 × 64 grid. This loses baseline/spacing; it includes no conjuncts or dependent marks. No real writers, photo noise, calibrated confidence or full shaping were evaluated. Extensive rendered-font work now lives in [Mashi-ML](https://github.com/anima-regem/Mashi-ML); its 96×64 baseline-aware contract differs from this historical pilot.

`Predictor.suggest(project, sequences)` and `UntrainedPredictor` preserve the initial research boundary. The current optional bridge is isolated in `ml_engine.py`, `ml_service.py` and `ml_capture.py`. It retains exact sequences, checkpoint/reference hashes, transforms and lineage. Normal exports exclude generated geometry even after acceptance; explicit generated-font export follows the [review and licence policy](LOCAL_COMPLETION.md).

## Further experiments

The linear SDF baseline above is implemented and measured. A reference-font affine adaptation remains a useful additional comparison, visibly labelled a template transformation. The next experiments need larger audited corpora and real consented handwriting; the current numerical result does not establish useful photo-to-handwriting completion.

Training material needs a manifest with the exact repository/release/commit, selected files and SHA-256s, full licence texts, reserved names, use/redistribution conditions, family/derivative lineage, rendering settings, Unicode/shaping sequence, split and acquisition date. Include all GSUB/GPOS dependencies needed for the chosen samples. The source research manifest is **not** a training dataset manifest.

Split by family and derivative lineage before training: variants and forks of one family cannot leak across train/validation/test. Hold out both entire source families and some observed forms. Evaluate at multiple sample counts with unseen writers, not only rendered fonts. Include simple copying/affine baselines, boundary error and counter topology, nearest-neighbor similarity/leakage checks, conjunct/chillu/mark HarfBuzz tests and human review by Malayalam readers. Rendered-font accuracy alone cannot establish handwritten-photo accuracy.

Store checkpoints, data manifests, transforms, seeds, evaluation outputs and model cards outside Git by default. Publish only when their licence obligations and claims have been reviewed. No paid compute, API service or external image transmission is required or enabled for this skeleton.

Some few-shot font-generation repositories mix permissive portions with inherited non-commercial code. Do not adopt FUNIT-derived MX-Font/LF-Font code on the assumption that a single MIT file licences the whole dependency chain. Start from audited code and dependencies suitable for the intended open-source project.

## Next milestones

1. Collect real consented handwriting examples and establish segmentation/recognition measurements.
2. Add perspective/shadow correction with invertible coordinate transforms, then an optional local handwriting-specific recognizer.
3. Design a Malayalam inventory with community review; add editable anchors, contextual substitutions, alternates and shaping fixtures for both script tags.
4. Expand the pilot corpus with audited family/derivative lineage, several held-out families and stronger baselines; coordinate extensive training separately.
5. Add a suggestion review workflow that clearly separates observed, generated, edited and explicitly accepted forms and preserves training/source attribution.
