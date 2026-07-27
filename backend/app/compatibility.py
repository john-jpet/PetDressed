from __future__ import annotations

import colorsys
from dataclasses import dataclass

NEUTRAL_SATURATION = 0.16
SCORING_VERSION = "compatibility-heuristic-1"


@dataclass(frozen=True)
class CompatibilityBreakdown:
    color: int
    formality: int
    pattern: int
    preference: int

    @property
    def total(self) -> int:
        return self.color + self.formality + self.pattern + self.preference


def hex_to_hls(value: str) -> tuple[float, float, float]:
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
    return colorsys.rgb_to_hls(red, green, blue)


def color_compatibility(left: str, right: str) -> int:
    left_hue, left_lightness, left_saturation = hex_to_hls(left)
    right_hue, right_lightness, right_saturation = hex_to_hls(right)
    lightness_contrast = abs(left_lightness - right_lightness)
    if left_saturation < NEUTRAL_SATURATION and right_saturation < NEUTRAL_SATURATION:
        return min(100, 78 + round(lightness_contrast * 22))
    if left_saturation < NEUTRAL_SATURATION or right_saturation < NEUTRAL_SATURATION:
        return min(100, 84 + round(lightness_contrast * 14))
    hue_distance = abs(left_hue - right_hue)
    hue_distance = min(hue_distance, 1 - hue_distance)
    analogous = hue_distance <= 1 / 12
    complementary = abs(hue_distance - 0.5) <= 1 / 12
    if analogous:
        return 88
    if complementary:
        return 92
    if 0.18 <= hue_distance <= 0.33:
        return 72
    return 48


def formality_compatibility(left: int, right: int) -> int:
    return max(0, 100 - 20 * abs(left - right))


def pattern_compatibility(left: str, right: str) -> int:
    left_solid = left == "solid"
    right_solid = right == "solid"
    if left_solid and right_solid:
        return 72
    if left_solid != right_solid:
        return 92
    if left == "unknown" or right == "unknown":
        return 60
    return 35


def score_pair(
    left: dict,
    right: dict,
    preference: int = 0,
    weights: tuple[int, int, int, int] = (4, 3, 2, 1),
) -> CompatibilityBreakdown:
    color = color_compatibility(left["color"], right["color"])
    formality = formality_compatibility(left["formality"], right["formality"])
    pattern = pattern_compatibility(left["pattern"], right["pattern"])
    color_weight, formality_weight, pattern_weight, preference_weight = weights
    return CompatibilityBreakdown(
        color=color * color_weight,
        formality=formality * formality_weight,
        pattern=pattern * pattern_weight,
        preference=preference * preference_weight,
    )
