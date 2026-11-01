"use strict";
(() => {
  const G = window.MashiGeometry,
    NS = "http://www.w3.org/2000/svg",
    // Match the exporter's baseline metric bound, not the raster's ink bounds.
    BASELINE_LIMIT = 100000;
  let key = "",
    draftKey = "",
    legacyDraftKey = "",
    contours = [],
    metrics = {},
    vector = null,
    activeContour = 0,
    selection = null,
    svg = null,
    view = null,
    rasterURL = "",
    undo = [],
    redo = [],
    drag = null,
    initial = null,
    identity = null;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const state = () => ({ paths: G.serialize(contours), ...metrics });
  function element(tag, attributes = {}) {
    const e = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  }
  function sync(writeMetrics = true) {
    $("paths").value = JSON.stringify(G.serialize(contours), null, 2);
    if (writeMetrics)
      ["baseline", "scale", "advance"].forEach(
        (k) => ($(k).value = metrics[k]),
      );
    $("outline-undo").disabled = !undo.length;
    $("outline-redo").disabled = !redo.length;
  }
  function persist(
    note = "Unsaved outline changes. Save to keep them in the project.",
    writeMetrics = true,
  ) {
    const saved = remember(draftKey, { ...identity, state: state() });
    $("outline-status").textContent =
      saved === false
        ? "Browser draft storage is unavailable. Save this outline before leaving."
        : note;
    sync(writeMetrics);
  }
  function history(before) {
    if (JSON.stringify(before) !== JSON.stringify(state())) {
      undo.push(before);
      if (undo.length > 50) undo.shift();
      redo = [];
      persist();
    }
    sync();
  }
  function contourOptions() {
    activeContour = Math.min(activeContour, contours.length - 1);
    $("outline-contour").replaceChildren(
      ...contours.map((c, i) => {
        const option = document.createElement("option");
        option.value = i;
        option.textContent = `Contour ${i + 1} · ${G.anchors(c).length} nodes`;
        return option;
      }),
    );
    $("outline-contour").value = activeContour;
  }
  function apply(next) {
    contours = G.parse(next.paths);
    metrics = {
      baseline: next.baseline,
      scale: next.scale,
      advance: next.advance,
    };
    selection = null;
    activeContour = 0;
    $("point-form").hidden = true;
    contourOptions();
    sync();
    draw();
    persist();
  }
  function fit() {
    const width = Math.max(
      vector.width,
      Math.min(vector.width * 2, (metrics.advance - 50) / metrics.scale),
    );
    const top = Math.min(0, metrics.baseline),
      bottom = Math.max(vector.height, metrics.baseline),
      margin = Math.max(vector.width, bottom - top) * 0.12;
    view = [-margin, top - margin, width + margin * 2, bottom - top + margin * 2];
    draw();
  }
  function zoom(factor) {
    const [x, y, w, h] = view;
    view = [
      x + (w * (1 - factor)) / 2,
      y + (h * (1 - factor)) / 2,
      w * factor,
      h * factor,
    ];
    draw();
  }
  function selectedPoint() {
    if (!selection) return null;
    const c = contours[selection.contour];
    return selection.kind === "anchor"
      ? selection.index === 0
        ? c.start
        : c.segments[selection.index - 1].to
      : c.segments[selection.segment][selection.kind];
  }
  function move(dx, dy) {
    if (!selection) return;
    if (selection.kind === "anchor")
      G.moveAnchor(contours[selection.contour], selection.index, dx, dy);
    else {
      const p = selectedPoint();
      p[0] += dx;
      p[1] += dy;
    }
  }
  function choose(ref) {
    selection = ref;
    const p = selectedPoint();
    $("point-x").value = p[0];
    $("point-y").value = p[1];
    $("point-form").hidden = false;
    draw();
  }
  function screenPoint(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const p = point.matrixTransform(svg.getScreenCTM().inverse());
    return [p.x, p.y];
  }
  function beginPoint(event, ref) {
    if (busy) return;
    event.stopPropagation();
    event.preventDefault();
    choose(ref);
    drag = {
      kind: "point",
      before: state(),
      last: screenPoint(event),
      pointer: event.pointerId,
    };
    svg.setPointerCapture(event.pointerId);
  }
  function keyPoint(event, ref) {
    if (busy) return;
    if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      choose(ref);
      return;
    }
    if (
      !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)
    )
      return;
    event.preventDefault();
    selection = ref;
    $("point-form").hidden = false;
    const before = state(),
      amount = event.shiftKey ? 10 : event.altKey ? 0.1 : 1;
    move(
      event.key === "ArrowLeft"
        ? -amount
        : event.key === "ArrowRight"
          ? amount
          : 0,
      event.key === "ArrowUp"
        ? -amount
        : event.key === "ArrowDown"
          ? amount
          : 0,
    );
    history(before);
    draw();
  }
  function handle(point, ref, label, kind = "anchor") {
    const selected =
      selection && JSON.stringify(selection) === JSON.stringify(ref);
    const rect = svg.getBoundingClientRect(),
      size = Math.max(
        view[2] / Math.max(200, rect.width),
        view[3] / Math.max(200, rect.height),
      );
    const circle = element("circle", {
      cx: point[0],
      cy: point[1],
      r: (kind === "anchor" ? 4.8 : 3.8) * size,
      class: `outline-${kind}${selected ? " selected" : ""}`,
      tabindex: 0,
      role: "button",
      "aria-label": label,
      "data-testid":
        kind === "anchor"
          ? `outline-node-${ref.index}`
          : `outline-${ref.kind}-${ref.segment}`,
    });
    circle.onpointerdown = (e) => beginPoint(e, ref);
    circle.onkeydown = (e) => keyPoint(e, ref);
    circle.onclick = () => choose(ref);
    svg.append(circle);
  }
  function draw() {
    if (!svg || !view) return;
    const focus = document.activeElement?.closest("#vector-preview")
      ? document.activeElement.getAttribute("data-testid")
      : null;
    svg.setAttribute("viewBox", view.join(" "));
    svg.replaceChildren();
    const rect = svg.getBoundingClientRect(),
      size = Math.max(
        view[2] / Math.max(200, rect.width),
        view[3] / Math.max(200, rect.height),
      );
    if ($("outline-overlay").checked)
      svg.append(
        element("image", {
          href: rasterURL,
          x: 0,
          y: 0,
          width: vector.width,
          height: vector.height,
          opacity: $("outline-opacity").value,
          "pointer-events": "none",
        }),
      );
    G.serialize(contours).forEach((d) =>
      svg.append(
        element("path", {
          d,
          fill: "#2b263d",
          "fill-rule": "nonzero",
          "fill-opacity": $("outline-overlay").checked ? 0.45 : 1,
          stroke: "#6452a3",
          "stroke-width": 0.7 * size,
          "pointer-events": "none",
        }),
      ),
    );
    const baseline = element("line", {
      x1: view[0],
      x2: view[0] + view[2],
      y1: metrics.baseline,
      y2: metrics.baseline,
      class: "outline-guide",
      "stroke-width": 2 * size,
      "stroke-dasharray": `${5 * size} ${4 * size}`,
      tabindex: 0,
      role: "slider",
      "aria-label": "Drag baseline",
      "data-testid": "outline-baseline",
      "aria-orientation": "vertical",
      "aria-valuenow": metrics.baseline,
      "aria-valuemin": -BASELINE_LIMIT,
      "aria-valuemax": BASELINE_LIMIT,
    });
    baseline.onpointerdown = (e) => {
      if (busy) return;
      e.preventDefault();
      drag = { kind: "baseline", before: state() };
      svg.setPointerCapture(e.pointerId);
    };
    baseline.onkeydown = (e) => {
      if (busy) return;
      if (!["ArrowUp", "ArrowDown"].includes(e.key)) return;
      e.preventDefault();
      const before = state();
      metrics.baseline = Math.max(
        -BASELINE_LIMIT,
        Math.min(
          BASELINE_LIMIT,
          metrics.baseline + (e.key === "ArrowUp" ? -1 : 1) * (e.shiftKey ? 10 : e.altKey ? 0.1 : 1),
        ),
      );
      history(before);
      draw();
    };
    svg.append(baseline);
    const advanceX = (metrics.advance - 50) / metrics.scale;
    const advance = element("line", {
      x1: advanceX,
      x2: advanceX,
      y1: view[1],
      y2: view[1] + view[3],
      class: "outline-advance",
      "stroke-width": 2 * size,
      "stroke-dasharray": `${5 * size} ${4 * size}`,
      tabindex: 0,
      role: "slider",
      "aria-label": "Drag advance width",
      "data-testid": "outline-advance",
      "aria-valuenow": metrics.advance,
      "aria-valuemin": 0,
      "aria-valuemax": 5000,
    });
    advance.onpointerdown = (e) => {
      if (busy) return;
      e.preventDefault();
      drag = { kind: "advance", before: state() };
      svg.setPointerCapture(e.pointerId);
    };
    advance.onkeydown = (e) => {
      if (busy || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key))
        return;
      e.preventDefault();
      const before = state();
      metrics.advance =
        e.key === "Home"
          ? 0
          : e.key === "End"
            ? 5000
            : Math.max(
                0,
                Math.min(
                  5000,
                  metrics.advance +
                    (e.key === "ArrowLeft" ? -1 : 1) * (e.shiftKey ? 10 : 1),
                ),
              );
      history(before);
      draw();
    };
    svg.append(advance);
    const c = contours[activeContour];
    if (!c) return;
    let start = c.start;
    c.segments.forEach((s, index) => {
      if (s.c1) {
        svg.append(
          element("line", {
            x1: start[0],
            y1: start[1],
            x2: s.c1[0],
            y2: s.c1[1],
            class: "outline-control-line",
            "stroke-width": size,
          }),
        );
        handle(
          s.c1,
          { contour: activeContour, segment: index, kind: "c1" },
          `Control 1 for segment ${index + 1}`,
          "control",
        );
      }
      if (s.c2) {
        svg.append(
          element("line", {
            x1: s.to[0],
            y1: s.to[1],
            x2: s.c2[0],
            y2: s.c2[1],
            class: "outline-control-line",
            "stroke-width": size,
          }),
        );
        handle(
          s.c2,
          { contour: activeContour, segment: index, kind: "c2" },
          `Control 2 for segment ${index + 1}`,
          "control",
        );
      }
      start = s.to;
    });
    G.anchors(c).forEach(({ index, point }) =>
      handle(
        point,
        { contour: activeContour, index, kind: "anchor" },
        `Node ${index + 1} of contour ${activeContour + 1}`,
      ),
    );
    const p = selectedPoint();
    if (p) {
      $("point-x").value = Math.round(p[0] * 1000) / 1000;
      $("point-y").value = Math.round(p[1] * 1000) / 1000;
    }
    if (focus)
      svg
        .querySelector(`[data-testid="${focus}"]`)
        ?.focus({ preventScroll: true });
  }
  function load(region, doc, page) {
    const nextKey =
      doc.id +
      ":" +
      (doc.page_id || doc.id) + ":" +
      region.id +
      ":" +
      region.revision +
      ":" +
      doc.image.canonical_sha256;
    if (nextKey === key && svg?.isConnected) {
      sync();
      return;
    }
    key = nextKey;
    draftKey = `mashi:outline-draft:${doc.id}:${doc.page_id || doc.id}:${region.id}`;
    legacyDraftKey = !doc.page_id || doc.page_id === doc.id ? `mashi:outline-draft:${doc.id}:${region.id}` : "";
    identity = { page_id: doc.page_id, revision: region.revision, image: doc.image.canonical_sha256,
      provenance: region.provenance, input_kind: doc.source_kind,
      ...(region.generation ? {generation:region.generation, vectorization:region.vectorization, not_observed_in_photo:true} : {}) };
    vector = region.vector;
    initial = {
      paths: clone(vector.paths),
      baseline: vector.baseline,
      scale: vector.scale,
      advance: vector.advance,
    };
    let chosen = initial,
      note = "Saved outline. Choose a node or control handle to edit.";
    const draft = recall(draftKey) || (legacyDraftKey ? recall(legacyDraftKey) : null);
    if (
      draft?.revision === identity.revision &&
      draft.image === identity.image
    ) {
      chosen = draft.state;
      note = "Recovered unsaved outline draft. Review it, then save.";
    } else if (draft)
      note =
        "An older draft was not applied because the saved form or photo changed.";
    try {
      contours = G.parse(chosen.paths);
    } catch {
      contours = G.parse(initial.paths);
      chosen = initial;
      note = "The draft could not be read. The saved outline is shown.";
    }
    metrics = {
      baseline: chosen.baseline,
      scale: chosen.scale,
      advance: chosen.advance,
    };
    undo = [];
    redo = [];
    selection = null;
    activeContour = 0;
    const crop = document.createElement("canvas"),
      [x0, y0, x1, y1] = region.box;
    crop.width = x1 - x0;
    crop.height = y1 - y0;
    crop
      .getContext("2d")
      .drawImage(
        page,
        x0,
        y0,
        crop.width,
        crop.height,
        0,
        0,
        crop.width,
        crop.height,
      );
    rasterURL = crop.toDataURL("image/png");
    svg = element("svg", {
      role: "group",
      "aria-label": "Visual outline editor",
      tabindex: 0,
    });
    $("vector-preview").replaceChildren(svg);
    svg.onpointerdown = (e) => {
      if (e.target === svg && $("outline-pan").checked) {
        drag = {
          kind: "pan",
          last: [e.clientX, e.clientY],
          beforeView: [...view],
        };
        svg.setPointerCapture(e.pointerId);
      }
    };
    svg.onpointermove = (e) => {
      if (!drag) return;
      const p = screenPoint(e);
      if (drag.kind === "point") {
        move(p[0] - drag.last[0], p[1] - drag.last[1]);
        drag.last = p;
      } else if (drag.kind === "baseline")
        metrics.baseline = Math.max(-BASELINE_LIMIT, Math.min(BASELINE_LIMIT, p[1]));
      else if (drag.kind === "advance")
        metrics.advance = Math.max(
          0,
          Math.min(5000, p[0] * metrics.scale + 50),
        );
      else {
        const rect = svg.getBoundingClientRect();
        view[0] =
          drag.beforeView[0] -
          ((e.clientX - drag.last[0]) / rect.width) * view[2];
        view[1] =
          drag.beforeView[1] -
          ((e.clientY - drag.last[1]) / rect.height) * view[3];
      }
      sync();
      draw();
    };
    const end = () => {
      if (drag && drag.kind !== "pan") history(drag.before);
      drag = null;
    };
    svg.onpointerup = end;
    svg.onpointercancel = end;
    svg.onkeydown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        (e.shiftKey ? redoAction : undoAction)();
      }
    };
    contourOptions();
    $("point-form").hidden = true;
    $("outline-status").textContent = note;
    sync();
    fit();
  }
  function undoAction() {
    if (busy) return;
    if (!undo.length) return;
    redo.push(state());
    apply(undo.pop());
    sync();
  }
  function redoAction() {
    if (busy) return;
    if (!redo.length) return;
    undo.push(state());
    apply(redo.pop());
    sync();
  }
  $("outline-undo").onclick = undoAction;
  $("outline-redo").onclick = redoAction;
  $("outline-zoom-in").onclick = () => zoom(0.8);
  $("outline-zoom-out").onclick = () => zoom(1.25);
  $("outline-fit").onclick = fit;
  $("outline-overlay").onchange = draw;
  $("outline-opacity").oninput = draw;
  $("outline-contour").onchange = () => {
    activeContour = Number($("outline-contour").value);
    selection = null;
    $("point-form").hidden = true;
    draw();
  };
  $("point-form").onsubmit = (e) => {
    e.preventDefault();
    const p = selectedPoint();
    if (!p) return;
    const x = Number($("point-x").value),
      y = Number($("point-y").value);
    if (!Number.isFinite(x + y) || Math.abs(x) > 100000 || Math.abs(y) > 100000)
      return;
    const before = state();
    move(x - p[0], y - p[1]);
    history(before);
    draw();
  };
  ["baseline", "scale", "advance"].forEach((name) => {
    let before = null;
    $(name).onfocus = () => {
      before = state();
    };
    $(name).oninput = () => {
      const n = Number($(name).value);
      if (Number.isFinite(n) && (name !== "scale" || n > 0)) {
        metrics[name] = n;
        $("paths").value = JSON.stringify(G.serialize(contours), null, 2);
        draw();
        persist(undefined, false);
      }
    };
    $(name).onblur = () => {
      if (before) {
        history(before);
        before = null;
      }
    };
  });
  $("outline-apply-paths").onclick = () => {
    try {
      const before = state();
      contours = G.parse(JSON.parse($("paths").value));
      activeContour = 0;
      selection = null;
      contourOptions();
      history(before);
      draw();
    } catch (e) {
      message(e.message, true);
    }
  };
  $("outline-discard-draft").onclick = () => {
    forget(draftKey);
    if (legacyDraftKey) forget(legacyDraftKey);
    contours = G.parse(initial.paths);
    metrics = {
      baseline: initial.baseline,
      scale: initial.scale,
      advance: initial.advance,
    };
    undo = [];
    redo = [];
    selection = null;
    activeContour = 0;
    contourOptions();
    $("point-form").hidden = true;
    $("outline-status").textContent =
      "Draft discarded. Saved outline restored.";
    sync();
    draw();
  };
  $("outline-download-draft").onclick = () => {
    const draft = recall(draftKey) || (legacyDraftKey ? recall(legacyDraftKey) : null);
    if (!draft) {
      message("No outline draft to download.");
      return;
    }
    const uri = URL.createObjectURL(
      new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = uri;
    a.download = "Mashi-outline-draft.json";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(uri), 10000);
  };
  window.MashiOutline = {
    load,
    refreshControls() {
      $("outline-undo").disabled = !undo.length;
      $("outline-redo").disabled = !redo.length;
    },
    saved() {
      forget(draftKey);
      if (legacyDraftKey) forget(legacyDraftKey);
      key = "";
    },
  };
  window.addEventListener("resize", () => {
    if (svg?.isConnected) draw();
  });
  if (project && current()?.vector && !generatedSelection(current())) load(current(), project, pageImage);
})();
