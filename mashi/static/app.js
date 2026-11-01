"use strict";
const $ = (id) => document.getElementById(id);
let token = "",
  project = null,
  selected = null,
  pageImage = null,
  busy = false;
const checked = new Set();
function remember(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
function recall(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}
function forget(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}
function message(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
async function api(path, options = {}) {
  const headers = { "X-Mashi-Token": token, ...(options.headers || {}) };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
    delete options.json;
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let error;
    try {
      error = await response.json();
    } catch {
      error = { detail: "Request failed. Reload the studio and try again." };
    }
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Check the crop, label and metrics. Some values are invalid.",
    );
  }
  return response;
}
async function work(callback) {
  if (busy) return;
  busy = true;
  document
    .querySelectorAll("button,input,textarea,select")
    .forEach((b) => (b.disabled = true));
  try {
    await callback();
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
    document
      .querySelectorAll("button,input,textarea,select")
      .forEach((b) => (b.disabled = false));
    $("prep-restore").disabled = !project?.preparation_history?.length;
    window.MashiOutline?.refreshControls();
    $("restore-state").disabled = !$("saved-history").value;
  }
}
const url = () => `/api/projects/${project.id}`;
const current = () =>
  project?.regions.find((r) => r.id === selected && r.active);
const cropDraftKey = () => `mashi:crop-draft:${project.id}:${selected}`;
function saveCropDraft() {
  const r = current();
  if (!r) return;
  remember(cropDraftKey(), {
    revision: r.revision,
    image: project.image.canonical_sha256,
    label: $("label").value,
    box: ["x0", "y0", "x1", "y1"].map((k) => Number($(k).value)),
    confirmed: $("confirmed").checked,
  });
  $("crop-draft-note").textContent =
    "Unsaved crop changes are stored in this browser. Save to apply them to the project.";
}
async function loadSavedHistory(r) {
  const id = project.id;
  $("saved-history").replaceChildren();
  $("restore-state").disabled = true;
  try {
    const entries = await (
      await api(`${url()}/regions/${r.id}/history`)
    ).json();
    if (project.id !== id || selected !== r.id) return;
    entries.forEach((e) => {
      const option = document.createElement("option");
      option.value = e.index;
      option.textContent = `Revision ${e.revision} · ${e.has_outline ? "with outline" : "crop/label"} · ${new Date(e.at * 1000).toLocaleString()}`;
      $("saved-history").append(option);
    });
    $("restore-state").disabled = busy || !entries.length;
  } catch (e) {
    $("crop-draft-note").textContent = e.message;
  }
}
async function update(path, options, text) {
  project = await (await api(path, options)).json();
  if (path.endsWith("/vector")) window.MashiOutline?.saved();
  if (options.method === "PUT" && /\/regions\/[a-f0-9]{32}$/.test(path))
    forget(cropDraftKey());
  if (!current())
    selected = project.regions.filter((r) => r.active).at(-1)?.id || null;
  render();
  await renderCoverage();
  message(text);
}
async function recent() {
  const entries = await (await api("/api/projects")).json();
  $("recent").replaceChildren();
  entries.slice(0, 50).forEach((p) => {
    const button = document.createElement("button");
    button.textContent = `${p.name || "Untitled page"} · ${p.image.width} × ${p.image.height}`;
    button.onclick = () => work(() => openProject(p.id));
    $("recent").append(button);
  });
}
async function openProject(id) {
  project = await (await api(`/api/projects/${id}`)).json();
  selected = project.regions.find((r) => r.active)?.id || null;
  checked.clear();
  $("fixture-export").checked = false;
  pageImage = new Image();
  pageImage.src = `${url()}/image`;
  await pageImage.decode();
  $("start").hidden = true;
  $("workspace").hidden = false;
  render();
  await renderCoverage();
  remember("mashi:last-project", id);
  window.MashiCapture?.load().catch((e) => message(e.message, true));
  message(
    "Page ready. Review crop boxes and confirm each exact Malayalam sequence.",
  );
}
async function upload(blob, source = "user-upload") {
  message("Reading the photograph and finding connected ink…");
  const doc = await (
    await api(`/api/projects?source=${source}`, {
      method: "POST",
      body: blob,
      headers: { "Content-Type": blob.type || "application/octet-stream" },
    })
  ).json();
  await openProject(doc.id);
}
function drawPage(drag = null) {
  if (!pageImage) return;
  const canvas = $("page"),
    ctx = canvas.getContext("2d");
  const ratio = Math.min(1, 1400 / pageImage.width); // Display-only transform. Stored coordinates stay canonical.
  canvas.width = Math.round(pageImage.width * ratio);
  canvas.height = Math.round(pageImage.height * ratio);
  ctx.drawImage(pageImage, 0, 0, canvas.width, canvas.height);
  ctx.scale(ratio, ratio);
  project.regions
    .filter((r) => r.active)
    .forEach((r) => {
      const [x0, y0, x1, y1] = r.box;
      ctx.strokeStyle =
        r.id === selected
          ? "#6452a3"
          : checked.has(r.id)
            ? "#316657"
            : "#9c91b3";
      ctx.lineWidth = (r.id === selected ? 3 : 1.3) / ratio;
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
      if (r.id === selected) {
        ctx.fillStyle = "#6452a316";
        ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      }
    });
  if (drag) {
    ctx.strokeStyle = "#316657";
    ctx.lineWidth = 2 / ratio;
    ctx.setLineDash([8 / ratio, 5 / ratio]);
    ctx.strokeRect(drag[0], drag[1], drag[2] - drag[0], drag[3] - drag[1]);
  }
}
function render() {
  const active = project.regions.filter((r) => r.active);
  const fixture = project.source_kind === "synthetic-fixture";
  $("fixture-note").hidden = !fixture;
  $("fixture-export-option").hidden = !fixture;
  $("export-note").textContent = fixture
    ? "Practice shapes are excluded by default. Test exports are explicitly labelled synthetic."
    : "Only confirmed, traced observed ink enters your export.";
  $("page-meta").textContent =
    `${project.image.width} × ${project.image.height} px · EXIF oriented · revision ${project.revision}`;
  $("count").textContent = `${active.length} crops`;
  $("capture-notice").textContent = project.capture_notice || "";
  $("capture-notice").hidden = !project.capture_notice;
  $("page-name").value = project.name || "Untitled page";
  $("regions").replaceChildren();
  active.forEach((r, i) => {
    const row = document.createElement("div");
    row.className = "region-row" + (r.id === selected ? " selected" : "");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = checked.has(r.id);
    check.setAttribute("aria-label", `Select crop ${i + 1} for merging`);
    check.onchange = () => {
      if (check.checked) checked.add(r.id);
      else checked.delete(r.id);
      drawPage();
    };
    const button = document.createElement("button"),
      label = document.createElement("span"),
      detail = document.createElement("small");
    label.lang = "ml";
    label.textContent = r.label || "—";
    detail.textContent = `Crop ${i + 1} · ${r.confirmed ? (r.vector ? "traced ✓" : "confirmed") : "needs review"}`;
    if (r.confirmed && r.vector) detail.className = "ok";
    button.append(label, detail);
    button.onclick = () => {
      selected = r.id;
      render();
    };
    row.append(check, button);
    $("regions").append(row);
  });
  checked.forEach((id) => {
    if (!active.some((r) => r.id === id)) checked.delete(id);
  });
  const r = current();
  $("no-selection").hidden = !!r;
  $("region-form").hidden = !r;
  $("vectors").hidden = !r?.vector;
  drawPage();
  if (!r) return;
  ["x0", "y0", "x1", "y1"].forEach((key, i) => ($(key).value = r.box[i]));
  $("label").value = r.label;
  $("confirmed").checked = r.confirmed;
  const draft = recall(cropDraftKey());
  $("crop-draft-note").textContent = "";
  if (
    draft?.revision === r.revision &&
    draft.image === project.image.canonical_sha256
  ) {
    $("label").value = draft.label;
    $("confirmed").checked = draft.confirmed === true;
    if (Array.isArray(draft.box) && draft.box.length === 4)
      ["x0", "y0", "x1", "y1"].forEach((k, i) => ($(k).value = draft.box[i]));
    $("crop-draft-note").textContent =
      "Recovered unsaved crop draft. Review and save to apply.";
  } else if (draft)
    $("crop-draft-note").textContent =
      "Older crop draft was not applied: the saved revision/image changed. Download it for review or discard it.";
  loadSavedHistory(r);
  showCodepoints();
  $("split-position").value = Math.floor((r.box[0] + r.box[2]) / 2);
  $("suggestion").textContent = r.suggestion
    ? `OCR word suggestion: ${r.suggestion.raw_text} (${Math.round(r.suggestion.confidence)}%). Copy or correct the sequence yourself; this is not a confirmed label.`
    : "Review the whole visible form. Detached marks may need merging with another crop.";
  const crop = $("crop"),
    [x0, y0, x1, y1] = r.box;
  crop.width = x1 - x0;
  crop.height = y1 - y0;
  crop
    .getContext("2d")
    .drawImage(
      pageImage,
      x0,
      y0,
      x1 - x0,
      y1 - y0,
      0,
      0,
      crop.width,
      crop.height,
    );
  $("provenance").textContent =
    r.provenance === "observed"
      ? "OBSERVED INK"
      : r.provenance === "synthetic-fixture"
        ? "SYNTHETIC TEST INK"
        : "GENERATED SUGGESTION";
  if (r.vector) {
    const v = r.vector;
    ["baseline", "scale", "advance"].forEach((k) => ($(k).value = v[k]));
    $("paths").value = JSON.stringify(v.paths, null, 2);
    $("threshold").value = v.threshold;
    $("threshold-value").value = v.threshold;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${v.width} ${v.height}`);
    svg.setAttribute("aria-label", "Traced vector outline");
    v.paths.forEach((d) => {
      const p = document.createElementNS(svg.namespaceURI, "path");
      p.setAttribute("d", d);
      p.setAttribute("fill", "#2b263d");
      svg.append(p);
    });
    const baseline = document.createElementNS(svg.namespaceURI, "line");
    baseline.setAttribute("x1", "0");
    baseline.setAttribute("x2", v.width);
    baseline.setAttribute("y1", v.baseline);
    baseline.setAttribute("y2", v.baseline);
    baseline.setAttribute("stroke", "#6452a3");
    baseline.setAttribute("stroke-width", Math.max(v.height / 200, 0.3));
    baseline.setAttribute("stroke-dasharray", "3 2");
    svg.append(baseline);
    if (window.MashiOutline) window.MashiOutline.load(r, project, pageImage);
    else $("vector-preview").replaceChildren(svg);
    $("svg-download").href = `${url()}/regions/${r.id}/svg`;
    $("svg-download").download = "mashi-glyph.svg";
  }
}
function showCodepoints() {
  $("codepoints").textContent =
    [...$("label").value]
      .map(
        (c) =>
          "U+" + c.codePointAt(0).toString(16).toUpperCase().padStart(4, "0"),
      )
      .join(" · ") ||
    "Exact codepoints will appear here. Joiners are preserved.";
}
async function renderCoverage() {
  const data = await (await api(`${url()}/coverage`)).json();
  $("coverage-title").textContent =
    project.source_kind === "synthetic-fixture"
      ? `${data.synthetic_confirmed.length} traced practice forms`
      : `${data.observed.length} confirmed, traced forms`;
  $("missing").textContent = data.missing.join("  ");
}
$("file").onchange = (event) => {
  const file = event.target.files[0];
  if (file) work(() => upload(file));
  event.target.value = "";
};
$("demo").onclick = () =>
  work(async () => {
    const c = document.createElement("canvas");
    c.width = 900;
    c.height = 650;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, 900, 650);
    ctx.strokeStyle = "#272232";
    ctx.lineWidth = 12;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.ellipse(245, 245, 90, 95, 0.15, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(500, 155);
    ctx.bezierCurveTo(640, 140, 690, 345, 530, 338);
    ctx.bezierCurveTo(460, 335, 480, 260, 570, 265);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(180, 460);
    ctx.bezierCurveTo(220, 400, 350, 440, 320, 505);
    ctx.bezierCurveTo(285, 580, 160, 530, 180, 460);
    ctx.stroke();
    const blob = await new Promise((resolve) => c.toBlob(resolve, "image/png"));
    await upload(blob, "synthetic-fixture");
    message(
      "Synthetic practice shapes loaded. These are geometry fixtures, not real Malayalam handwriting. Assign labels only to explore the workflow.",
    );
  });
$("new-page").onclick = () =>
  work(async () => {
    $("workspace").hidden = true;
    $("start").hidden = false;
    forget("mashi:last-project");
    selected = null;
    await recent();
    message("Choose another photograph, or reopen a saved local page.");
  });
$("page-name-form").onsubmit = (event) => {
  event.preventDefault();
  work(async () => {
    await update(
      `${url()}/name`,
      {
        method: "PUT",
        json: { name: $("page-name").value, revision: project.revision },
      },
      "Page name saved.",
    );
  });
};
$("label").oninput = () => {
  showCodepoints();
  saveCropDraft();
};
["x0", "y0", "x1", "y1"].forEach((k) => ($(k).oninput = saveCropDraft));
$("confirmed").onchange = saveCropDraft;
$("crop-draft-discard").onclick = () => {
  forget(cropDraftKey());
  render();
};
$("crop-draft-download").onclick = () => {
  const draft = recall(cropDraftKey());
  if (!draft) {
    message("No local crop draft to download.");
    return;
  }
  const uri = URL.createObjectURL(
    new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = uri;
  a.download = "Mashi-crop-draft.json";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(uri), 10000);
};
$("restore-state").onclick = () =>
  work(async () => {
    const r = current();
    await update(
      `${url()}/regions/${r.id}/restore`,
      {
        method: "POST",
        json: {
          revision: r.revision,
          history_index: Number($("saved-history").value),
        },
      },
      "Earlier crop, label and outline restored. The replaced state remains in saved history.",
    );
  });
$("region-form").onsubmit = (event) => {
  event.preventDefault();
  work(async () => {
    const r = current();
    await update(
      `${url()}/regions/${r.id}`,
      {
        method: "PUT",
        json: {
          revision: r.revision,
          box: ["x0", "y0", "x1", "y1"].map((k) => Number($(k).value)),
          label: $("label").value,
          confirmed: $("confirmed").checked,
        },
      },
      "Label and crop saved. Trace the ink when the crop is ready.",
    );
  });
};
$("split-axis").onchange = () => {
  const b = current().box,
    i = $("split-axis").value === "x" ? 0 : 1;
  $("split-position").value = Math.floor((b[i] + b[i + 2]) / 2);
};
$("split").onclick = () =>
  work(async () => {
    const r = current();
    await update(
      `${url()}/regions/${r.id}/split`,
      {
        method: "POST",
        json: {
          revision: r.revision,
          axis: $("split-axis").value,
          position: Number($("split-position").value),
        },
      },
      "Crop split. Review and label both new crops.",
    );
  });
$("discard").onclick = () =>
  work(async () => {
    const r = current();
    await update(
      `${url()}/regions/${r.id}?revision=${r.revision}`,
      { method: "DELETE" },
      "Crop discarded. Its history remains in the local project.",
    );
  });
$("merge").onclick = () =>
  work(async () => {
    if (checked.size < 2)
      throw new Error("Check two or more crops in the list, then merge them.");
    const ids = [...checked];
    await update(
      `${url()}/merge`,
      {
        method: "POST",
        json: {
          ids,
          revisions: ids.map(
            (id) => project.regions.find((r) => r.id === id).revision,
          ),
        },
      },
      "Crops merged. Confirm the label of the complete form.",
    );
  });
$("add-crop").onclick = () =>
  work(async () => {
    await update(
      `${url()}/regions`,
      {
        method: "POST",
        json: {
          box: ["new-x0", "new-y0", "new-x1", "new-y1"].map((k) =>
            Number($(k).value),
          ),
        },
      },
      "Crop added. Select it and assign a label.",
    );
    selected = project.regions.at(-1).id;
    render();
  });
$("ocr").onclick = () =>
  work(async () => {
    message("Running local Malayalam OCR…");
    await update(
      `${url()}/ocr`,
      { method: "POST" },
      "OCR word proposals added. Their labels remain unconfirmed; review every crop.",
    );
  });
$("threshold").oninput = () =>
  ($("threshold-value").value = $("threshold").value);
$("trace").onclick = () =>
  work(async () => {
    const r = current();
    message("Tracing the selected pixels…");
    await update(
      `${url()}/regions/${r.id}/trace`,
      {
        method: "POST",
        json: { revision: r.revision, threshold: Number($("threshold").value) },
      },
      "Ink traced. Inspect counters and curves in the outline workbench below.",
    );
  });
$("vector-form").onsubmit = (event) => {
  event.preventDefault();
  work(async () => {
    const r = current();
    let paths;
    try {
      paths = JSON.parse($("paths").value);
    } catch {
      throw new Error(
        "Path geometry must be a JSON list of closed SVG path strings.",
      );
    }
    await update(
      `${url()}/regions/${r.id}/vector`,
      {
        method: "PUT",
        json: {
          revision: r.revision,
          paths,
          baseline: Number($("baseline").value),
          scale: Number($("scale").value),
          advance: Number($("advance").value),
        },
      },
      "Outline and metrics saved.",
    );
  });
};
async function download(kind) {
  const fixture = project.source_kind === "synthetic-fixture";
  if (fixture && !$("fixture-export").checked)
    throw new Error(
      "Practice shapes are excluded. Enable the explicitly labelled synthetic test export first.",
    );
  message(
    kind === "ttf"
      ? "Compiling experimental TTF. This may take a minute…"
      : "Packaging SVG outlines and UFO sources…",
  );
  const response = await api(
    `${url()}/export/${kind}?include_fixture=${fixture && $("fixture-export").checked}`,
    { method: "POST" },
  );
  const blob = await response.blob();
  const objectURL = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = objectURL;
  a.download = `Mashi-${fixture ? "SYNTHETIC-" : ""}${kind}.zip`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectURL), 10000);
  message(
    "Export downloaded. Read coverage.json before using the experimental font.",
  );
}
$("export-ufo").onclick = () => work(() => download("ufo"));
$("export-ttf").onclick = () => work(() => download("ttf"));
let dragStart = null;
function point(event) {
  const rect = $("page").getBoundingClientRect();
  return [
    Math.max(
      0,
      Math.min(
        project.image.width,
        Math.round(
          ((event.clientX - rect.left) / rect.width) * project.image.width,
        ),
      ),
    ),
    Math.max(
      0,
      Math.min(
        project.image.height,
        Math.round(
          ((event.clientY - rect.top) / rect.height) * project.image.height,
        ),
      ),
    ),
  ];
}
$("page").onpointerdown = (event) => {
  if (busy) return;
  const p = point(event);
  if ($("draw-mode").checked) {
    dragStart = p;
    $("page").setPointerCapture(event.pointerId);
  } else {
    const hits = project.regions.filter(
      (r) =>
        r.active &&
        r.box[0] <= p[0] &&
        p[0] < r.box[2] &&
        r.box[1] <= p[1] &&
        p[1] < r.box[3],
    );
    hits.sort(
      (a, b) =>
        (a.box[2] - a.box[0]) * (a.box[3] - a.box[1]) -
        (b.box[2] - b.box[0]) * (b.box[3] - b.box[1]),
    );
    if (hits.length) {
      selected = hits[0].id;
      render();
    }
  }
};
$("page").onpointermove = (event) => {
  if (dragStart) drawPage([...dragStart, ...point(event)]);
};
$("page").onpointercancel = () => {
  dragStart = null;
  drawPage();
};
$("page").onpointerup = (event) => {
  if (!dragStart) return;
  const p = point(event),
    box = [
      Math.min(p[0], dragStart[0]),
      Math.min(p[1], dragStart[1]),
      Math.max(p[0], dragStart[0]),
      Math.max(p[1], dragStart[1]),
    ];
  dragStart = null;
  if (box[2] - box[0] < 2 || box[3] - box[1] < 2) {
    drawPage();
    return;
  }
  work(async () => {
    await update(
      `${url()}/regions`,
      { method: "POST", json: { box } },
      "Crop drawn. Assign its exact label.",
    );
    selected = project.regions.at(-1).id;
    render();
  });
};
work(async () => {
  const session = await (await api("/api/session")).json();
  token = session.token;
  $("ocr").title = session.ocr.reason;
  await recent();
  message(`Ready locally. ${session.ocr.reason}`);
  const saved = recall("mashi:last-project");
  if (typeof saved === "string" && /^[a-f0-9]{32}$/.test(saved)) {
    try {
      await openProject(saved);
      message(
        "Your last saved page was reopened. All saved crops and outlines are local.",
      );
    } catch {
      forget("mashi:last-project");
      message(`Ready locally. ${session.ocr.reason}`);
    }
  }
});
