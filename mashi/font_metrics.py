"""Font-unit metrics; the image-to-outline transform remains owned by tracing."""

import hashlib
import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TypographyOptions:
    """Caller overrides, never changes the project or its exact Unicode labels.

    Anchors are {exact_label: {top|_top: (x, y)}} in 1000-UPM font units.
    top belongs to a base; _top belongs to the visible virama mark.
    """

    family_name: str = "Mashi Handwriting"
    style_name: str = "Regular"
    ascender: int = 1000
    descender: int = -400
    line_gap: int = 100
    space_advance: int = 300
    mark_gap: int = 40
    anchors: dict = field(default_factory=dict)

    def validate(self):
        for name in (self.family_name, self.style_name):
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError("Font family/style must contain 1–100 characters")
            if any(ord(c) < 32 or ord(c) == 127 for c in name):
                raise ValueError("Font names cannot contain control characters")
        if self.style_name != "Regular":
            raise ValueError(
                "V1 exports one Regular style; weight/style variants are not implemented"
            )
        for key, low, high in (
            ("ascender", 1, 16000),
            ("descender", -16000, 0),
            ("line_gap", 0, 4000),
            ("space_advance", 1, 5000),
            ("mark_gap", 0, 1000),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer between {low} and {high}")
        if not isinstance(self.anchors, dict):
            raise ValueError("anchors must be an exact-label mapping")
        for label, anchors in self.anchors.items():
            if not isinstance(label, str) or not isinstance(anchors, dict):
                raise ValueError("anchors must be an exact-label mapping")
            for name, point in anchors.items():
                if name not in {"top", "_top"} or not isinstance(point, (tuple, list)):
                    raise ValueError("Supported anchors are top and _top coordinate pairs")
                if len(point) != 2 or any(
                    type(v) not in {int, float} or not math.isfinite(v) or abs(v) > 16000
                    for v in point
                ):
                    raise ValueError("Anchor coordinates must be finite, within 16,000 units")


def postscript_name(family, style):
    # PS names are ASCII, no delimiters, at most 63 bytes. Display names retain Unicode.
    raw = f"{family}-{style}"
    clean = re.sub(r"[^A-Za-z0-9-]", "", raw)
    if clean != raw or len(clean) > 63:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
        clean = (clean.strip("-") or "Mashi")[:52] + "-" + digest
    return clean


def validate_vector_metrics(vector, *, spacing):
    for key in ("scale", "baseline", "advance"):
        value = vector.get(key)
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError(f"Vector {key} must be finite")
    if not 0.01 < vector["scale"] <= 100 or abs(vector["baseline"]) > 100000:
        raise ValueError("Vector scale or baseline is out of range")
    if not (1 <= round(vector["advance"]) <= 5000 if spacing else 0 <= vector["advance"] <= 5000):
        raise ValueError("Spacing glyphs need a positive advance, at most 5,000 units")
