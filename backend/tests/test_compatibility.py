from app.compatibility import (
    color_compatibility,
    formality_compatibility,
    pattern_compatibility,
    score_pair,
)


def test_neutral_color_is_broadly_compatible():
    assert color_compatibility("#222222", "#D94545") >= 80


def test_complementary_colors_score_higher_than_clashing_colors():
    assert color_compatibility("#E53935", "#35DDE5") > color_compatibility("#E53935", "#B57B22")


def test_formality_score_is_clamped():
    assert formality_compatibility(0, 5) == 0
    assert formality_compatibility(3, 3) == 100


def test_patterned_plus_solid_is_preferred():
    assert pattern_compatibility("floral", "solid") > pattern_compatibility("floral", "checked")


def test_pair_breakdown_remains_explainable():
    left = {"color": "#1D3557", "formality": 3, "pattern": "solid"}
    right = {"color": "#E8E0D5", "formality": 2, "pattern": "checked"}
    score = score_pair(left, right, preference=5)
    assert score.total == score.color + score.formality + score.pattern + score.preference
