import math
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import vtracer
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from PIL import Image

from .imaging import ink_mask


def validate_paths(paths):
    if not paths:
        raise ValueError("No closed outline paths were found")
    if sum(map(len, paths)) > 500_000:
        raise ValueError("Outline exceeds 500,000 characters")
    for path in paths:
        # Only path geometry. No SVG markup, attributes, external URLs or transforms.
        if not re.fullmatch(r"[MmLlHhVvCcSsQqTtZzEe0-9+.,\s-]+", path):
            raise ValueError("Use SVG path geometry (M/L/C/Q/Z); SVG markup is not accepted")
        try:
            pen = RecordingPen()
            parse_path(path, pen)
            if not pen.value or any(op == "endPath" for op, _ in pen.value):
                raise ValueError("Font contours must be closed")
            for _, points in pen.value:
                for point in points:
                    if point is not None and any(
                        not math.isfinite(v) or abs(v) > 100_000 for v in point
                    ):
                        raise ValueError("Outline coordinate out of range")
        except (TypeError, IndexError, AssertionError) as error:
            raise ValueError("Invalid SVG path geometry") from error


def trace(image, threshold):
    mask = ink_mask(image, threshold)
    if not np.any(mask):
        raise ValueError("No dark ink in this crop; adjust the crop or threshold")
    # Transparent background avoids tracing the paper as a closed white contour.
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = mask
    with tempfile.TemporaryDirectory(prefix="mashi-trace-") as directory:
        raster, vector = Path(directory) / "ink.png", Path(directory) / "ink.svg"
        Image.fromarray(rgba).save(raster)
        vtracer.convert_image_to_svg_py(
            str(raster),
            str(vector),
            colormode="color",
            hierarchical="stacked",
            mode="spline",
            filter_speckle=0,
            color_precision=6,
            layer_difference=16,
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
        root = ET.parse(vector).getroot()
    paths = []
    for element in root.iter("{http://www.w3.org/2000/svg}path"):
        transform = element.get("transform", "")
        match = re.fullmatch(r"translate\(([-\d.eE]+)[ ,]+([-\d.eE]+)\)", transform)
        if transform and not match:
            raise ValueError("Unsupported transform from tracer")
        dx, dy = map(float, match.groups()) if match else (0, 0)
        pen = SVGPathPen(None)
        parse_path(element.attrib["d"], TransformPen(pen, (1, 0, 0, 1, dx, dy)))
        paths.append(pen.getCommands())
    validate_paths(paths)
    scale = round(min(10, 700 / image.height), 6)
    return {
        "paths": paths,
        "width": image.width,
        "height": image.height,
        "baseline": round(image.height * 0.85, 3),
        "scale": scale,
        "advance": round(image.width * scale + 100),
        "threshold": threshold,
        "tracer": "vtracer-0.6.12",
        "transform": "x_font = x_crop*scale+50; y_font = (baseline-y_crop)*scale",
        "edited": False,
    }


def svg(vector, provenance=None, *, generation=None):
    validate_paths(vector["paths"])
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        viewBox=f"0 0 {vector['width']} {vector['height']}",
    )
    if provenance:
        ET.SubElement(root, "metadata").text = "Mashi source provenance: " + provenance
    if generation is not None:
        ET.SubElement(root, "metadata").text = json.dumps(
            {
                "provenance": "model-generated",
                "not_observed_in_photo": True,
                "generation": generation,
            },
            ensure_ascii=False,
        )
    for path in vector["paths"]:
        ET.SubElement(root, "path", d=path, fill="black", **{"fill-rule": "nonzero"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
