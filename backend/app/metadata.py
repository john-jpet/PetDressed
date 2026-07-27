from __future__ import annotations

import colorsys
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class PaletteColor:
    hex_value: str
    lab: tuple[float, float, float]
    proportion: float


@dataclass(frozen=True)
class AttributePrediction:
    value: str
    confidence: float
    alternatives: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class MetadataOutput:
    embedding: list[float]
    category: AttributePrediction
    subcategory: AttributePrediction
    formality: int
    warmth: int
    breathability: int
    water_resistance: int
    pattern: str
    colors: list[PaletteColor]
    model_name: str
    model_version: str


class MetadataExtractor(Protocol):
    def extract(self, image: Image.Image, filename: str = "") -> MetadataOutput: ...


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    values = rgb.astype(np.float64) / 255.0
    values = np.where(values > 0.04045, ((values + 0.055) / 1.055) ** 2.4, values / 12.92)
    xyz = values @ np.array(
        [
            [0.4124564, 0.2126729, 0.0193339],
            [0.3575761, 0.7151522, 0.1191920],
            [0.1804375, 0.0721750, 0.9503041],
        ]
    )
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])],
        axis=1,
    )


def extract_palette(image: Image.Image, k: int = 4) -> list[PaletteColor]:
    rgba = np.asarray(image.convert("RGBA"))
    pixels = rgba[..., :3][rgba[..., 3] > 16]
    if not len(pixels):
        return []
    stride = max(1, len(pixels) // 12_000)
    pixels = pixels[::stride]
    lab = rgb_to_lab(pixels)
    unique_count = len(np.unique(pixels, axis=0))
    cluster_count = max(1, min(k, unique_count))
    indices = np.linspace(0, len(lab) - 1, cluster_count, dtype=int)
    centers = lab[indices].copy()
    labels = np.zeros(len(lab), dtype=int)
    for _ in range(18):
        distances = np.linalg.norm(lab[:, None, :] - centers[None, :, :], axis=2)
        next_labels = distances.argmin(axis=1)
        next_centers = np.array(
            [
                lab[next_labels == index].mean(axis=0)
                if np.any(next_labels == index)
                else centers[index]
                for index in range(cluster_count)
            ]
        )
        if np.array_equal(labels, next_labels):
            break
        labels, centers = next_labels, next_centers
    colors = []
    for index in range(cluster_count):
        members = pixels[labels == index]
        if not len(members):
            continue
        rgb = np.rint(np.median(members, axis=0)).astype(int)
        proportion = float(len(members) / len(pixels))
        colors.append(
            PaletteColor(
                hex_value=f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}",
                lab=tuple(float(value) for value in centers[index]),
                proportion=proportion,
            )
        )
    return sorted(colors, key=lambda color: color.proportion, reverse=True)


def visual_embedding(image: Image.Image) -> list[float]:
    """Stable local 512-D visual descriptor used when Fashion-CLIP is unavailable."""
    rgba = image.convert("RGBA").resize((32, 32), Image.Resampling.BILINEAR)
    data = np.asarray(rgba, dtype=np.float32)
    visible = data[..., 3] > 16
    rgb = data[..., :3] / 255.0
    features: list[float] = []
    for channel in range(3):
        hist, _ = np.histogram(rgb[..., channel][visible], bins=48, range=(0, 1), density=True)
        features.extend(hist.tolist())
    grayscale = rgb.mean(axis=2)
    for axis in (0, 1):
        gradient = np.abs(np.diff(grayscale, axis=axis))
        hist, _ = np.histogram(
            gradient[visible[:-1, :] if axis == 0 else visible[:, :-1]],
            bins=32,
            range=(0, 1),
            density=True,
        )
        features.extend(hist.tolist())
    silhouette = visible.astype(np.float32).reshape(16, 2, 16, 2).mean(axis=(1, 3)).reshape(-1)
    vector = np.asarray((features + silhouette.tolist())[:512], dtype=np.float32)
    if len(vector) < 512:
        vector = np.pad(vector, (0, 512 - len(vector)))
    norm = float(np.linalg.norm(vector))
    return (vector / norm if norm else vector).tolist()


def infer_baseline_metadata(image: Image.Image, filename: str = "") -> MetadataOutput:
    """Deterministic test/degraded backend. It deliberately makes no semantic claim."""
    lower = filename.lower()
    keyword_categories = {
        "shoe": ("shoes", "sneakers"),
        "boot": ("shoes", "boots"),
        "dress": ("one_piece", "dress"),
        "jacket": ("outerwear", "light jacket"),
        "coat": ("outerwear", "coat"),
        "pant": ("bottom", "trousers"),
        "jean": ("bottom", "jeans"),
        "skirt": ("bottom", "skirt"),
        "shirt": ("top", "shirt"),
        "sweater": ("top", "sweater"),
    }
    category, subcategory = ("top", "")
    confidence = 0.0
    for keyword, values in keyword_categories.items():
        if keyword in lower:
            category, subcategory = values
            confidence = 0.64
            break
    palette = extract_palette(image)
    dominant = palette[0].hex_value if palette else "#808080"
    red, green, blue = (int(dominant[index : index + 2], 16) / 255 for index in (1, 3, 5))
    _, saturation, _lightness = colorsys.rgb_to_hls(red, green, blue)
    seed = hashlib.sha256((filename + dominant).encode()).digest()
    pattern = "solid" if len(palette) <= 2 or palette[0].proportion > 0.72 else "unknown"
    return MetadataOutput(
        embedding=visual_embedding(image),
        category=AttributePrediction(
            category,
            confidence,
            tuple(
                (candidate, score)
                for candidate, score in [("bottom", 0.2), ("outerwear", 0.15)]
                if candidate != category
            ),
        ),
        subcategory=AttributePrediction(subcategory, confidence * 0.9, ()),
        formality=2 if saturation < 0.75 else 1,
        warmth=2 + seed[0] % 2,
        breathability=3,
        water_resistance=1,
        pattern=pattern,
        colors=palette,
        model_name="deterministic-test-fallback",
        model_version="2",
    )


CATEGORY_PROMPTS = {
    "top": "a photo of an upper-body garment, shirt, blouse, sweater, or top",
    "bottom": "a photo of trousers, pants, jeans, shorts, or a skirt",
    "one_piece": "a photo of a dress, jumpsuit, or one-piece garment",
    "outerwear": "a photo of a coat, jacket, blazer, or outerwear garment",
    "shoes": "a photo of footwear, shoes, boots, sandals, or sneakers",
    "accessory": "a photo of a clothing accessory, belt, scarf, hat, tie, or bag",
}
SUBCATEGORY_PROMPTS = {
    "top": {
        "t-shirt": "a short-sleeve or long-sleeve collarless T-shirt",
        "button-up shirt": "a collared button-up or button-down shirt",
        "polo": "a collared polo shirt with a short button placket",
        "blouse": "a blouse",
        "sweater": "a knitted sweater or pullover",
        "hoodie": "a hooded sweatshirt",
        "sweatshirt": "a crew-neck sweatshirt",
        "tank top": "a sleeveless tank top",
    },
    "bottom": {
        "trousers": "tailored trousers or pants",
        "jeans": "denim jeans",
        "shorts": "shorts",
        "skirt": "a skirt",
        "leggings": "leggings",
    },
    "one_piece": {
        "dress": "a dress",
        "jumpsuit": "a jumpsuit or romper",
    },
    "outerwear": {
        "coat": "a coat",
        "jacket": "a jacket",
        "blazer": "a blazer or sport coat",
        "cardigan": "an open-front cardigan",
    },
    "shoes": {
        "sneakers": "sneakers or athletic shoes",
        "boots": "boots",
        "dress shoes": "formal dress shoes",
        "sandals": "sandals",
        "heels": "high-heeled shoes",
    },
    "accessory": {
        "belt": "a belt",
        "scarf": "a scarf",
        "hat": "a hat or cap",
        "tie": "a necktie or bow tie",
        "bag": "a handbag or bag",
    },
}


class FashionClipMetadataExtractor:
    def __init__(self, model_name: str, device: str = "cpu", cache_dir: str | None = None):
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Fashion-CLIP dependencies are not installed; install the cv dependency group"
            ) from exc
        self._torch = torch
        self._device = device
        self._model_name = model_name
        self._processor = CLIPProcessor.from_pretrained(model_name, cache_dir=cache_dir)
        self._model = CLIPModel.from_pretrained(model_name, cache_dir=cache_dir).to(device)
        self._model.eval()

    def _classify(
        self, image: Image.Image, prompts: dict[str, str]
    ) -> tuple[str, float, tuple[tuple[str, float], ...]]:
        labels = list(prompts)
        inputs = self._processor(
            text=[prompts[label] for label in labels],
            images=image.convert("RGB"),
            return_tensors="pt",
            padding=True,
        )
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with self._torch.inference_mode():
            probabilities = self._model(**inputs).logits_per_image.softmax(dim=1)[0].cpu()
        ranked = sorted(
            zip(labels, (float(value) for value in probabilities), strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked[0][0], ranked[0][1], tuple(ranked[1:4])

    def garment_candidate_score(self, image: Image.Image) -> float:
        prompts = {
            "garment": "a catalog photo showing one complete clothing garment",
            "person": "a photograph of a person or human body wearing clothes",
            "detail": "a close-up of a button, collar, fabric detail, or small object",
            "background": "empty background without a clothing item",
        }
        label, score, alternatives = self._classify(image, prompts)
        probabilities = {label: score, **dict(alternatives)}
        return probabilities.get("garment", 0.0) - probabilities.get("person", 0.0)

    def extract(self, image: Image.Image, filename: str = "") -> MetadataOutput:
        category, category_score, alternatives = self._classify(image, CATEGORY_PROMPTS)
        subtype, subtype_score, subtype_alternatives = self._classify(
            image, SUBCATEGORY_PROMPTS[category]
        )
        image_inputs = self._processor(images=image.convert("RGB"), return_tensors="pt")
        image_inputs = {key: value.to(self._device) for key, value in image_inputs.items()}
        with self._torch.inference_mode():
            feature_output = self._model.get_image_features(**image_inputs)
            features = (
                feature_output.pooler_output
                if hasattr(feature_output, "pooler_output")
                else feature_output
            )
            features = features / features.norm(dim=-1, keepdim=True)
        embedding = features[0].float().cpu().tolist()
        if len(embedding) != 512:
            raise ValueError(f"Fashion-CLIP returned {len(embedding)} dimensions; expected 512")
        palette = extract_palette(image)
        dominant = palette[0].hex_value if palette else "#808080"
        red, green, blue = (int(dominant[index : index + 2], 16) / 255 for index in (1, 3, 5))
        _, saturation, _lightness = colorsys.rgb_to_hls(red, green, blue)
        return MetadataOutput(
            embedding=embedding,
            category=AttributePrediction(category, category_score, alternatives),
            subcategory=AttributePrediction(subtype, subtype_score, subtype_alternatives),
            formality=2 if saturation < 0.75 else 1,
            warmth=2,
            breathability=3,
            water_resistance=1,
            pattern="solid" if len(palette) <= 2 or palette[0].proportion > 0.72 else "unknown",
            colors=palette,
            model_name="fashion-clip",
            model_version=self._model_name,
        )


@lru_cache(maxsize=2)
def create_metadata_extractor(
    backend: str,
    model_name: str = "patrickjohncyh/fashion-clip",
    device: str = "cpu",
    cache_dir: str | None = None,
) -> MetadataExtractor:
    if backend == "fashion_clip":
        return FashionClipMetadataExtractor(model_name, device, cache_dir)
    if backend == "deterministic":
        return _DeterministicMetadataExtractor()
    raise RuntimeError(f"Unsupported metadata backend: {backend}")


class _DeterministicMetadataExtractor:
    def extract(self, image: Image.Image, filename: str = "") -> MetadataOutput:
        return infer_baseline_metadata(image, filename)
