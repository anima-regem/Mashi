"use strict";
(() => {
  let identity = "";
  const node = (tag, text, parent) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (parent) parent.append(element);
    return element;
  };
  function refreshControls() {
    if (!project) return;
    $("project-page-tools").querySelectorAll("button,input,select").forEach(control => control.disabled = busy);
    $("add-page-file").disabled = busy || project.pages?.length >= 20;
    $("page-upload-open").disabled = $("add-page-file").disabled;
    $("font-sample-list").querySelectorAll("button,select").forEach(control => control.disabled = busy);
    $("save-font-settings").disabled = busy;
  }
  async function showSample(sample) {
    await openProject(project.id, sample.page_id);
    selected = sample.region_id;
    render();
    $("vectors").scrollIntoView({behavior:"smooth", block:"start"});
  }
  function sync() {
    const enabled = !!features.multi_page;
    $("project-page-tools").hidden = !enabled;
    $("save-font-settings").hidden = !enabled;
    if (!enabled || !project) return;
    const next = `${project.id}:${project.page_id}:${project.revision}`;
    if (next === identity) return;
    identity = next;
    const pages = project.pages || [];
    $("page-switcher").hidden = pages.length < 2;
    $("project-page").replaceChildren();
    pages.forEach(page => {
      const option = node("option", page.name, $("project-page"));
      option.value = page.id;
    });
    $("project-page").value = project.page_id;
    $("current-page-name").value = project.page_name;
    const groups = project.sample_groups || [];
    $("font-samples").hidden = !groups.length;
    const unresolved = groups.filter(group => group.needs_choice && !group.choice).length;
    $("font-samples-summary").textContent = `Font samples · ${groups.length} sequence${groups.length === 1 ? "" : "s"}${unresolved ? ` · ${unresolved} need${unresolved === 1 ? "s" : ""} a choice` : ""}`;
    $("font-sample-list").replaceChildren();
    groups.forEach(group => {
      const row = node("div", "", $("font-sample-list")); row.className = "font-sample-row";
      const label = node("span", group.label, row); label.lang = "ml"; label.className = "sample-label";
      let sample = group.choice ? group.samples.find(s => s.page_id === group.choice.page_id && s.region_id === group.choice.region_id && s.revision === group.choice.revision) : group.needs_choice ? null : group.samples[0];
      const description = s => `${s.page_name} · ${s.kind === "generated" ? "generated form" : "crop " + s.number}${s.provenance === "synthetic-fixture" ? " · synthetic" : ""}`;
      if (group.needs_choice || group.samples.length > 1) {
        const select = node("select", "", row);
        select.setAttribute("aria-label", `Sample to use for ${group.label}`);
        node("option", "Choose a sample…", select).value = "";
        group.samples.forEach((s, i) => { node("option", description(s), select).value = String(i); });
        select.value = sample ? String(group.samples.indexOf(sample)) : "";
        select.onchange = () => {
          if (select.value === "") return;
          const chosen = group.samples[Number(select.value)];
          work(async () => {
            await update(`${url()}/samples/select`, {method:"PUT", json:{revision:project.revision, label:group.label, page_id:chosen.page_id, region_id:chosen.region_id, sample_revision:chosen.revision}}, `Sample chosen for ${group.label}. Rebuild the proof to review it.`);
          });
        };
        if (group.reason) node("small", "Sample changed. Choose again.", row);
      } else node("span", description(sample), row);
      const view = node("button", "View sample", row);
      view.disabled = !sample; view.hidden = !sample;
      view.onclick = () => work(() => showSample(sample));
    });
    refreshControls();
  }
  $("project-page").onchange = () => work(() => openProject(project.id, $("project-page").value));
  $("backup-open").onclick = $("workspace-import").onclick = () => $("backup-file").click();
  $("page-upload-open").onclick = () => $("add-page-file").click();
  $("page-rename-form").onsubmit = event => {
    event.preventDefault();
    work(() => update(`${url()}/pages/${project.page_id}/name`, {method:"PUT", json:{name:$("current-page-name").value, revision:project.revision}}, "Page name saved."));
  };
  $("add-page-file").onchange = event => {
    const file = event.target.files[0]; event.target.value = "";
    if (!file) return;
    work(async () => {
      const doc = await (await api(`${url()}/pages?revision=${project.revision}`, {method:"POST", body:file, headers:{"Content-Type":file.type || "application/octet-stream"}})).json();
      await openProject(doc.id, doc.page_id);
      message("Page added. Confirm its crops and labels before tracing.");
    });
  };
  $("save-font-settings").onclick = () => work(async () => {
    const input = window.MashiProof.projectSettings();
    const doc = await (await api(`${url()}/typography`, {method:"PUT", json:input})).json();
    window.MashiProof.settingsSaved();
    if (!await setProject(doc)) return;
    render(); message("Proof text and font settings saved in the project.");
  });
  $("project-backup").onclick = () => work(async () => {
    const id = project.id, revision = project.revision;
    message("Preparing the project backup…");
    const response = await api(`${url()}/backup`, {method:"POST", json:{revision}});
    const blob = await response.blob();
    if (project.id !== id || project.revision !== revision) throw new Error("The project changed. Create a fresh backup.");
    const objectURL = URL.createObjectURL(blob), link = node("a", "", document.body);
    link.href = objectURL; link.download = "Mashi-Project.mashi.zip"; link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(objectURL), 10000);
    message("Project backup downloaded. It includes your source photos.");
  });
  $("backup-file").onchange = event => {
    const file = event.target.files[0]; event.target.value = "";
    if (!file) return;
    work(async () => {
      message("Checking the project backup…");
      const doc = await (await api("/api/projects/import", {method:"POST", body:file, headers:{"Content-Type":"application/zip"}})).json();
      await openProject(doc.id, doc.page_id);
      message("Backup imported as a new font project. Your existing projects are unchanged.");
    });
  };
  window.MashiProjects = {sync, refreshControls};
  if (project) sync();
})();
