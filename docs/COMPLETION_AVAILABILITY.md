# Completion availability and alpha gates

This is an availability audit, not a new model evaluation or permission to distribute checkpoints. The application can execute actual local inference. A turnkey, useful completion engine for the requested single alpha is not yet qualified.

| Component | Verified availability | Remaining gate |
| --- | --- | --- |
| Mashi adapter and setup | Public source; explicit local profile validation, default-off startup, bounded inference and review/export provenance. No arbitrary browser path, code installation or model download. | Native setup/selection/retry/off/reopen qualification after manual Mac unlock. |
| Numerical runtime | Pinned NumPy/Pillow plus optional SciPy 1.16.3. Source installation and actual worker import/inference passed; a controlled worker import failure fails load safely and can be retried. | The `1f89cc81` native development bundle excludes SciPy. Rebuild with the completion extra; qualify frozen-worker libraries and dependency notices on a clean host. |
| Existing full format 2 | Local reviewed hash `01656906…80ea045`; contract validation is supported. Its training-template arrays are not loaded by the studio. | Not packaged or publicly distributed. Payload classification/delivery review remains open. |
| Existing template-free format 3 | Local reviewed hash `b5975fc1…26d95`; actual saved-profile setup inspected 698 sequences and PCA/mean capabilities, then inferred three candidates and built a synthetic generated-font export. | Removing template arrays did not establish blanket rights clearance for the learned payload. No download service or alpha bundle supplies it. |
| User-supplied checkpoint | A local owner can select an existing bounded format-2/3 NPZ and reviewed hash using source setup. Structure/runtime validation precedes the profile write; files stay external and are checked again for each inference. | A structurally valid unknown hash has unclassified source terms. Its suggestions may be inspected, but generated-font output remains blocked until a reviewed source/notice record exists. Loading or accepting a candidate is not license approval. |

Exact hashes, format/capability contract and source-notice registry are in [local completion](LOCAL_COMPLETION.md). No source glyph/template substitution was added. Profiles contain a path and hash, never arrays; imported project backups do not install models. Settings errors, absent dependencies and absent/changed checkpoints leave manual capture/export available. Environment overrides remain explicit and never silently modify saved settings.

## Quality and licensing remain separate

The frozen [Mashi-ML audit](https://github.com/anima-regem/Mashi-ML/blob/7b3f65680fb66be27a4c57593848fef75b884e76/reports/AUDIT.md) reports selected-model rendered-font macro IoU **0.3862**, versus **0.4070** for nearest-font retrieval; retrieval wins in all three tested families, covering only two held-out lineage groups. The scoring correction was disclosed after initial test inspection. This is not a fresh untouched handwriting evaluation. Correct scale/baseline and canonical digital renders are assumptions; photographs and individual handwriting do not automatically satisfy them. A software smoke with a synthetic ring cannot close writer/style or Malayalam-reader acceptance gates.

Application code and source dependency installation are independent of model-weight delivery. Keeping a user's existing checkpoint on their machine does not distribute it to another person or relicense it. It also does not settle whether a particular model or generated font can be shared. The project has not resolved a compliant distribution classification/package for the existing learned checkpoints and has no authorization to publish them. This is an unresolved review and release decision, not a demonstrated blanket ban on training or all weight redistribution.

For font outputs, the current project policy retains OFL source notices and uses OFL-1.1 for known-model generated fonts, following [SIL's AI/font FAQ 1.25–1.26](https://openfontlicense.org/ofl-faq/#1_25). The [official OFL text](https://openfontlicense.org/open-font-license-official-text/) addresses notices, modifications and Reserved Font Names. This output policy is separate from the unresolved checkpoint-delivery question. An explicit generated-font choice never changes generated geometry into observed handwriting, nor grants new rights in an unknown model. The application MIT license is not a replacement for those font/model terms.

## Next executable steps

1. Rebuild locally with the pinned completion runtime (no weights), inspect dependency notices and run a frozen-worker setup/inference smoke with the already-held local checkpoint. This is independent of public weight distribution; use isolated synthetic data and keep the artifact private.
2. After manual unlock, qualify native file selection, unavailable/error/retry, aligned-reference review, candidate edit/reject/accept, generated-output notices and off/reopen. PKG-004's native OCR checks remain blocked separately; do not bypass the lock.
3. Close LIC-003 with a reviewed, authorized model-delivery plan. A future checkpoint source, download or bundled model needs exact lineage/notice/classification review and explicit publication scope.
4. Freeze ML-003's writer/style protocol, obtain consented private data (ML-004), compare with retrieval/manual work and obtain reader review. Then decide whether completion is useful enough for the alpha, rather than inferring quality from successful execution.

The board's REL-004 gate remains blocked. No alpha, model download, trained weights, new training, signing purchase or security-settings change is part of this source milestone.
