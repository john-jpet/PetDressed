from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


@dataclass(frozen=True)
class Prompt:
    positive_points: tuple[tuple[int, int], ...] = ()
    negative_points: tuple[tuple[int, int], ...] = ()
    bbox: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class SegmentationOutput:
    mask: np.ndarray
    confidence: float
    model_name: str
    model_version: str


@dataclass(frozen=True)
class Artifacts:
    processed_png: bytes
    preview_png: bytes
    mask_png: bytes
    bbox: tuple[int, int, int, int]
    mask_area_ratio: float


class Segmenter(Protocol):
    def segment(self, image: Image.Image, prompt: Prompt | None = None) -> SegmentationOutput: ...


def normalize_image(data: bytes, max_dimension: int) -> Image.Image:
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return image


class CpuForegroundSegmenter:
    """Deterministic local baseline for clean, contrasting capture backgrounds."""

    def segment(self, image: Image.Image, prompt: Prompt | None = None) -> SegmentationOutput:
        pixels = np.asarray(image, dtype=np.float32)
        height, width, _ = pixels.shape
        patch = max(2, min(width, height) // 20)
        corners = np.concatenate(
            [
                pixels[:patch, :patch].reshape(-1, 3),
                pixels[:patch, -patch:].reshape(-1, 3),
                pixels[-patch:, :patch].reshape(-1, 3),
                pixels[-patch:, -patch:].reshape(-1, 3),
            ]
        )
        background = np.median(corners, axis=0)
        distance = np.linalg.norm(pixels - background, axis=2)
        threshold = max(24.0, float(np.percentile(distance, 68)) * 0.55)
        mask = distance > threshold

        if prompt and prompt.bbox:
            x0, y0, x1, y1 = prompt.bbox
            box_mask = np.zeros_like(mask)
            box_mask[max(0, y0) : min(height, y1), max(0, x0) : min(width, x1)] = True
            mask &= box_mask

        pil_mask = Image.fromarray((mask * 255).astype(np.uint8))
        pil_mask = pil_mask.filter(ImageFilter.MedianFilter(5))
        drawing = ImageDraw.Draw(pil_mask)
        radius = max(8, min(width, height) // 30)
        if prompt:
            for x, y in prompt.positive_points:
                drawing.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
            for x, y in prompt.negative_points:
                drawing.ellipse((x - radius, y - radius, x + radius, y + radius), fill=0)
        mask = np.asarray(pil_mask) > 127
        area = float(mask.mean())
        edge_pixels = np.concatenate((mask[0], mask[-1], mask[:, 0], mask[:, -1]))
        edge_ratio = float(edge_pixels.mean())
        confidence = max(0.15, min(0.82, 0.88 - abs(area - 0.42) - edge_ratio * 0.4))
        return SegmentationOutput(mask, confidence, "cpu-foreground", "1")


class Sam2Segmenter:
    def __init__(self, checkpoint: str, model_config: str, device: str = "cpu"):
        try:
            import torch
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as exc:
            raise RuntimeError(
                "SAM 2 dependencies are not installed; use the cpu backend or CUDA image"
            ) from exc
        if not Path(checkpoint).is_file():
            raise RuntimeError(f"SAM 2 checkpoint does not exist: {checkpoint}")
        self._torch = torch
        self._predictor = SAM2ImagePredictor(build_sam2(model_config, checkpoint, device=device))

    def segment(self, image: Image.Image, prompt: Prompt | None = None) -> SegmentationOutput:
        prompt = prompt or Prompt()
        self._predictor.set_image(np.asarray(image))
        points = list(prompt.positive_points) + list(prompt.negative_points)
        labels = [1] * len(prompt.positive_points) + [0] * len(prompt.negative_points)
        kwargs = {}
        if points:
            kwargs["point_coords"] = np.asarray(points)
            kwargs["point_labels"] = np.asarray(labels)
        if prompt.bbox:
            kwargs["box"] = np.asarray(prompt.bbox)
        masks, scores, _ = self._predictor.predict(multimask_output=True, **kwargs)
        index = int(np.argmax(scores))
        return SegmentationOutput(
            masks[index].astype(bool), float(scores[index]), "sam2", "hiera-small-1"
        )


class TransformersSam2Segmenter:
    """SAM 2.1 image segmentation using official Hugging Face model weights."""

    def __init__(
        self,
        model_name: str = "facebook/sam2.1-hiera-tiny",
        device: str = "cpu",
        cache_dir: str | None = None,
        metadata_model_name: str = "patrickjohncyh/fashion-clip",
    ):
        try:
            import torch
            from transformers import Sam2Model, Sam2Processor
        except ImportError as exc:
            raise RuntimeError(
                "SAM 2 dependencies are not installed; install the cv dependency group"
            ) from exc
        self._torch = torch
        self._device = device
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._metadata_model_name = metadata_model_name
        self._processor = Sam2Processor.from_pretrained(model_name, cache_dir=cache_dir)
        self._model = Sam2Model.from_pretrained(model_name, cache_dir=cache_dir).to(device)
        self._model.eval()

    def segment(self, image: Image.Image, prompt: Prompt | None = None) -> SegmentationOutput:
        prompt = prompt or Prompt()
        kwargs: dict = {}
        points = list(prompt.positive_points) + list(prompt.negative_points)
        if points:
            kwargs["input_points"] = [[points]]
            kwargs["input_labels"] = [
                [([1] * len(prompt.positive_points)) + ([0] * len(prompt.negative_points))]
            ]
        elif prompt.bbox:
            kwargs["input_boxes"] = [[list(prompt.bbox)]]
        else:
            # Product and on-person garment photos normally place the intended piece
            # around the upper-center. The review UI can refine this prompt.
            kwargs["input_points"] = [[[[image.width * 0.5, image.height * 0.42]]]]
            kwargs["input_labels"] = [[[1]]]
        inputs = self._processor(images=image.convert("RGB"), return_tensors="pt", **kwargs)
        device_inputs = {
            key: value.to(self._device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
        with self._torch.inference_mode():
            outputs = self._model(**device_inputs, multimask_output=True)
        masks = self._processor.post_process_masks(
            outputs.pred_masks.cpu(), inputs["original_sizes"]
        )[0][0]
        scores = outputs.iou_scores[0, 0].detach().cpu()
        index = self._select_garment_candidate(image, masks, scores)
        return SegmentationOutput(
            masks[index].numpy().astype(bool),
            float(scores[index]),
            "sam2.1",
            self._model_name,
        )

    def _select_garment_candidate(self, image, masks, scores) -> int:
        from .metadata import create_metadata_extractor

        ranker = create_metadata_extractor(
            "fashion_clip",
            self._metadata_model_name,
            self._device,
            self._cache_dir,
        )
        ranked: list[tuple[float, int]] = []
        for index, candidate in enumerate(masks):
            mask = candidate.numpy().astype(bool)
            area = float(mask.mean())
            if area < 0.01 or area > 0.85:
                continue
            ys, xs = np.where(mask)
            rgba = image.convert("RGBA")
            rgba.putalpha(Image.fromarray((mask * 255).astype(np.uint8)))
            crop = rgba.crop((int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)))
            background = Image.new("RGB", crop.size, "white")
            background.paste(crop, mask=crop.getchannel("A"))
            semantic = ranker.garment_candidate_score(background)
            coverage = min(area, 0.45) / 0.45
            combined = semantic * 2.0 + coverage * 0.35 + float(scores[index]) * 0.1
            ranked.append((combined, index))
        if not ranked:
            return int(scores.argmax())
        return max(ranked)[1]


@lru_cache(maxsize=2)
def create_segmenter(
    backend: str,
    checkpoint: str | None,
    model_config: str,
    device: str = "cpu",
    cache_dir: str | None = None,
    metadata_model_name: str = "patrickjohncyh/fashion-clip",
) -> Segmenter:
    if backend == "sam2_transformers":
        return TransformersSam2Segmenter(
            model_config, device, cache_dir, metadata_model_name
        )
    if backend == "sam2":
        if not checkpoint:
            raise RuntimeError("SEGMENTATION_CHECKPOINT is required for the SAM 2 backend")
        return Sam2Segmenter(checkpoint, model_config, device)
    if backend == "deterministic":
        return CpuForegroundSegmenter()
    raise RuntimeError(f"Unsupported segmentation backend: {backend}")


def apply_mask_runs(mask: np.ndarray, runs: list[tuple[int, int, int]]) -> np.ndarray:
    flat = mask.reshape(-1).copy()
    for start, length, value in runs:
        if start >= flat.size or start + length > flat.size:
            raise ValueError("Mask correction run is outside image bounds")
        flat[start : start + length] = bool(value)
    return flat.reshape(mask.shape)


def render_artifacts(image: Image.Image, mask: np.ndarray) -> Artifacts:
    if mask.shape != (image.height, image.width):
        raise ValueError("Mask dimensions do not match image")
    ys, xs = np.where(mask)
    if not len(xs):
        raise ValueError("No garment foreground was detected")
    x0, x1, y0, y1 = int(xs.min()), int(xs.max() + 1), int(ys.min()), int(ys.max() + 1)
    padding = max(8, round(max(x1 - x0, y1 - y0) * 0.03))
    bbox = (
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(image.width, x1 + padding),
        min(image.height, y1 + padding),
    )
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.fromarray((mask * 255).astype(np.uint8)))
    processed = rgba.crop(bbox)

    overlay = image.convert("RGBA")
    tint = Image.new("RGBA", image.size, (232, 137, 104, 0))
    tint.putalpha(Image.fromarray((mask * 92).astype(np.uint8)))
    preview = Image.alpha_composite(overlay, tint)

    def png_bytes(value: Image.Image) -> bytes:
        buffer = BytesIO()
        value.save(buffer, "PNG", optimize=True)
        return buffer.getvalue()

    return Artifacts(
        processed_png=png_bytes(processed),
        preview_png=png_bytes(preview),
        mask_png=png_bytes(Image.fromarray((mask * 255).astype(np.uint8))),
        bbox=bbox,
        mask_area_ratio=float(mask.mean()),
    )
