"use strict";
(() => {
  let status = recognitionStatus || null;
  function refreshControls() {
    $("ocr").hidden = !status?.available;
    $("ocr").disabled = busy || !project || !status?.available;
    $("ocr-setup").hidden = !status?.can_setup;
    $("ocr-setup").disabled = busy || !status?.can_setup;
    $("ocr-setup-note").hidden = !status?.can_setup;
    $("ocr-check").disabled = busy;
    $("use-suggestion").disabled = busy;
  }
  function setStatus(next) {
    status = next;
    $("ocr-status").textContent = status?.reason || "Check whether word recognition is ready.";
    refreshControls();
  }
  function selection(region) {
    const text = region?.suggestion?.raw_text;
    $("use-suggestion").hidden = !region?.active || region.coordinate_space === "generated-canvas" ||
      typeof text !== "string" || !text.length || [...text].length > 32 ||
      !/^[\u0d00-\u0d7f\u200c\u200d]+$/u.test(text);
    refreshControls();
  }
  $("ocr-check").onclick = () => work(async () => {
    setStatus(await (await api("/api/ocr/status")).json());
    message(status.reason);
  });
  $("ocr-setup").onclick = () => work(async () => {
    message("Adding Malayalam recognition data… Your photos are not sent.");
    try {
      setStatus(await (await api("/api/ocr/setup", {method:"POST"})).json());
      message(status.reason, !status.available);
    } catch (error) {
      // A failed setup never marks recognition ready or changes the open project.
      try {setStatus(await (await api("/api/ocr/status")).json());} catch {}
      throw error;
    }
  });
  $("ocr").onclick = () => work(async () => {
    const r = current();
    if (r && !generatedSelection(r) && !window.MashiReviewState.sameCrop(r, cropInputs()))
      throw new Error("Save or discard the current crop changes before word recognition.");
    const previous = new Set(project.regions.map(region => region.id));
    message("Recognizing words…");
    const doc = await (await api(`${url()}/ocr`, {method:"POST", json:{revision:project.revision}})).json();
    if (!await setProject(doc)) return;
    const added = project.regions.filter(region => !previous.has(region.id) && region.source === "ocr-word");
    if (added.length) selected = added[0].id;
    render();
    message(added.length ? `${added.length} word suggestion${added.length === 1 ? "" : "s"} added. Check each crop and label before confirming.`
      : "No words found. Draw or adjust a crop and label it manually.");
  });
  $("use-suggestion").onclick = () => {
    if (busy || $("use-suggestion").hidden) return;
    const r = current();
    $("label").value = r.suggestion.raw_text;
    $("confirmed").checked = false;
    showCodepoints(); saveCropDraft(); $("label").focus();
    message("Suggested text copied. Correct it and confirm the crop before saving.");
  };
  window.MashiRecognition = {setStatus, refreshControls, selection};
  setStatus(status);
})();
