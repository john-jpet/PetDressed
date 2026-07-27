from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.segmentation import (
    CpuForegroundSegmenter,
    Prompt,
    apply_mask_runs,
    normalize_image,
    render_artifacts,
)


def synthetic_shirt() -> Image.Image:
    image = Image.new("RGB", (480, 600), "#f7f4eb")
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [
            (150, 120),
            (90, 190),
            (130, 270),
            (170, 235),
            (170, 500),
            (310, 500),
            (310, 235),
            (350, 270),
            (390, 190),
            (330, 120),
            (280, 105),
            (265, 145),
            (215, 145),
            (200, 105),
        ],
        fill="#274b77",
    )
    return image


def test_cpu_segmenter_creates_transparent_crop():
    image = synthetic_shirt()
    result = CpuForegroundSegmenter().segment(image)
    artifacts = render_artifacts(image, result.mask)
    with Image.open(BytesIO(artifacts.processed_png)) as processed:
        assert processed.mode == "RGBA"
        assert processed.width < image.width
        assert processed.height < image.height
        assert processed.getextrema()[3][0] == 0
    assert 0.15 < artifacts.mask_area_ratio < 0.5
    assert result.model_name == "cpu-foreground"


def test_bounding_box_prompt_limits_foreground():
    image = synthetic_shirt()
    result = CpuForegroundSegmenter().segment(image, Prompt(bbox=(100, 100, 380, 520)))
    ys, xs = np.where(result.mask)
    assert xs.min() >= 100
    assert xs.max() < 380
    assert ys.min() >= 100
    assert ys.max() < 520


def test_mask_runs_are_bounds_checked():
    mask = np.zeros((10, 10), dtype=bool)
    changed = apply_mask_runs(mask, [(11, 4, 1)])
    assert changed.reshape(-1)[11:15].all()
    with pytest.raises(ValueError):
        apply_mask_runs(mask, [(99, 2, 1)])


def test_normalization_downscales_large_image():
    image = Image.new("RGB", (2200, 1100), "white")
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    normalized = normalize_image(buffer.getvalue(), 1000)
    assert normalized.size == (1000, 500)
