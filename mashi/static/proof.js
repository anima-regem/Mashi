"use strict";
(() => {
  const requests = new window.MashiReviewState.LatestRequest();
  const ids = ["text", "family", "ascender", "descender", "line-gap", "space", "mark-gap", "anchors"];
  const defaults = ["", "Mashi Handwriting", 1000, -400, 100, 300, 40, "{}"];
  const NS = "http://www.w3.org/2000/svg";
  let identity = "", running = false, reviewed = null, anchors = null;
  const storageKey = () => `mashi:proof:${project.id}`;
  const fixture = () => project?.source_kind === "synthetic-fixture" && $("fixture-export").checked;
  function text(tag, content, parent) {
    const node = document.createElement(tag); node.textContent = content; parent.append(node); return node;
  }
  function values() {
    if (!$("proof-form").reportValidity()) throw new Error("Check proof text and font settings.");
    let anchorData;
    try { anchorData = JSON.parse($("proof-anchors").value); }
    catch { throw new Error("Anchor overrides must be a JSON object with exact labels and coordinate pairs."); }
    return {revision: project.revision, text: $("proof-text").value, options: {
      family_name: $("proof-family").value,
      ascender: Number($("proof-ascender").value), descender: Number($("proof-descender").value),
      line_gap: Number($("proof-line-gap").value), space_advance: Number($("proof-space").value),
      mark_gap: Number($("proof-mark-gap").value), anchors: anchorData,
    }};
  }
  const stamp = (input) => JSON.stringify([project.id, input, fixture()]);
  function refreshControls() {
    $("proof-check").disabled = busy || running;
    $("proof-build").disabled = busy || running;
    $("proof-cancel").disabled = busy || !running;
    $("proof-copy-anchors").disabled = busy || running || !anchors;
  }
  function invalidate(note = "Proof changed. Check samples or rebuild the preview before export.") {
    requests.cancel(); running = false; reviewed = anchors = null;
    $("proof-status").textContent = note;
    $("proof-status").classList.remove("error");
    ["coverage", "drawing", "diagnostics", "unicode", "issues", "metadata"].forEach(id => $("proof-" + id).replaceChildren());
    refreshControls();
  }
  function persist() {
    if (!project) return;
    const saved = remember(storageKey(), ids.map(id => $("proof-" + id).value));
    $("proof-storage").textContent = saved
      ? "Proof text and settings are kept in this browser for this page."
      : "Browser storage unavailable. Copy proof text and settings before leaving.";
  }
  function sync() {
    const next = `${project.id}:${project.revision}`;
    if (next === identity) return;
    const changedPage = identity.split(":")[0] !== project.id;
    identity = next;
    if (changedPage) {
      const saved = recall(storageKey());
      ids.forEach((id, i) => $("proof-" + id).value = Array.isArray(saved) && saved.length === ids.length ? saved[i] : defaults[i]);
    }
    invalidate(`Saved page revision ${project.revision}. Build a fresh proof from its confirmed outlines.`);
  }
  function coverage(report) {
    const box = $("proof-coverage"); box.replaceChildren();
    text("h3", report.supported ? "Required samples are available in V1" : "This text needs attention", box);
    if (report.synthetic_test_export) text("p", "This proof uses synthetic sample shapes, not handwriting.", box);
    if (report.required_samples.length) text("p", "Capture and confirm: " + report.required_samples.join(" · "), box);
    if (report.duplicate_labels.length) text("p", "Choose one confirmed variant for duplicate labels: " + report.duplicate_labels.join(" · "), box);
    const list = document.createElement("ul");
    report.issues.forEach(issue => text("li", `${issue.code.replaceAll("_", " ")} · ${issue.sequence} · position ${issue.index}` +
      (issue.required_samples.length ? ` · samples: ${issue.required_samples.join(" · ")}` : " · requires a text change or future shaping support"), list));
    if (!report.supported && !report.issues.length && !report.duplicate_labels.length)
      text("p", "Confirm and trace eligible ink first. Synthetic practice ink also needs the explicit test-export checkbox below.", box);
    $("proof-issues").replaceChildren(list);
    const unsupported = report.issues.filter(issue => !issue.required_samples.length);
    if (unsupported.length) text("p", "Unsupported text: " + [...new Set(unsupported.map(issue => issue.sequence))].slice(0, 6).join(" · ") + ". Edit the text; capturing a whole word will not add shaping support. See details below.", box);
    if (report.issues_truncated) text("p", `Showing the first 100 of ${report.issues_total} issues in shaping details. Shorten the text to inspect the rest.`, box);
    const normalize = report.normalization;
    $("proof-unicode").textContent = `Original: ${report.text}\nCodepoints: ${report.codepoints.join(" ")}\nNFC (informative): ${normalize.nfc}\nNFD (informative): ${normalize.nfd}\nPolicy: preserve original`;
  }
  function draw(result) {
    const output = $("proof-drawing"); output.replaceChildren();
    const wrap = document.createElement("div"); wrap.className = "proof-line";
    const svg = document.createElementNS(NS, "svg");
    const bounds = result.drawing.view_box;
    svg.setAttribute("viewBox", bounds.join(" "));
    svg.setAttribute("width", Math.round(bounds[2] * 0.1));
    svg.setAttribute("height", Math.round(bounds[3] * 0.1)); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Compiled proof; ${result.drawing.lines.length} lines; exact text: ${result.preview.text}`);
    result.drawing.lines.forEach(line => {
      line.glyphs.forEach(glyph => {
        const path = document.createElementNS(NS, "path");
        path.setAttribute("d", result.drawing.paths[glyph.name]);
        path.setAttribute("transform", `translate(${glyph.x},${line.baseline_offset - glyph.y}) scale(1,-1)`);
        svg.append(path);
      });
    });
    wrap.append(svg); output.append(wrap);
    const metrics = result.metrics;
    const metadata = $("proof-metadata");
    metadata.replaceChildren();
    text("p", `${result.drawing.family_name} · ${result.preview.engine} · revision ${result.revision}${result.cache.hit ? " · cached" : ""}. ` +
      `Actual ascender ${metrics.ascender}, descender ${metrics.descender}, line gap ${metrics.line_gap} at 1000 UPM.`, metadata);
    const diagnostics = $("proof-diagnostics"); diagnostics.replaceChildren();
    const list = document.createElement("ul");
    result.preview.diagnostics.forEach(d => text("li", `${d.code.replaceAll("_", " ")} · line ${d.line + 1}${d.glyph ? " · " + d.glyph : ""}`, list));
    diagnostics.append(list);
    if (result.preview.diagnostics_truncated) text("p", `Showing 100 of ${result.preview.diagnostics_total} diagnostics. Shorten proof text for the rest.`, diagnostics);
    if (result.preview.diagnostics.length) text("p", "Overlap checks compare ink bounds, not contours. Review the actual shapes. Forms and mark stacks outside V1 remain unsupported.", diagnostics);
    anchors = Object.fromEntries(Object.entries(metrics.anchors).map(([label, a]) => [label, {[a.name]: a.point}]));
  }
  async function run(action) {
    if (busy || running) return;
    let input;
    try { input = values(); }
    catch (e) { $("proof-status").textContent = e.message; return; }
    const fingerprint = stamp(input), id = project.id;
    invalidate(); running = true; refreshControls();
    $("proof-status").textContent = action === "preview" ? "Compiling and shaping saved ink locally… Cancel stops this review; compiler work may finish in the background." : "Checking exact-text sample coverage…";
    await requests.run(async signal => (await api(`/api/projects/${id}/proof/${action}?include_fixture=${fixture()}`, {method: "POST", json: input, signal})).json(),
      result => {
        if (project.id !== id || result.revision !== project.revision || stamp(input) !== fingerprint) return;
        coverage(result.coverage);
        if (action === "preview") {
          draw(result);
          const safe = result.coverage.supported && !result.preview.has_notdef && !result.preview.diagnostics.some(d => d.code === "vertical_clipping");
          reviewed = safe ? fingerprint : null;
          $("proof-status").textContent = safe ? "Current proof shaped successfully. Review the ink and spacing; this exact text and these settings can be exported." : "Proof drawn for inspection. Missing samples or unsupported text block final export.";
        } else $("proof-status").textContent = "Sample check complete. Build the compiled preview to verify actual glyph selection and positions.";
        if (!busy) message(action === "preview" ? "Proof preview ready. Review its coverage and diagnostics below." : "Proof sample check complete.");
      }, error => { $("proof-status").textContent = error.message + " Retry after correcting the input, or reload the saved page if it changed."; $("proof-status").classList.add("error"); });
    // A new request owns its own controls; a canceled request never re-enables it.
    if (requests.controller === null) { running = false; refreshControls(); }
  }
  $("proof-form").oninput = () => { persist(); invalidate(); };
  $("proof-form").onsubmit = event => { event.preventDefault(); run("preview"); };
  $("proof-check").onclick = () => run("preflight");
  $("proof-cancel").onclick = () => invalidate("Preview canceled. Its late result will not be shown. You can edit or retry.");
  $("fixture-export").onchange = () => invalidate("Export provenance changed. Build a fresh proof with this choice.");
  $("proof-copy-anchors").onclick = () => { $("proof-anchors").value = JSON.stringify(anchors, null, 2); persist(); invalidate("Anchor estimates copied. Edit the pairs and rebuild to inspect positioning."); };
  window.MashiProof = {sync, refreshControls, cancel: () => invalidate("Page closed. Late proof results are ignored."),
    exportInput(kind) {
      const input = values();
      if (kind === "ttf" && reviewed !== stamp(input)) throw new Error("Build and review a current, supported proof preview before TTF export.");
      return input;
    }};
  if (project) sync();
})();
