# Mashi task board

This is the durable execution board for making Mashi a usable Malayalam font-creation application. Updated 2026-11-02. [Roadmap](ROADMAP.md) gives the overview; [validation](VALIDATION.md) records what actually ran. IDs stay stable when tasks move. Split large tasks before implementation; do not turn a prototype or synthetic test into a handwriting-quality claim.

GitHub Projects inspection returned `missing required scopes [read:project]`. No credentials/scopes were changed. This repository board is authoritative; a native board is optional and does not block work.

## Working rules and current iteration

- Status is **Todo**, **In progress**, **Blocked** or **Done**. P0 protects the first successful font or release; P1 improves frequent work; P2 extends capability.
- Done requires the stated acceptance checks and linked evidence. Local implementation evidence and exact remote CI are distinct. Release qualification also requires the native/clean-host gates below.
- Take one small unblocked task at a time. Record a specific blocker and continue independent work. Use isolated synthetic QA data; preserve projects/workloads. Keep photos and weights out of Git. Do not publish a binary, buy signing/services, widen credentials or change DNS as a routine task.
- Use existing standard public runners only. Inspect a failed run before retrying; no billed runner, artifact-storage or billing changes are authorized. Keep developer commands in GitHub documentation, not ordinary studio screens.
- **Closed iteration: GOV-001, FLOW-002, DOC-001.** Tracing now waits for the displayed crop/label/confirmation to be saved, and recovered/invalid drafts cannot trace previous pixels. The quiet precision-tool layout gains only contextual action guidance. [Iteration evidence](VALIDATION.md#task-board-and-capture-readiness). Applied [unslop-ui-design](https://github.com/anima-regem/skills/blob/5c1a365113d7f44b420cc5633c746b42cfd14707/unslop-ui-design/SKILL.md).
- **Local checkpoint: PKG-001 and PKG-002 verified**, with [native evidence](experiments/native-package-f08fd848.json). The tested picker-boundary fix is `f08fd848`, published with evidence in `1d91e73`; [exact branch CI passed](https://github.com/anima-regem/Mashi/actions/runs/41522913947). This is a core development package, not an alpha. **Source recognition checkpoint: CAP-008 is complete**, with [recognition evidence](experiments/recognition-readiness.json). **Next: finish PKG-004** by rebuilding/qualifying these new setup controls in the native application; then PKG-005 completion setup. The core artifact above predates recognition setup. The previous inspection stall is not claimed resolved.

## One integrated alpha

The requested alpha is one application release after the engines work together: image capture/import → local recognition and user correction → source vectorization/editing → usable missing-form inference with honest quality/provenance → review/proof → font export → reopen/recovery. A core-only package or a website gallery does not close this gate.

| Gate | Remaining work |
| --- | --- |
| Recognition and correction | PKG-004 setup/readiness, CAP-006 frozen protocol and CAP-007 consented handwriting evaluation. The current bundle excludes OCR executable/data; printed OCR smoke is not handwriting evidence. |
| Useful missing-form inference | PKG-005 local runtime/checkpoint setup, ML-003 protocol and ML-005 representative held-out writer/style results against retrieval/manual baselines. The learned baseline underperforms retrieval; SciPy/weights are absent from this bundle. |
| Representative complete workflow | QA-002 first use and recovery, starter repertoire/reader review (TYPE-003/004), and PKG-003 clean-host qualification. Synthetic compilation and a fresh development-machine profile are narrower evidence. |
| Permitted delivery | LIC-003 model/checkpoint classification and source/RFN obligations, LIC-002 native dependency clearance, and a reviewed distribution/install plan. No weights, signing purchase or security bypass is authorized by this gate. |

REL-004 tracks this functional alpha gate. Signing/public distribution remain separate gates; publishing the website gallery is neither app qualification nor a dependency of engine readiness.

Evidence shorthand: [C7](https://github.com/anima-regem/Mashi/commit/c7b41de3acb3075d55edaa12eb432ee215bed3a5), [C7 CI](https://github.com/anima-regem/Mashi/actions/runs/41340676872) = verified source baseline, 168 Python/20 Node tests; **V** = [validation record](VALIDATION.md). Source CI is not native/reader qualification. No real-writer corpus, clean-install evidence or signed/notarized release is established.

## Board and documentation

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| GOV-001 | P0 | Done | Publish this board and prominent README link; every task has stable ID, status, checks and dependencies; next task is explicit. | — | This file and [README link](../README.md); 72 unique IDs, valid statuses, acyclic dependencies and existing local links checked. |
| DOC-001 | P0 | Done | Correct stale desktop backup/proof-persistence guidance; distinguish source features from features verified in a particular bundle. | PROJ-002, TYPE-002 | [Desktop guidance](DESKTOP.md#data-recovery-and-diagnostics), [proof persistence/API](PROOFING.md), iteration evidence. |
| DOC-002 | P1 | Todo | One short end-user font walkthrough with screenshots, exact coverage limits and recovery actions; developer setup stays separate. | FLOW-002, QA-002 | Not yet a verified first-use guide. |

## Capture and first use

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| FLOW-001 | P0 | Done | Upload → confirm exact label → trace actual ink → edit → compiled proof → SVG/UFO/TTF subset works with no key. Preserve counters, orientation and joiners. | CAP-001, EDIT-001, TYPE-001 | [C7 CI], [workflow tests](../tests/test_workflow.py), V. Synthetic fixtures only. |
| FLOW-002 | P0 | Done | Trace is unavailable until the displayed crop/label/confirmation are saved; dirty/recovered/invalid form cannot trace previous pixels; save/discard restores readiness; explain next action briefly. Check desktop/mobile and keyboard. | FLOW-001 | [State regressions](../tests/review-state.test.cjs), [rendered/compiled evidence](VALIDATION.md#task-board-and-capture-readiness); 168 Python/22 Node passed locally. |
| FLOW-003 | P0 | Todo | Make empty/blank/noisy upload recoverable: drawing or coordinate crop is discoverable; no invented segmentation; preserve the original on errors. | CAP-001, FLOW-002 | Existing manual crop fallback needs first-use review. |
| CAP-001 | P0 | Done | Bounded raster decode, EXIF/alpha handling, immutable original/canonical hashes and half-open coordinates. | — | [imaging tests](../tests/test_workflow.py), V, [architecture](ARCHITECTURE.md). |
| CAP-002 | P0 | Done | Crop drawing, exact coordinates, split/merge ancestry, local OCR word suggestions and manual exact-label confirmation. No word-by-character splitting. | CAP-001 | [OCR/provenance tests](../tests/test_provenance_ocr.py), [printed OCR smoke](experiments/ocr-smoke-results.json). Handwriting OCR is unmeasured. |
| CAP-003 | P0 | Done | Preview/apply/restore perspective, rotation and lighting; page/source/original transforms and prior state survive; fresh regions remain unconfirmed. | CAP-001 | [preparation tests](../tests/test_preparation.py), V, C7. Synthetic photo transforms only. |
| CAP-004 | P1 | Todo | Add reversible line/page deskew suggestions with a reviewed angle; test rotated content, borders, blank paper and rejection. | CAP-003 | Current rotation is adjustable; automatic reliable deskew is not established. |
| CAP-005 | P1 | Todo | Useful blur/glare/no-ink feedback from measured image conditions; keep manual work available and avoid false quality scores. | FLOW-003 | Needs defined synthetic fixtures and conservative thresholds. |
| CAP-006 | P1 | Todo | Freeze handwriting OCR evaluation: raw text/joiners, word-region overlap, missed ink and manual correction effort; compare with manual-only capture. | CAP-002, ML-003 | Printed-text smoke is not handwriting recognition evidence. |
| CAP-007 | P1 | Blocked | Run that OCR/region protocol on consented handwriting photos; retain failure examples privately and report limits without character-count splitting. | CAP-006, ML-004 | No consented real handwriting-photo set is available. |
| CAP-008 | P0 | Done | Source recognition distinguishes absent engine/data/load error/ready; explicit pinned data setup preserves prior files; raw proposals require correction/confirmation; dirty and stale work stays safe. Rendered wide/narrow browser capture → trace/edit → compiled proof/font/reopen and no-engine fallback. | CAP-002, FLOW-002, SEC-001 | [Recognition guidance](RECOGNITION.md), [13 Python regressions](../tests/test_recognition_setup.py), [4 controller regressions](../tests/recognition.test.cjs), [live printed evidence](experiments/recognition-readiness.json). Full source: 186 Python/26 Node passed locally; not handwriting or rebuilt-native qualification. |

## Editable outlines

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| EDIT-001 | P0 | Done | Closed contour tracing and visual nodes/handles; zoom/pan, source comparison, baseline/advance and session undo/redo. Counters and winding survive edits. | CAP-001 | [geometry tests](../tests/outline-geometry.test.cjs), [baseline tests](../tests/outline-baseline.test.cjs), V. |
| EDIT-002 | P1 | Todo | Insert/delete a visual node without opening a contour; explicit selection, undo and counter retention; reject impossible edits. | EDIT-001 | Current editor moves existing nodes only. |
| EDIT-003 | P1 | Todo | Bound large-contour rendering and simplify selection without losing ink; benchmark dense synthetic paths and keyboard latency. | EDIT-001, PERF-001 | No large real-writing usability benchmark. |
| EDIT-004 | P0 | Done | Retrace and saved-region restore keep the replaced vector/metrics; stale drafts do not replace new saved state. | EDIT-001 | [history tests](../tests/test_history_restore.py), V, C7. |
| EDIT-005 | P2 | Todo | Offer reversible smoothing as a previewed operation with original/after comparison; retain exact source trace and holes. | EDIT-002 | No smoothing-quality claim yet. |

## Font projects and recovery

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| PROJ-001 | P0 | Done | Up to 20 named pages share typography and explicit variants; source identity stays per page; no cross-page crop merge or silent replacement. | FLOW-001 | [projects/backups](PROJECTS_BACKUPS.md), [tests](../tests/test_projects_backups.py), C7 CI. |
| PROJ-002 | P0 | Done | Exact first-write legacy recovery; editable backup includes referenced source/history images; bounded fresh-ID import does not overwrite projects. | PROJ-001, SEC-002 | C7 CI, V. Browser drafts and external model weights are excluded. |
| PROJ-003 | P0 | Done | Imported stale choices remain recoverable; unfinished wide estimates and corrected history round-trip; unsupported data fails before backup download. | PROJ-002 | [C7], [sample-choice UI regressions](../tests/sample-choices.test.cjs), V. |
| PROJ-004 | P1 | Todo | Reorder pages with keyboard-accessible controls; IDs/assets/choices unchanged, global proof invalidated, order persists in backup/restart. | PROJ-001 | Missing. |
| PROJ-005 | P1 | Todo | Archive and restore a page reversibly; never silently switch a chosen variant; keep its photos/history and explicit recovery. | PROJ-001, PROJ-002 | No page archive/delete flow yet. |
| PROJ-006 | P1 | Todo | Restore a whole historical page/project state with stale-revision checks and a retained before-state; no cross-page overwrite. | PROJ-002, EDIT-004 | Current preparation/region restores are narrower than general undo. |
| PROJ-007 | P1 | Todo | Make sample naming/numbers consistent between active crop list, variant selector and view action after discard/merge/split. | PROJ-001 | Current lists can use different numbering conventions. |
| PROJ-008 | P2 | Todo | Search/reopen a larger saved-project library without decoding every image; empty/error/retry states and no silent data migration. | PROJ-001 | Current chooser lists up to 50 projects. |
| PROJ-009 | P1 | Todo | Detect inaccessible interrupted-import staging/orphan data and offer safe recovery/cleanup; never remove a referenced asset. | PROJ-002 | Crash-orphan limitation documented; cleanup is not implemented. |

## Malayalam typography and readability

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| TYPE-001 | P0 | Done | Bounded `mlm2` repertoire with actual HarfBuzz glyph/advance/anchor/clipping checks; dependencies constructed and validated, exact text retained. | CAP-002, EDIT-001 | [typography](TYPOGRAPHY.md), [tests/corpus](../tests/test_typography.py), C7 CI. Not complete Malayalam shaping. |
| TYPE-002 | P0 | Done | Compiled-outline proof/preflight, revision/options cache, shared saved font settings and required-text export; no fallback font masks missing ink. | TYPE-001 | [proofing](PROOFING.md), [proof tests](../tests/test_proof_api.py), V. |
| TYPE-003 | P0 | Todo | Define an explicit design-font starter repertoire and capture/proof sheet; include chillus, joiners, conjuncts and vowel contexts with dependencies. | TYPE-001 | Needs an auditable repertoire rather than a claim that every codepoint is one glyph. |
| TYPE-004 | P0 | Blocked | Malayalam-reader review of starter proof sheet; record incorrect forms/spacing and acceptance per context. | TYPE-003 | No reader/writer review evidence or consented review set is available. Synthetic compilation cannot close this. |
| TYPE-005 | P1 | Todo | Visual anchor adjustment with marks on the actual compiled base; save/restart/export parity and accessible numeric fallback. | TYPE-002 | Current anchor override is Advanced JSON. |
| TYPE-006 | P1 | Todo | Expand only reviewed conjunct/mark contexts with complete dependencies and explicit unsupported cases; regression corpus and reader review. | TYPE-003, TYPE-004 | General contextual/stacked marks remain incomplete. |
| TYPE-007 | P1 | Todo | Qualify the same exported file in supported browser/OS/design applications; record shaping engine/version and discrepancies. | TYPE-003 | Current HarfBuzz checks do not establish platform parity. |
| TYPE-008 | P2 | Todo | Export selected optional alternate forms through deliberate OpenType controls; preserve current default resolver and provenance. | PROJ-001, TYPE-004 | Alternatives currently stay editable but only one is exported. |

## Useful, accessible interface

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| UI-001 | P0 | Done | Remove slogans/version/local badges and developer setup from normal screens; retain contextual source/license/accuracy decisions. | FLOW-001 | [6c331e3](https://github.com/anima-regem/Mashi/commit/6c331e3a464f5e3f7de973c00ef67fecbeecec84), V. |
| UI-002 | P0 | Todo | Complete keyboard path for capture, outline, variants, proof and export; visible focus, sensible order and no keyboard trap. | FLOW-002 | Selected paths tested; complete audit is not done. |
| UI-003 | P1 | Todo | Screen-reader announcements for state/error/progress and named editor controls; manual assistive-technology record. | UI-002 | No full screen-reader qualification. |
| UI-004 | P1 | Todo | Review 200% zoom, narrow/landscape layout and reduced motion across every state; no clipped actions or horizontal document overflow. | UI-002 | 390 px baseline exists; broader matrix remains. |
| UI-005 | P1 | Todo | Review Malayalam labels/help and long exact sequences with Malayalam speakers; language metadata and font fallback remain explicit. | TYPE-004 | No localization/readability approval. |

## Errors, performance and provenance

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| PERF-001 | P0 | Todo | Benchmark upload/trace/save/proof/import at documented limits; record peak memory/time and responsive recovery after failure. | FLOW-001, PROJ-002 | Bounds exist; product performance budget is not measured. |
| PERF-002 | P1 | Todo | Test service interruption, corrupt/missing image, full disk and actions while another form has a draft; preserve work and offer recovery without false success or framework jargon. | FLOW-002, PROJ-002 | Partial error coverage exists; full product recovery matrix is missing. |
| PERF-003 | P1 | Todo | Bound and cancel owned trace/compiler work where practical; late results never replace current state and unrelated work is untouched. | PERF-001 | Proof cancellation currently ignores late display but may finish compilation. |
| SEC-001 | P0 | Done | Loopback, Host/Origin/token, bounded raster/path inputs, argument-list subprocesses and no cloud fallback. | — | [architecture](ARCHITECTURE.md), [workflow tests](../tests/test_workflow.py), C7 CI. Not a complete penetration test. |
| SEC-002 | P0 | Done | Bounded ZIP directory/decompression; reject traversal, duplicate/case collisions, symlinks, encryption, malformed references/geometry and unexpected files. | SEC-001 | [archive tests](../tests/test_projects_backups.py), V, C7 CI. |
| SEC-003 | P0 | Done | Generated/synthetic origins survive review/edit/export; ordinary font ZIPs contain only eligible current observed forms, no candidate/history geometry. | PROJ-001 | [completion review tests](../tests/test_completion_review.py), V, C7. |
| SEC-004 | P0 | Todo | Audit packaged offline behavior and diagnostics for unintended requests, sensitive logging or broad filesystem access; publish a concrete privacy boundary. | PKG-001 | Source protections are tested; current native build needs its own audit. |
| LIC-001 | P0 | Done | MIT app license and separate font/source attribution, pinned research sources and notices; no font outlines/FEA copied silently. | — | [research](RESEARCH.md), [source manifest](source-manifest.json), [licensing](../README.md#licensing). |
| LIC-002 | P0 | Todo | Review every native binary/dependency notice and redistribution obligation; resolve empty wheel-notice entries before distribution. | PKG-001 | [desktop inventory limitations](DESKTOP.md#dependency-and-licence-inventory). |
| LIC-003 | P0 | Blocked | Resolve model/checkpoint distribution classification and exact source/RFN obligations; record a permitted distribution plan. | ML-001 | Weights remain local; removal of templates is not license clearance. No weight publication authorized. |

## Completion model quality

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| ML-001 | P0 | Done | Preserve reproducible rendered-font baseline, lineage split and audit; disclose scoring correction and retrieval comparison. | LIC-001 | [Mashi-ML audit](https://github.com/anima-regem/Mashi-ML/blob/7b3f65680fb66be27a4c57593848fef75b884e76/reports/AUDIT.md). Learned baseline underperforms retrieval; handwriting fidelity unmeasured. |
| ML-002 | P0 | Done | Optional local format-2/3 inference, safe load, aligned reference preview, candidate edit/accept/reject and separate generated output. Failure leaves core capture working. | SEC-003 | [local completion](LOCAL_COMPLETION.md), C7 CI, V. No weights bundled. |
| ML-003 | P0 | Todo | Freeze writer/style evaluation protocol before tuning; lineage/writer splits, retrieval and manual baselines, missing-sequence and reader metrics. | ML-001, TYPE-003 | Rendered-font IoU alone is insufficient. |
| ML-004 | P0 | Blocked | Obtain a consented private handwriting set with usage limits, writer split and retention/deletion plan; no public photos by default. | ML-003 | No real-writer data/consent is supplied. |
| ML-005 | P1 | Todo | Evaluate capture alignment and missing-form style coherence on that held-out set; record failures and edit effort beside retrieval. | ML-003, ML-004 | Requires the consented set; do not substitute synthetic evidence. |
| ML-006 | P1 | Todo | Improve the learned method only against frozen baselines; bounded local compute, recorded manifests/checkpoint and a new untouched test split. | ML-005 | No new paid compute is implied; weight distribution still requires LIC-003. |

## Native delivery, tests and release

| ID | Priority | Status | Task and acceptance checks | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| PKG-001 | P0 | Done | Build current pinned source locally; bundled headless capture→TTF smoke, static assets/notices/hash manifest and close/reopen pass outside checkout. | FLOW-002, DOC-001 | [Local f08fd848 artifact evidence](experiments/native-package-f08fd848.json): 11 restricted packaged checks, exact assets/notices/manifest, strict original/extracted signatures. [Exact published branch CI passed](https://github.com/anima-regem/Mashi/actions/runs/41522913947). |
| PKG-002 | P0 | Done | Native file picker, save dialog, edit/proof/export, window close/Quit/reopen, bounded failure recovery and no orphan worker; investigate any stall with owned-process logs. | PKG-001 | [Local native qualification](VALIDATION.md#local-native-package-and-picker-boundary): capture/edit/proof/TTF/backup/recovery, window close and Quit, error feedback, active compiler cleanup. Baseline restriction-triggered picker abort investigated; a tested exception boundary contains Python delegate failures. Underlying trigger and earlier inspection stall are not claimed fully diagnosed. |
| PKG-003 | P0 | Blocked | Clean-Mac installation without Python/uv/dev dependencies; first font and restart work offline; record OS/architecture and bundle hash. | PKG-001, PKG-002 | No clean host qualification; current development machine cannot prove it. |
| PKG-004 | P1 | In progress | Optional OCR setup/diagnostics distinguish missing executable/data/ready; explicit user action, verified official data and manual fallback. No setup commands in normal studio. | PKG-002, CAP-008 | CAP-008 source flow is verified. Rebuild and qualify Finder discovery, explicit setup/error/retry, correction/proof/export/reopen in the native bundle; core artifact f08fd848 still excludes OCR executable/data and predates setup UI. |
| PKG-005 | P1 | Todo | Optional local completion setup accepts only reviewed external model/dependencies; clear unavailable/load/error/off states and explicit review. No automatic download or bundled weights. | PKG-002, ML-002 | Desktop bundle currently excludes ML dependencies/weights; bundling weights remains blocked by LIC-003. |
| PKG-006 | P1 | Todo | Qualify minimum macOS and available architectures with separate manifests; document unsupported systems honestly. | PKG-003 | No cross-architecture qualification yet. |
| PKG-007 | P0 | Blocked | Signed/notarized release from a reviewed bundle; verify identity and distribution, with no Gatekeeper bypass. | PKG-003, LIC-002, REL-001 | No signing identity/notarization authorization or paid account purchase permission. |
| PKG-008 | P1 | Todo | Install/update/rollback UX preserves data and explains incompatible schemas; no automatic security changes. | PKG-003, PKG-007, PROJ-002 | Developer `.app` is not a polished installer/update flow. |
| QA-001 | P0 | Done | Source lint/tests and exact published commit CI; existing regression coverage is recorded separately from native qualification. | FLOW-001 | [Published fe15500 CI](https://github.com/anima-regem/Mashi/actions/runs/41514198237): 168 Python/22 Node. Picker fix: 173 Python/22 Node, lint and [published branch CI passed](https://github.com/anima-regem/Mashi/actions/runs/41522913947). |
| QA-002 | P0 | Todo | Repeatable first-use product smoke from an empty data folder through backup/reopen/font output; include deliberate errors, keyboard and narrow layout. | FLOW-002, PROJ-002, TYPE-002 | Existing component/synthetic flows are a baseline, not a clean-install qualification. |
| QA-003 | P1 | Todo | Expand archive/state property regressions for repeated edits, restores, selections and interrupted imports; no silent loss or generated leakage. | PROJ-002, SEC-002 | Current adversarial fixtures exist; broader state sequences are missing. |
| REL-001 | P0 | Todo | Release checklist pins commit, exact CI, artifact hash, dependency notices, native/clean-host matrix, known limitations and rollback plan. | QA-002, PKG-003, LIC-002, TYPE-004 | No polished public release is qualified. |
| REL-002 | P1 | Todo | Review user-facing documentation against the actual release and remove stale prototype/setup claims; link useful help from relevant failures. | DOC-002, REL-001 | Current source/build/docs and artifact states must stay distinct. |
| REL-003 | P1 | Todo | Export support diagnostics only with reviewable contents; exclude tokens, photos, private text and environment dumps; test redaction. | SEC-004, PKG-002 | Desktop logs/diagnostics exist but a user support-export flow is missing. |
| REL-004 | P0 | Blocked | One integrated alpha only when capture/import, recognition/correction, vector editing, useful inference, reviewed proof, export and recovery work together with representative handwriting evidence and permitted model delivery. Website/gallery progress does not qualify the app. | PKG-004, PKG-005, CAP-007, ML-005, TYPE-004, QA-002, LIC-003 | Core-only native checkpoint is not an alpha. Missing OCR/ML runtime/model availability, writer/reader evidence and checkpoint distribution clearance remain explicit blockers; see the integrated-alpha gate above. |

## Closing an iteration

Update this board's status/evidence and V; report completed IDs, exact commit, tests/CI, blockers and next task. Do not claim that source checks establish native installation, reader-approved typography or writer fidelity. Keep pending approval work (including domain/DNS) separate from this product board.

[C7]: https://github.com/anima-regem/Mashi/commit/c7b41de3acb3075d55edaa12eb432ee215bed3a5
[C7 CI]: https://github.com/anima-regem/Mashi/actions/runs/41340676872
