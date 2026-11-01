import numpy as np
import pytest
from PIL import Image, ImageDraw

from mashi.completion import SDFCompletionModel, distance_field, normalize_ink


def test_model_learns_style_and_reloads_without_pickle(tmp_path):
    labels = ["ക", "ഖ", "ഗ"]
    masks = np.zeros((3, 3, 64, 64), dtype=bool)
    for font in range(3):
        for glyph in range(3):
            masks[font, glyph, 15:45, 15 + font * 3 : 25 + font * 3 + glyph * 2] = True
    fields = np.array([[distance_field(m) for m in f] for f in masks])
    model = SDFCompletionModel.fit(labels, fields)
    predictions, weights = model.predict({"ക": masks[2, 0]})
    assert predictions.shape == (3, 64, 64) and np.isfinite(weights).all()
    assert (
        np.abs(predictions[1] - fields[2, 1]).mean() < np.abs(model.mean[1] - fields[2, 1]).mean()
    )
    checkpoint = tmp_path / "model.npz"
    assert len(model.save(checkpoint)) == 64
    loaded = SDFCompletionModel.load(checkpoint)
    np.testing.assert_allclose(loaded.predict({"ക": masks[2, 0]})[0], predictions)
    with pytest.raises(ValueError):
        loaded.predict({"അ": masks[2, 0]})


def test_completion_normalization_is_shape_only():
    image = Image.new("RGB", (120, 80), "white")
    ImageDraw.Draw(image).ellipse((40, 20, 80, 60), outline="black", width=4)
    mask = normalize_ink(image)
    assert mask.shape == (64, 64) and mask.any() and not mask[32, 32]
    assert distance_field(mask)[32, 32] < 0
    with pytest.raises(ValueError):
        normalize_ink(Image.new("RGB", (50, 50), "white"))
