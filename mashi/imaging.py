import hashlib
import io
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Image exceeds 12 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Use a JPEG, PNG or WebP photograph")
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError("Image exceeds 16 megapixels")
                original.load()
                orientation = original.getexif().get(274, 1)
                image = ImageOps.exif_transpose(original).convert("RGBA")
                background = Image.new("RGBA", image.size, "white")
                image = Image.alpha_composite(background, image).convert("RGB")
                metadata = {
                    "original_size": list(original.size),
                    "exif_orientation": orientation,
                    "original_sha256": sha(data),
                }
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Invalid or oversized raster image") from error
    out = io.BytesIO()
    image.save(out, format="PNG")
    canonical = out.getvalue()
    metadata.update(
        {
            "width": image.width,
            "height": image.height,
            "canonical_sha256": sha(canonical),
            "coordinates": "EXIF-oriented pixels, origin top-left, half-open [x0,y0,x1,y1)",
            "transforms": [
                {"operation": "exif_transpose", "orientation": orientation},
                {"operation": "composite_on_white_and_convert_rgb"},
            ],
        }
    )
    return image, canonical, metadata


def validate_box(box, width, height):
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("Crop must be nonempty and inside the oriented page")


def ink_mask(image, threshold=180):
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return (gray < threshold).astype(np.uint8) * 255


def propose_regions(image):
    # Connected ink is just a starting box, never a character/codepoint claim.
    mask = ink_mask(image)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    for x, y, w, h, area in stats[1:count]:
        if area >= 12 and w >= 2 and h >= 2:
            boxes.append(
                [
                    max(0, int(x) - 3),
                    max(0, int(y) - 3),
                    min(image.width, int(x + w) + 3),
                    min(image.height, int(y + h) + 3),
                ]
            )
    if len(boxes) > 1000:
        raise ValueError("Over 1,000 ink regions; use a cleaner or smaller photograph")
    return sorted(boxes, key=lambda b: (b[1], b[0]))
