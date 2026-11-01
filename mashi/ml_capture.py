"""Approved vector → fixed model canvas. No crop stretching or inferred baseline."""

import base64
import hashlib
import io
import json
import math

import cv2
import numpy as np
from PIL import Image
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path

from .ml_engine import NORMALIZATION
from .tracing import validate_paths


def vector_hash(vector):
    return hashlib.sha256(json.dumps(vector, sort_keys=True, allow_nan=False).encode()).hexdigest()


class Polygons(BasePen):
    def __init__(self):
        super().__init__(None)
        self.contours, self.points, self.count = [], [], 0

    def _moveTo(self, point):
        self.points = [point]

    def _lineTo(self, point):
        self.points.append(point)
        self.count += 1
        if self.count > 20000:
            raise ValueError("Reference is too complex for bounded alignment")

    def _curveToOne(self, a, b, end):
        start = self._getCurrentPoint()
        count = min(
            256,
            max(4, math.ceil(sum(math.dist(x, y) for x, y in [(start, a), (a, b), (b, end)]) * 3)),
        )
        for t in np.linspace(0, 1, count + 1)[1:]:
            self._lineTo(
                tuple(
                    (1 - t) ** 3 * start[i]
                    + 3 * (1 - t) ** 2 * t * a[i]
                    + 3 * (1 - t) * t * t * b[i]
                    + t**3 * end[i]
                    for i in range(2)
                )
            )

    def _qCurveToOne(self, control, end):
        start = self._getCurrentPoint()
        count = min(
            256, max(4, math.ceil((math.dist(start, control) + math.dist(control, end)) * 3))
        )
        for t in np.linspace(0, 1, count + 1)[1:]:
            self._lineTo(
                tuple(
                    (1 - t) ** 2 * start[i] + 2 * (1 - t) * t * control[i] + t * t * end[i]
                    for i in range(2)
                )
            )

    def _closePath(self):
        if len(self.points) >= 3:
            self.contours.append(self.points)


def aligned_reference(region):
    vector = region["vector"]
    validate_paths(vector["paths"])
    scale = vector["scale"] * 32 / 1000
    if not math.isfinite(scale) or scale <= 0 or not math.isfinite(vector["baseline"]):
        raise ValueError("Reference baseline/scale must be finite")
    bounds = BoundsPen(None)
    for path in vector["paths"]:
        parse_path(path, bounds)
    if bounds.bounds is None:
        raise ValueError("Reference has no ink")
    x0, y0, x1, y1 = bounds.bounds
    offset = 48 - (x0 + x1) * scale / 2
    baseline = 45 - vector["baseline"] * scale
    if (x1 - x0) * scale > 92 or y0 * scale + baseline < 2 or y1 * scale + baseline > 62:
        raise ValueError(
            f"Reference {region['label']} does not fit the model canvas. Adjust its saved baseline/scale and review alignment."
        )
    pen = Polygons()
    transform = TransformPen(pen, (scale, 0, 0, scale, offset, baseline))
    for path in vector["paths"]:
        parse_path(path, transform)
    winding = np.zeros((64 * 3, 96 * 3), np.int16)
    for contour in pen.contours:
        points = np.rint(np.asarray(contour) * 3).astype(np.int32)
        area = cv2.contourArea(points, oriented=True)
        if area:
            mask = np.zeros_like(winding, np.uint8)
            cv2.fillPoly(mask, [points], 1)
            winding += mask.astype(np.int16) * (1 if area > 0 else -1)
    image = Image.fromarray(np.where(winding != 0, 0, 255).astype(np.uint8)).resize(
        (96, 64), Image.Resampling.LANCZOS
    )
    if not (np.asarray(image) < 128).any():
        raise ValueError("Reference is empty at the model resolution")
    encoded = io.BytesIO()
    image.save(encoded, "PNG")
    data = encoded.getvalue()
    return {
        "id": region["id"],
        "label": region["label"],
        "revision": region["revision"],
        "provenance": region["provenance"],
        "confirmed": True,
        "vector_sha256": vector_hash(vector),
        "png": base64.b64encode(data).decode(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "normalization": NORMALIZATION,
        "crop_to_canonical": [[scale, 0, offset], [0, scale, baseline], [0, 0, 1]],
        "rasterizer": "mashi-vector-winding-3x/v1",
        "box": region["box"],
        "source_polygon": region.get("source_polygon", []),
        "original_polygon": region.get("original_polygon", []),
        "advance": vector["advance"],
    }


def references_current(project, suggestion):
    for reference in suggestion["generation"]["observations"]:
        region = next(
            (r for r in project["regions"] if r["id"] == reference["id"] and r["active"]), None
        )
        if (
            not region
            or not region["confirmed"]
            or not region.get("vector")
            or region["label"] != reference["label"]
            or region["revision"] != reference["revision"]
            or vector_hash(region["vector"]) != reference["vector_sha256"]
        ):
            return False
    return project["image"]["canonical_sha256"] == suggestion["generation"]["image_sha256"]


def pixel_boundaries(image, threshold=180):
    """Exact closed pixel-edge contours for small generated masks, without smoothing.

    Shared edges disappear; the remaining directed edges retain outer/counter
    winding. This is a declared low-resolution fallback, never inferred ink.
    """
    mask = np.asarray(image.convert("L")) < threshold
    height, width = mask.shape
    if width > 96 or height > 64 or not mask.any():
        raise ValueError("Generated pixel fallback requires nonempty ink within 96 × 64")
    edges = {}

    def edge(start, end):
        edges.setdefault(start, []).append(end)

    for y, x in np.argwhere(mask):
        x, y = int(x), int(y)
        if y == 0 or not mask[y - 1, x]:
            edge((x, y), (x + 1, y))
        if x == width - 1 or not mask[y, x + 1]:
            edge((x + 1, y), (x + 1, y + 1))
        if y == height - 1 or not mask[y + 1, x]:
            edge((x + 1, y + 1), (x, y + 1))
        if x == 0 or not mask[y, x - 1]:
            edge((x, y + 1), (x, y))
    contours = []
    while edges:
        start = min(edges)
        points, point = [start], start
        while True:
            end = edges[point].pop()
            if not edges[point]:
                del edges[point]
            points.append(end)
            point = end
            if point == start:
                break
        simplified = []
        for i, p in enumerate(points[:-1]):
            previous, following = points[i - 1 if i else -2], points[i + 1]
            if (p[0] - previous[0]) * (following[1] - p[1]) != (p[1] - previous[1]) * (
                following[0] - p[0]
            ):
                simplified.append(p)
        if len(simplified) >= 3:
            contours.append("M" + "L".join(f"{x} {y}" for x, y in simplified) + "Z")
    paths = ["".join(contours)]
    validate_paths(paths)
    return {
        "paths": paths,
        "width": width,
        "height": height,
        "baseline": 45,
        "scale": 31.25,
        "advance": 1000,
        "threshold": threshold,
        "tracer": "pixel-boundary/v1",
        "edited": False,
        "transform": "x_font = x_crop*scale+50; y_font = (baseline-y_crop)*scale",
    }
