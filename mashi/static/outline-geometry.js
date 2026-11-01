"use strict";
(() => {
  function parse(paths) {
    if (
      !Array.isArray(paths) ||
      !paths.length ||
      paths.some((p) => typeof p !== "string")
    )
      throw new Error("Use a list of closed SVG paths.");
    if (paths.join("").length > 500000)
      throw new Error("Outline is too large.");
    const contours = [];
    paths.forEach((path, pathIndex) => {
      const expression =
        /[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g;
      if (path.replace(expression, "").replace(/[\s,]/g, ""))
        throw new Error(
          "Visual editing supports M/L/H/V/C/S/Q/T/Z geometry only.",
        );
      const tokens = path.match(expression) || [];
      let i = 0,
        command = null,
        current = [0, 0],
        contour = null,
        previous = null;
      const number = () => {
        if (i >= tokens.length || /^[a-z]$/i.test(tokens[i]))
          throw new Error("Incomplete path coordinates.");
        const n = Number(tokens[i++]);
        if (!Number.isFinite(n) || Math.abs(n) > 100000)
          throw new Error("Outline coordinate out of range.");
        return n;
      };
      while (i < tokens.length) {
        if (/^[a-z]$/i.test(tokens[i])) command = tokens[i++];
        if (!command) throw new Error("A path command is required.");
        const type = command.toUpperCase(),
          relative = command !== type;
        const point = () => {
          const p = [number(), number()];
          return relative ? [p[0] + current[0], p[1] + current[1]] : p;
        };
        if (type === "Z") {
          if (!contour) throw new Error("Unexpected close command.");
          const last = contour.segments.at(-1);
          if (
            last &&
            Math.hypot(
              last.to[0] - contour.start[0],
              last.to[1] - contour.start[1],
            ) < 1e-7
          )
            last.to = contour.start;
          contours.push(contour);
          current = [...contour.start];
          contour = null;
          previous = null;
          command = null;
          continue;
        }
        if (type === "M") {
          if (contour)
            throw new Error("Close each contour before starting another.");
          current = point();
          contour = { path: pathIndex, start: current, segments: [] };
          command = relative ? "l" : "L";
          previous = null;
          continue;
        }
        if (!contour) throw new Error("Start each contour with M.");
        let segment;
        if (type === "L") segment = { type: "L", to: point() };
        else if (type === "H")
          segment = {
            type: "L",
            to: [number() + (relative ? current[0] : 0), current[1]],
          };
        else if (type === "V")
          segment = {
            type: "L",
            to: [current[0], number() + (relative ? current[1] : 0)],
          };
        else if (type === "C")
          segment = { type: "C", c1: point(), c2: point(), to: point() };
        else if (type === "S")
          segment = {
            type: "C",
            c1:
              previous?.type === "C"
                ? [
                    2 * current[0] - previous.c2[0],
                    2 * current[1] - previous.c2[1],
                  ]
                : [...current],
            c2: point(),
            to: point(),
          };
        else if (type === "Q")
          segment = { type: "Q", c1: point(), to: point() };
        else if (type === "T")
          segment = {
            type: "Q",
            c1:
              previous?.type === "Q"
                ? [
                    2 * current[0] - previous.c1[0],
                    2 * current[1] - previous.c1[1],
                  ]
                : [...current],
            to: point(),
          };
        else throw new Error("Unsupported path command.");
        contour.segments.push(segment);
        current = segment.to;
        previous = segment;
      }
      if (contour) throw new Error("Font contours must remain closed with Z.");
    });
    if (!contours.length) throw new Error("No closed contours.");
    return contours;
  }
  function serialize(contours) {
    const groups = new Map();
    const point = (p) =>
      p
        .map((n) => {
          if (!Number.isFinite(n) || Math.abs(n) > 100000)
            throw new Error("Outline coordinate out of range.");
          return Object.is(n, -0) ? "0" : String(n);
        })
        .join(" ");
    contours.forEach((c) => {
      let path = "M" + point(c.start);
      for (const s of c.segments)
        path +=
          s.type +
          (s.c1 ? point(s.c1) + " " : "") +
          (s.c2 ? point(s.c2) + " " : "") +
          point(s.to);
      path += "Z";
      groups.set(c.path, (groups.get(c.path) || "") + path);
    });
    return [...groups.values()];
  }
  function anchors(contour) {
    const list = [{ index: 0, point: contour.start }];
    contour.segments.forEach((s, i) => {
      if (s.to !== contour.start) list.push({ index: i + 1, point: s.to });
    });
    return list;
  }
  function moveAnchor(contour, index, dx, dy) {
    const anchor = index === 0 ? contour.start : contour.segments[index - 1].to;
    const incoming =
      index === 0
        ? contour.segments.at(-1)?.to === contour.start
          ? contour.segments.at(-1)
          : null
        : contour.segments[index - 1];
    const outgoing = contour.segments[index];
    const controls = new Set(
      [
        incoming?.c2 || (incoming?.type === "Q" ? incoming.c1 : null),
        outgoing?.c1,
      ].filter(Boolean),
    );
    for (const p of [anchor, ...controls]) {
      p[0] += dx;
      p[1] += dy;
    }
  }
  const api = { parse, serialize, anchors, moveAnchor };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else window.MashiGeometry = api;
})();
