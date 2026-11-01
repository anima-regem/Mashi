"use strict";
(() => {
  const requests = new window.MashiReviewState.LatestRequest();
  const editorLoads = new window.MashiReviewState.LatestRequest();
  const alignmentLoads = new window.MashiReviewState.LatestRequest();
  let capability = null, identity = "", loadingCaps = false, job = null, running = false;
  let references = [], chosen = new Set(), editorKey = "";
  const targetValues = () => $("completion-targets").value.split(",").map(s => s.trim()).filter(Boolean);
  function node(tag, content, parent) {
    const element = document.createElement(tag);
    if (content) element.textContent = content;
    if (parent) parent.append(element);
    return element;
  }
  function status(message, error = false) {
    $("completion-status").textContent = message;
    $("completion-status").classList.toggle("error", error);
  }
  function image(src, alt, parent) {
    const img = node("img", "", parent); img.src = src.startsWith("/api/projects/") ? pageURL(src) : src; img.alt = alt; return img;
  }
  function targetNote() {
    const targets = targetValues(), labels = capability?.model?.labels || [];
    const pages = project.pages || [project];
    const present = new Set(pages.flatMap(p => p.regions.filter(r => r.active && r.confirmed).map(r => r.label)));
    pages.flatMap(p => p.completion_suggestions || []).filter(r => r.review_state !== "rejected").forEach(r => present.add(r.label));
    $("completion-target-note").textContent = targets.map(s => `${s} · ${!labels.includes(s) ? "not supported by this model" : present.has(s) ? "already captured or awaiting review" : "missing, supported"} · ${[...s].map(c => "U+" + c.codePointAt(0).toString(16).toUpperCase().padStart(4,"0")).join(" ")}`).join("; ");
  }
  function refreshControls() {
    $("completion-load").disabled = busy || running || !capability?.available || capability.loaded;
    $("completion-actions").hidden = !capability?.available && !running;
    $("completion-load").hidden = !capability?.available || capability.loaded || running;
    $("completion-unload").hidden = !capability?.loaded || running;
    $("completion-cancel").hidden = !running;
    $("completion-unload").disabled = busy || running || !capability?.loaded;
    $("completion-cancel").disabled = busy || !running;
    $("completion-align").disabled = busy || running || !chosen.size || !capability?.loaded;
    $("completion-generate").disabled = busy || running || !capability?.loaded || !references.length || !$("completion-alignment-confirmed").checked;
    $("completion-use-proof").disabled = busy || running || !capability?.loaded;
    $("completion-references").querySelectorAll("input").forEach(input => input.disabled = busy || running);
    $("completion-suggestions").querySelectorAll("button").forEach(button => button.disabled = busy || running || button.dataset.disabled === "1");
    if (generatedSelection(current())) $("vector-form").querySelectorAll("button,input,textarea").forEach(control => control.disabled = busy || !outlineReady);
  }
  function clearAlignment() {
    alignmentLoads.cancel();
    references = []; $("completion-aligned").replaceChildren();
    $("completion-alignment-confirmed").checked = false;
    refreshControls();
  }
  function cancel() {
    requests.cancel();
    const previous = job; job = null; running = false;
    if (previous) {
      api(pageURL(`/api/projects/${previous.project}/completion/cancel`, previous.page), {method:"POST", json:{revision:previous.revision, job_id:previous.id}}).then(() => {if (previous.action === "load") fetchCapability();}).catch(() => status("Cancel could not be confirmed. Reload the page before reviewing any late candidates.", true));
    }
    status("Request canceled. You can retry."); refreshControls();
  }
  async function fetchCapability() {
    if (loadingCaps) return;
    loadingCaps = true;
    try { capability = await (await api("/api/completion/capabilities")).json(); }
    catch { capability = {available:false, configured:false, loaded:false, reason:"Suggestions are unavailable. You can still capture missing forms."}; }
    finally { loadingCaps = false; if (project) sync(true); }
  }
  async function run(action, body, accept) {
    if (busy || running) return;
    const snapshot = {id:crypto.randomUUID(), project:project.id, page:project.page_id, revision:project.revision, action};
    requests.cancel(); job = snapshot; running = true; refreshControls();
    status(action === "load" ? "Loading model…" : "Generating suggestions…");
    await requests.run(async signal => (await api(`/api/projects/${snapshot.project}/completion/${action}`, {method:"POST", json:{...body, revision:snapshot.revision, job_id:snapshot.id}, signal})).json(), async result => {
      if (!project || project.id !== snapshot.project || project.page_id !== snapshot.page || project.revision !== snapshot.revision) return;
      job = null; running = false;
      await accept(result);
    }, error => {status(action === "load" ? "Could not load the model. Check model setup or continue with captured forms." : error.message, true);});
    if (job?.id === snapshot.id) {job = null; running = false;}
    refreshControls();
  }
  function renderReferences() {
    const list = $("completion-references"); list.replaceChildren();
    const supported = new Set(capability?.model?.labels || []);
    const eligible = project.regions.filter(r => r.active && r.confirmed && r.vector && supported.has(r.label) && (r.provenance === "observed" || project.source_kind === "synthetic-fixture" && r.provenance === "synthetic-fixture"));
    chosen = new Set([...chosen].filter(id => eligible.some(r => r.id === id)));
    eligible.forEach(region => {
      const label = node("label", "", list); label.className = "reference-choice";
      const check = node("input", "", label); check.type = "checkbox"; check.checked = chosen.has(region.id);
      check.setAttribute("aria-label", `Use ${region.label} as a completion reference`);
      check.onchange = () => {if (check.checked) chosen.add(region.id); else chosen.delete(region.id); clearAlignment();};
      image(`${url()}/regions/${region.id}/svg`, `Reference outline ${region.label}`, label);
      node("span", region.label + (region.provenance === "synthetic-fixture" ? " · synthetic" : ""), label);
    });
    if (!eligible.length) node("p", "Confirm and trace supported reference forms first. Only captured forms can be references.", list);
  }
  function renderSuggestions() {
    const list = $("completion-suggestions"); list.replaceChildren();
    const suggestions = project.completion_suggestions || [];
    $("completion-quality").hidden = !capability?.available && !suggestions.length;
    $("completion-review-title").hidden = !suggestions.length;
    const accepted = (project.pages || [project]).flatMap(p => p.completion_suggestions || []).filter(s => s.review_state === "accepted");
    $("generated-export-option").hidden = !accepted.length;
    $("generated-export-terms").hidden = !accepted.length;
    if (!accepted.length) $("generated-export").checked = false;
    suggestions.forEach(item => {
      const stale = item.generation.image_sha256 !== project.image.canonical_sha256 || item.generation.observations.some(ref => !project.regions.some(r => r.id === ref.id && r.active && r.confirmed && r.label === ref.label && r.revision === ref.revision));
      const card = node("article", "", list); card.className = "completion-card";
      node("h4", `${item.label} · ${item.review_state}`, card);
      const samples = node("div", "", card); samples.className = "candidate-comparison";
      const proposal = node("figure", "", samples);
      image(`${url()}/completion/suggestions/${item.id}/raster`, `Generated candidate ${item.label}`, proposal);
      node("figcaption", "Generated · not present in the photograph", proposal);
      item.generation.observations.forEach(ref => {
        const reference = node("figure", "", samples);
        image(`${url()}/completion/suggestions/${item.id}/reference/${ref.id}`, `Aligned reference ${ref.label}`, reference);
        node("figcaption", `${ref.label} · ${ref.provenance === "synthetic-fixture" ? "synthetic reference" : "captured reference"}`, reference);
      });
      if (item.trace_error) node("p", `No usable outline: ${item.trace_error}. Capture this form manually.`, card);
      if (stale) node("p", "Reference crops changed after this prediction. Reject and regenerate it before font export.", card);
      if (item.vectorization.method === "pixel-boundary/v1") node("p", "This outline has rough pixel edges. Review or edit it before use.", card);
      const actions = node("div", "", card); actions.className = "actions";
      const review = (state) => work(async () => update(`${url()}/completion/suggestions/${item.id}/review`, {method:"POST", json:{revision:project.revision, suggestion_revision:item.revision, state}}, `${item.label}: ${state}.`));
      const accept = node("button", "Accept candidate", actions); accept.disabled = stale || item.empty_prediction || !item.vector || item.review_state === "accepted"; accept.onclick = () => review("accepted");
      const edit = node("button", "Edit candidate outline", actions); edit.disabled = !item.vector || item.review_state === "rejected"; edit.onclick = () => {selected = item.id; render(); $("vector-preview").scrollIntoView({behavior:"smooth",block:"center"});};
      accept.hidden = accept.disabled || item.review_state === "rejected";
      edit.hidden = edit.disabled;
      [accept, edit].forEach(button => button.dataset.disabled = button.disabled ? "1" : "0");
      const reject = node("button", item.review_state === "rejected" ? "Review again" : "Reject candidate", actions); reject.onclick = () => review(item.review_state === "rejected" ? "pending" : "rejected");
      if (item.generation.model.terms.checkpoint_source_known) {
        const details = node("details", "", card); node("summary", "Font terms", details);
        node("p", "Fonts containing this form use OFL-1.1 and retain source notices.", details);
      } else node("p", "Font export is blocked because this model's source rights are unverified.", card);
    });
  }
  function sync(force = false) {
    if (!project) return;
    const next = `${project.id}:${project.page_id || project.id}:${project.revision}`;
    if (!force && identity === next) return;
    if (job && (project.id !== job.project || project.page_id !== job.page || project.revision !== job.revision)) cancel();
    if (identity.split(":").slice(0,2).join(":") !== next.split(":").slice(0,2).join(":")) chosen.clear();
    identity = next; clearAlignment();
    if (!capability) fetchCapability();
    $("completion-capability").textContent = !capability ? "Checking suggestions…" : capability.loaded ? "Choose reference forms to guide the suggestions." : capability.available ? "Suggestions are off. Load the model to continue." : "Suggestions are unavailable. You can still capture missing forms.";
    $("completion-capability").hidden = !!capability?.loaded;
    $("completion-request").hidden = !capability?.loaded;
    renderReferences(); renderSuggestions(); targetNote(); refreshControls();
  }
  async function loadEditor(item) {
    if (!item.vector) return;
    const key = `${project.id}:${project.page_id || project.id}:${item.id}:${item.revision}`;
    if (editorKey === key) {outlineReady = true;refreshControls();return;}
    outlineReady = false; $("vector-preview").replaceChildren(); refreshControls();
    const pid = project.id, pageId = project.page_id;
    await editorLoads.run(async () => {const raster = new Image(); raster.src = pageURL(`${url()}/completion/suggestions/${item.id}/raster`); await raster.decode(); return raster;}, raster => {
      if (project.id !== pid || project.page_id !== pageId || selected !== item.id) return;
      ["baseline", "scale", "advance"].forEach(k => $(k).value = item.vector[k]);
      $("paths").value = JSON.stringify(item.vector.paths, null, 2);
      window.MashiOutline.load(item, {...project, image:{...project.image, canonical_sha256:item.raster_sha256}}, raster);
      $("svg-download").href = pageURL(`${url()}/completion/suggestions/${item.id}/svg`);
      $("svg-download").download = "Mashi-model-generated-glyph.svg";
      $("svg-download").hidden = item.review_state !== "accepted" || !item.generation.model.terms.checkpoint_source_known;
      editorKey = key;
      outlineReady = true; refreshControls();
    }, error => {editorKey = ""; message("Generated raster could not load. Select the candidate again to retry. " + error.message, true);});
  }
  $("completion-load").onclick = () => run("load", {}, result => {capability = result; sync(true); status("Model ready.");});
  $("completion-unload").onclick = async () => {cancel(); try {capability = await (await api("/api/completion/unload", {method:"POST"})).json(); sync(true); status("");} catch(e) {status(e.message,true);}};
  $("completion-cancel").onclick = cancel;
  $("completion-align").onclick = async () => {
    if (chosen.size > 20) {status("Choose at most 20 references.",true);return;}
    const pid = project.id, pageId = project.page_id, revision = project.revision, ids = [...chosen];
    const fingerprint = JSON.stringify(ids);
    await alignmentLoads.run(async signal => (await api(`${url()}/completion/references`, {method:"POST", json:{revision, ids}, signal})).json(), result => {
      if (project.id !== pid || project.page_id !== pageId || project.revision !== revision || JSON.stringify([...chosen]) !== fingerprint) return;
      references = result.references; $("completion-aligned").replaceChildren();
      references.forEach(ref => {const figure = node("figure", "", $("completion-aligned")); figure.className = "aligned-reference"; image("data:image/png;base64," + ref.png, `Aligned reference ${ref.label}`, figure); node("figcaption", ref.label, figure);});
      $("completion-alignment-confirmed").checked = false;
      status("Check that the references sit on the baseline and keep a consistent size."); refreshControls();
    }, error => {clearAlignment(); status(error.message,true);});
  };
  $("completion-alignment-confirmed").onchange = refreshControls;
  $("completion-targets").oninput = targetNote;
  $("completion-use-proof").onclick = () => {const supported = new Set(capability.model.labels); $("completion-targets").value = window.MashiProof.missingSamples().filter(s => supported.has(s)).slice(0,8).join(", "); targetNote();};
  $("completion-generate").onclick = () => {
    const targets = targetValues();
    if (!targets.length || targets.length > 8) {status("Choose 1–8 supported missing sequences.",true);return;}
    run("generate", {ids:[...chosen], targets, reference_hashes:Object.fromEntries(references.map(r=>[r.id,r.sha256])), alignment_confirmed:$("completion-alignment-confirmed").checked}, async doc => {
      if (!await setProject(doc)) return;
      render(); await renderCoverage(); status("Suggestions ready for review.");
    });
  };
  window.MashiCompletion = {sync, refreshControls, loadEditor, cancel, clearEditorIdentity: () => {editorKey = ""; editorLoads.cancel();}};
  if (project) sync();
})();
