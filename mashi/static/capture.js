"use strict";
(() => {
  let source = null,
    points = [],
    key = "",
    previewURL = null,
    timer = null,
    requestNumber = 0,
    drag = null;
  const fields = [
    "prep-rotation",
    "prep-light",
    "prep-mode",
    "prep-threshold",
    "prep-window",
    "prep-bias",
  ];
  function options() {
    return {
      corners: $("prep-perspective").checked ? points : null,
      rotation: Number($("prep-rotation").value),
      illumination: Number($("prep-light").value),
      mode: $("prep-mode").value,
      threshold: Number($("prep-threshold").value),
      adaptive_window: Number($("prep-window").value),
      adaptive_bias: Number($("prep-bias").value),
    };
  }
  function draw() {
    if (!source) return;
    const c = $("prep-source"),
      ratio = Math.min(1, 1000 / source.width);
    c.width = Math.round(source.width * ratio);
    c.height = Math.round(source.height * ratio);
    const ctx = c.getContext("2d");
    ctx.drawImage(source, 0, 0, c.width, c.height);
    ctx.scale(ratio, ratio);
    if (!$("prep-perspective").checked) return;
    ctx.strokeStyle = "#6452a3";
    ctx.lineWidth = 3 / ratio;
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(...p) : ctx.moveTo(...p)));
    ctx.closePath();
    ctx.stroke();
    points.forEach((p, i) => {
      ctx.fillStyle = "#6452a3";
      ctx.beginPath();
      ctx.arc(...p, 8 / ratio, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "white";
      ctx.font = `${11 / ratio}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(i + 1), ...p);
    });
  }
  function cornerFields() {
    $("prep-corners").replaceChildren();
    points.forEach((point, i) => {
      const row = document.createElement("div"),
        name = document.createElement("span");
      name.textContent = [
        "Top left",
        "Top right",
        "Bottom right",
        "Bottom left",
      ][i];
      row.append(name);
      point.forEach((value, axis) => {
        const label = document.createElement("label"),
          input = document.createElement("input");
        label.textContent = axis ? "Y" : "X";
        input.type = "number";
        input.step = "0.1";
        input.min = 0;
        input.max = axis ? source.height : source.width;
        input.value = Math.round(value * 10) / 10;
        input.setAttribute(
          "aria-label",
          `${name.textContent} ${axis ? "Y" : "X"}`,
        );
        input.oninput = () => {
          points[i][axis] = Number(input.value);
          draw();
          schedule();
        };
        label.append(input);
        row.append(label);
      });
      $("prep-corners").append(row);
    });
  }
  async function preview() {
    if (!source || !project) return;
    const number = ++requestNumber;
    $("prep-preview-note").textContent = "Preparing preview…";
    try {
      const response = await api(`${url()}/preparation/preview`, {
        method: "POST",
        json: options(),
      });
      const blob = await response.blob();
      if (number !== requestNumber) return;
      if (previewURL) URL.revokeObjectURL(previewURL);
      previewURL = URL.createObjectURL(blob);
      $("prep-preview").src = previewURL;
      $("prep-preview-note").textContent =
        `Prepared size: ${response.headers.get("X-Prepared-Width")} × ${response.headers.get("X-Prepared-Height")} pixels. Source pixels remain preserved.`;
    } catch (e) {
      if (number === requestNumber)
        $("prep-preview-note").textContent = e.message;
    }
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(preview, 450);
  }
  async function load() {
    if (!project || !$("photo-prep").open) return;
    const newKey = project.id + ":" + (project.image.preparation_revision || 0);
    if (key === newKey && source?.complete && source.naturalWidth) return;
    key = newKey;
    source = new Image();
    source.src = `${url()}/source-image`;
    await source.decode();
    const state = project.preparation || {};
    points = state.corners?.map((p) => [...p]) || [
      [0, 0],
      [source.width, 0],
      [source.width, source.height],
      [0, source.height],
    ];
    $("prep-perspective").checked = !!state.corners;
    [
      "rotation",
      "illumination",
      "mode",
      "threshold",
      "adaptive_window",
      "adaptive_bias",
    ].forEach(
      (k, i) =>
        ($(fields[i]).value = state[k] ?? [0, 0, "keep", 180, 51, 11][i]),
    );
    cornerFields();
    draw();
    $("prep-restore").disabled = !project.preparation_history?.length;
    await preview();
  }
  $("photo-prep").ontoggle = () => {
    if ($("photo-prep").open) load().catch((e) => message(e.message, true));
  };
  fields.forEach((id) => ($(id).oninput = schedule));
  $("prep-perspective").onchange = () => {
    draw();
    schedule();
  };
  $("prep-preview-button").onclick = () => preview();
  $("prep-detect").onclick = () =>
    work(async () => {
      const found = await (
        await api(`${url()}/preparation/suggest`, { method: "POST" })
      ).json();
      points = found.corners;
      $("prep-perspective").checked = true;
      cornerFields();
      draw();
      await preview();
      $("prep-feedback").textContent = found.reason;
    });
  $("prep-apply").onclick = () =>
    work(async () => {
      const id = project.id;
      message("Applying preparation from the preserved source…");
      await api(`${url()}/preparation`, {
        method: "POST",
        json: { ...options(), revision: project.revision },
      });
      key = "";
      await openProject(id);
      await load();
      message(
        "Prepared page saved. New crop proposals need review; previous crops can be restored.",
      );
    });
  $("prep-restore").onclick = () =>
    work(async () => {
      const id = project.id;
      await api(`${url()}/preparation/restore`, {
        method: "POST",
        json: { revision: project.revision },
      });
      key = "";
      await openProject(id);
      await load();
      message("Previous image, labels, crops and outlines restored.");
    });
  const c = $("prep-source");
  const point = (e) => {
    const rect = c.getBoundingClientRect();
    return [
      Math.max(
        0,
        Math.min(
          source.width,
          ((e.clientX - rect.left) / rect.width) * source.width,
        ),
      ),
      Math.max(
        0,
        Math.min(
          source.height,
          ((e.clientY - rect.top) / rect.height) * source.height,
        ),
      ),
    ];
  };
  c.onpointerdown = (e) => {
    if (!source || !$("prep-perspective").checked) return;
    const p = point(e),
      distances = points.map((q) => Math.hypot(q[0] - p[0], q[1] - p[1]));
    const i = distances.indexOf(Math.min(...distances));
    if (distances[i] < (source.width / c.getBoundingClientRect().width) * 32) {
      drag = i;
      c.setPointerCapture(e.pointerId);
    }
  };
  c.onpointermove = (e) => {
    if (drag === null) return;
    points[drag] = point(e);
    draw();
    cornerFields();
  };
  c.onpointerup = () => {
    if (drag !== null) {
      drag = null;
      schedule();
    }
  };
  c.onpointercancel = () => {
    drag = null;
  };
  window.MashiCapture = { load };
  window.addEventListener("resize",()=>{if(source&&$("photo-prep").open)draw();});
})();
