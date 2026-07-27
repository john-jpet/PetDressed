import numpy as np
from PIL import Image, ImageDraw

from app.metadata import extract_palette, infer_baseline_metadata, rgb_to_lab, visual_embedding


def garment_image() -> Image.Image:
    image = Image.new("RGBA", (320, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 60, 250, 360), fill="#274B77")
    draw.rectangle((70, 250, 250, 360), fill="#E8C7A3")
    return image


def test_rgb_to_lab_reference_points():
    lab = rgb_to_lab(np.array([[255, 255, 255], [0, 0, 0]], dtype=np.uint8))
    assert np.allclose(lab[0], [100, 0, 0], atol=0.02)
    assert np.allclose(lab[1], [0, 0, 0], atol=0.02)


def test_palette_ignores_transparency_and_sorts_by_proportion():
    palette = extract_palette(garment_image(), k=3)
    assert palette
    assert palette[0].proportion >= palette[-1].proportion
    assert sum(color.proportion for color in palette) == pytest.approx(1, abs=0.01)
    assert all(color.hex_value != "#000000" for color in palette)


def test_visual_embedding_is_normalized_and_deterministic():
    first = np.array(visual_embedding(garment_image()))
    second = np.array(visual_embedding(garment_image()))
    assert len(first) == 512
    assert np.linalg.norm(first) == pytest.approx(1, abs=1e-5)
    assert np.array_equal(first, second)


def test_filename_hint_remains_low_confidence_and_editable():
    output = infer_baseline_metadata(garment_image(), "blue-shirt.png")
    assert output.category.value == "top"
    assert 0.5 < output.category.confidence < 0.8
    assert output.colors


def test_unknown_filename_does_not_invent_a_tshirt_classification():
    output = infer_baseline_metadata(garment_image(), "upload-123.png")
    assert output.category.confidence == 0
    assert output.subcategory.value == ""
    assert output.subcategory.confidence == 0
    assert output.model_name == "deterministic-test-fallback"


import pytest
