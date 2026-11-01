"""Regenerable photo preparation with explicit pixel-edge coordinate transforms."""

import io

import cv2
import numpy as np
from PIL import Image

from .imaging import MAX_PIXELS, sha


def map_points(points, matrix):
    points = np.asarray(points, dtype=np.float64)
    homogeneous = np.column_stack([points, np.ones(len(points))]) @ np.asarray(matrix).T
    if np.any(np.abs(homogeneous[:, 2]) < 1e-10):
        raise ValueError("Transform maps a crop outside finite image coordinates")
    return (homogeneous[:, :2] / homogeneous[:, 2:]).tolist()


def source_polygons(box, image):
    x0, y0, x1, y1 = box
    quad = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    source = map_points(quad, image.get("working_to_source", np.eye(3)))
    inverse = image.get("source_to_original")
    if inverse is None:
        # Older projects retained EXIF metadata before numeric transforms existed.
        width, height = image.get("original_size", [image["width"], image["height"]])
        orient = image.get("exif_orientation", 1)
        matrices = {
            2: [[-1, 0, width], [0, 1, 0], [0, 0, 1]],
            3: [[-1, 0, width], [0, -1, height], [0, 0, 1]],
            4: [[1, 0, 0], [0, -1, height], [0, 0, 1]],
            5: [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
            6: [[0, -1, height], [1, 0, 0], [0, 0, 1]],
            7: [[0, -1, height], [-1, 0, width], [0, 0, 1]],
            8: [[0, 1, 0], [-1, 0, width], [0, 0, 1]],
        }
        inverse = np.linalg.inv(matrices.get(orient, np.eye(3)))
    original = map_points(source, inverse)
    return {
        "source_polygon": source,
        "original_polygon": original,
        "image_revision": image.get("preparation_revision", 0),
    }


def geometry(size, corners, rotation):
    width, height = size
    transform = np.eye(3)
    if corners is not None:
        quad = np.asarray(corners, dtype=np.float32)
        if quad.shape != (4, 2) or not np.isfinite(quad).all():
            raise ValueError(
                "Choose four finite page corners: top-left, top-right, bottom-right, bottom-left"
            )
        if np.any(quad < 0) or np.any(quad[:, 0] > width) or np.any(quad[:, 1] > height):
            raise ValueError("Page corners must lie inside the oriented source image")
        if not cv2.isContourConvex(quad) or cv2.contourArea(quad, oriented=True) < 64:
            raise ValueError("Page corners must form a clockwise convex page, without crossing")
        width = round(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3])))
        height = round(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1])))
        if min(width, height) < 8:
            raise ValueError("Selected page is too narrow")
        destination = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        transform = cv2.getPerspectiveTransform(quad, destination)
    if rotation:
        rotate = np.vstack(
            [cv2.getRotationMatrix2D((width / 2, height / 2), rotation, 1), [0, 0, 1]]
        )
        extents = np.asarray(map_points([[0, 0], [width, 0], [width, height], [0, height]], rotate))
        lower, upper = np.floor(extents.min(axis=0)), np.ceil(extents.max(axis=0))
        rotate[:2, 2] -= lower
        width, height = map(int, upper - lower)
        transform = rotate @ transform
    if width * height > MAX_PIXELS or max(width, height) > 16000:
        raise ValueError("Prepared page exceeds 16 megapixels or 16,000 pixels on one edge")
    if not np.isfinite(transform).all() or abs(np.linalg.det(transform)) < 1e-10:
        raise ValueError("Page transform is not invertible")
    return transform, (width, height)


def prepare(image, options):
    matrix, size = geometry(image.size, options.corners, options.rotation)
    # Coordinates are pixel edges; OpenCV samples at integer pixel centers.
    to_edges = np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1]], dtype=float)
    to_centers = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1]], dtype=float)
    raster = cv2.warpPerspective(
        np.array(image.convert("RGB")),
        to_centers @ matrix @ to_edges,
        size,
        flags=cv2.INTER_CUBIC,
        borderValue=(255, 255, 255),
    )
    if options.illumination or options.mode != "keep":
        gray = cv2.cvtColor(raster, cv2.COLOR_RGB2GRAY)
        if options.illumination:
            ratio = min(1, 800 / max(size))
            small = cv2.resize(gray, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
            background = cv2.GaussianBlur(small, (0, 0), 25)
            background = cv2.resize(background, size, interpolation=cv2.INTER_LINEAR)
            corrected = cv2.divide(gray, np.maximum(background, 1), scale=255)
            gray = cv2.addWeighted(
                corrected, options.illumination, gray, 1 - options.illumination, 0
            )
        if options.mode == "global":
            gray = cv2.threshold(gray, options.threshold, 255, cv2.THRESH_BINARY)[1]
        elif options.mode == "adaptive":
            gray = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                options.adaptive_window,
                options.adaptive_bias,
            )
        raster = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    result = Image.fromarray(raster)
    encoded = io.BytesIO()
    result.save(encoded, "PNG")
    data = encoded.getvalue()
    return (
        result,
        data,
        {
            "width": size[0],
            "height": size[1],
            "canonical_sha256": sha(data),
            "source_to_working": matrix.tolist(),
            "working_to_source": np.linalg.inv(matrix).tolist(),
            "options": options.model_dump(),
            "coordinate_convention": "pixel edges; half-open crop bounds",
        },
    )


def suggest_corners(image):
    ratio = min(1, 900 / max(image.size))
    small = np.array(
        image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))))
    )
    edges = cv2.Canny(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        polygon = cv2.approxPolyDP(contour, 0.025 * cv2.arcLength(contour, True), True)
        if (
            len(polygon) == 4
            and cv2.isContourConvex(polygon)
            and cv2.contourArea(polygon) > 0.2 * small.shape[0] * small.shape[1]
        ):
            points = polygon[:, 0, :].astype(float) / ratio
            center = points.mean(axis=0)
            points = points[
                np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
            ]
            points = np.roll(points, -np.argmin(points.sum(axis=1)), axis=0)
            return {
                "corners": points.tolist(),
                "reason": "Suggested paper boundary. Review all four corners before applying.",
            }
    return {
        "corners": [[0, 0], [image.width, 0], [image.width, image.height], [0, image.height]],
        "reason": "No reliable page boundary found. Set the four corners manually.",
    }
