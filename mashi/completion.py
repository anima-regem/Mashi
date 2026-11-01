"""Small CPU research model. Not an enabled studio completion feature.

Learns paired per-form signed-distance-field means and shared font-style axes.
Inference fits a style vector from a subset of normalized observed glyph masks.
"""

import hashlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

GRID = 64


def normalize_ink(image):
    gray = ImageOps.grayscale(image)
    dark = ImageOps.invert(gray)
    bounds = dark.point(lambda p: 255 if p > 100 else 0).getbbox()
    if not bounds:
        raise ValueError("Observed glyph has no dark ink")
    dark = dark.crop(bounds)
    dark.thumbnail((52, 52), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (GRID, GRID), 0)
    canvas.paste(dark, ((GRID - dark.width) // 2, (GRID - dark.height) // 2))
    return np.array(canvas) >= 128


def distance_field(mask):
    mask = np.asarray(mask, dtype=np.uint8)
    if mask.shape != (GRID, GRID):
        raise ValueError("Completion masks must be 64 by 64")
    inside = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    outside = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 5)
    return np.clip((inside - outside) / 8, -1, 1).astype(np.float32)


class SDFCompletionModel:
    """A learned low-rank linear model, not a handwriting foundation model."""

    def __init__(self, labels, mean, basis, ridge=0.1):
        self.labels = list(labels)
        self.mean = np.asarray(mean, dtype=np.float32)
        self.basis = np.asarray(basis, dtype=np.float32)
        self.ridge = ridge

    @classmethod
    def fit(cls, labels, fields, rank=2, ridge=0.1):
        fields = np.asarray(fields, dtype=np.float32)
        if fields.ndim != 4 or fields.shape[1:] != (len(labels), GRID, GRID):
            raise ValueError("Training fields must have shape [fonts, labels, 64, 64]")
        if fields.shape[0] < 3:
            raise ValueError("At least three training fonts are needed for this pilot")
        flat = fields.reshape(fields.shape[0], -1)
        mean = flat.mean(axis=0)
        centered = flat - mean
        # The small fonts×fonts Gram matrix keeps fitting inexpensive on a CPU.
        eigenvalues, eigenvectors = np.linalg.eigh(centered @ centered.T)
        order = np.argsort(eigenvalues)[::-1][: min(rank, fields.shape[0] - 1)]
        components = []
        for index in order:
            if eigenvalues[index] > 1e-8:
                # Scale axes to one standard deviation of training-family variation.
                components.append(eigenvectors[:, index] @ centered / np.sqrt(fields.shape[0] - 1))
        if not components:
            raise ValueError("Training fonts have no distinguishable variation")
        shape = (len(labels), GRID, GRID)
        return cls(labels, mean.reshape(shape), np.stack(components).reshape(-1, *shape), ridge)

    def predict(self, observations):
        known = [label for label in self.labels if label in observations]
        if not known:
            raise ValueError("Supply one or more observed forms from the model inventory")
        indices = [self.labels.index(label) for label in known]
        target = np.stack([distance_field(observations[label]) for label in known])
        basis = self.basis[:, indices].reshape(len(self.basis), -1)
        residual = (target - self.mean[indices]).reshape(-1)
        weights = np.linalg.solve(
            basis @ basis.T + self.ridge * np.eye(len(basis)), basis @ residual
        )
        prediction = self.mean + np.tensordot(weights, self.basis, axes=1)
        return prediction.astype(np.float32), weights

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            labels=np.array(self.labels),
            mean=self.mean,
            basis=self.basis,
            ridge=np.array(self.ridge),
            format_version=np.array(1),
        )
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            if data["format_version"].item() != 1:
                raise ValueError("Unsupported model checkpoint version")
            return cls(data["labels"].tolist(), data["mean"], data["basis"], data["ridge"].item())
