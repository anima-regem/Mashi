# Missing-letter completion: research boundary

**Status: no model has been trained. No reference font is bundled. No automatic missing-form generator is enabled.** The current coverage inventory asks for missing forms, rather than presenting invented strokes as photographed handwriting.

`Predictor.suggest(project, sequences)` is the local interface for future experiments. `UntrainedPredictor` gives a useful unavailable message. An implementation must return geometry, the requested exact sequence, provenance (`template-generated` or `model-generated`), source asset/checkpoint hashes, the style observations used, uncertainty and licence/lineage information. Generated forms must remain separate suggestions, never automatically accepted. The current exporter deliberately excludes all non-observed provenance, even when marked confirmed; future explicit acceptance requires its own reviewed policy and state.

## First experiment to evaluate

An inexpensive CPU baseline could render aligned glyph signed-distance fields across audited Malayalam fonts, learn low-rank per-glyph bases, infer a writer-style latent vector from observed forms with ridge regression, and synthesize missing distance fields. A reference-font affine adaptation is a simpler baseline, but would be visibly labelled a template transformation, not learned handwriting. Neither method is implemented or validated here.

Training material needs a manifest with the exact repository/release/commit, selected files and SHA-256s, full licence texts, reserved names, use/redistribution conditions, family/derivative lineage, rendering settings, Unicode/shaping sequence, split and acquisition date. Include all GSUB/GPOS dependencies needed for the chosen samples. The source research manifest is **not** a training dataset manifest.

Split by family and derivative lineage before training: variants and forks of one family cannot leak across train/validation/test. Hold out both entire source families and some observed forms. Evaluate at multiple sample counts with unseen writers, not only rendered fonts. Include simple copying/affine baselines, boundary error and counter topology, nearest-neighbor similarity/leakage checks, conjunct/chillu/mark HarfBuzz tests and human review by Malayalam readers. Rendered-font accuracy alone cannot establish handwritten-photo accuracy.

Store checkpoints, data manifests, transforms, seeds, evaluation outputs and model cards outside Git by default. Publish only when their licence obligations and claims have been reviewed. No paid compute, API service or external image transmission is required or enabled for this skeleton.

Some few-shot font-generation repositories mix permissive portions with inherited non-commercial code. Do not adopt FUNIT-derived MX-Font/LF-Font code on the assumption that a single MIT file licences the whole dependency chain. Start from audited code and dependencies suitable for the intended open-source project.

## Next milestones

1. Collect real consented handwriting examples and establish segmentation/recognition measurements.
2. Add perspective/shadow correction with invertible coordinate transforms, then an optional local handwriting-specific recognizer.
3. Design a Malayalam inventory with community review; add editable anchors, contextual substitutions, alternates and shaping fixtures for both script tags.
4. Assemble and audit a small lineage-labelled font corpus. Run and record the CPU completion experiment against basic baselines.
5. Add a suggestion review workflow that clearly separates observed, generated, edited and explicitly accepted forms and preserves training/source attribution.
