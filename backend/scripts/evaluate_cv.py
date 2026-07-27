from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import get_settings
from app.segmentation import create_segmenter, normalize_image


def intersection_over_union(predicted: np.ndarray, expected: np.ndarray) -> float:
    predicted = predicted.astype(bool)
    expected = expected.astype(bool)
    intersection = np.logical_and(predicted, expected).sum()
    union = np.logical_or(predicted, expected).sum()
    return float(intersection / union) if union else 1.0


def evaluate(manifest_path: Path) -> dict:
    records = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        return {"labelled_samples": 0, "accuracy_claim_allowed": False}
    settings = get_settings()
    segmenter = create_segmenter(
        settings.segmentation_backend,
        settings.segmentation_checkpoint,
        settings.segmentation_model_config,
    )
    root = manifest_path.parent
    results = []
    categories: dict[str, int] = {}
    for record in records:
        image_path = (root / record["image"]).resolve()
        mask_path = (root / record["mask"]).resolve()
        image = normalize_image(image_path.read_bytes(), settings.inference_max_dimension)
        expected = (
            np.asarray(
                Image.open(mask_path).convert("L").resize(image.size, Image.Resampling.NEAREST)
            )
            > 127
        )
        output = segmenter.segment(image)
        iou = intersection_over_union(output.mask, expected)
        results.append(iou)
        categories[record["category"]] = categories.get(record["category"], 0) + 1
    return {
        "labelled_samples": len(results),
        "mean_mask_iou": sum(results) / len(results),
        "accepted_without_correction_rate": sum(value >= 0.85 for value in results) / len(results),
        "category_counts": categories,
        "model": settings.segmentation_backend,
        "accuracy_claim_allowed": len(results) >= 30 and len(categories) >= 4,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.manifest), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
