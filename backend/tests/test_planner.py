from datetime import date, timedelta

import pytest

from app.planner import LockedConflict, PlanningGarment, PlanRequest, meaningful_pairs, solve_plan


def days(count=7):
    start = date(2026, 7, 27)
    return tuple(start + timedelta(days=offset) for offset in range(count))


def garment(identifier, category, count=7, score=100, reuse=1):
    return PlanningGarment(identifier, category, (score,) * count, reuse)


def test_minimum_wardrobe_relaxes_rotation_for_week():
    request = PlanRequest(
        days=days(),
        garments=(
            garment("top", "top", reuse=3),
            garment("bottom", "bottom", reuse=2),
            garment("shoes", "shoes"),
        ),
    )
    result = solve_plan(request)
    assert result.status in {"optimal", "feasible"}
    assert result.relaxed_constraints == ("rotation",)
    assert all(len(day.garment_ids) == 3 for day in result.days)


def test_one_piece_replaces_top_and_bottom():
    request = PlanRequest(
        days=days(1),
        garments=(
            garment("top", "top", 1, 10),
            garment("bottom", "bottom", 1, 10),
            garment("dress", "one_piece", 1, 100),
            garment("shoes", "shoes", 1),
        ),
    )
    result = solve_plan(request)
    assert set(result.days[0].garment_ids) == {"dress", "shoes"}


def test_locked_one_piece_and_top_conflict_is_rejected_before_solve():
    request = PlanRequest(
        days=days(1),
        garments=(
            garment("top", "top", 1),
            garment("bottom", "bottom", 1),
            garment("dress", "one_piece", 1),
            garment("shoes", "shoes", 1),
        ),
        locked_items=frozenset({(0, "top"), (0, "dress")}),
    )
    with pytest.raises(LockedConflict):
        solve_plan(request)


def test_pair_score_changes_selected_outfit():
    request = PlanRequest(
        days=days(1),
        garments=(
            garment("top-a", "top", 1),
            garment("top-b", "top", 1),
            garment("bottom", "bottom", 1),
            garment("shoes", "shoes", 1),
        ),
        pair_scores={("top-b", "bottom"): 1000},
    )
    assert "top-b" in solve_plan(request).days[0].garment_ids


def test_missing_shoes_is_explicitly_infeasible():
    result = solve_plan(
        PlanRequest(
            days=days(1),
            garments=(garment("top", "top", 1), garment("bottom", "bottom", 1)),
        )
    )
    assert result.status == "infeasible"
    assert result.days == ()


def test_unavailable_hard_weather_protection_is_explicitly_relaxed():
    request = PlanRequest(
        days=days(1),
        garments=(
            garment("top", "top", 1),
            garment("bottom", "bottom", 1),
            garment("shoes", "shoes", 1),
        ),
        weather_required_by_day={0: frozenset()},
    )
    result = solve_plan(request)
    assert "weather_protection" in result.relaxed_constraints


def test_replacement_can_force_optional_category():
    request = PlanRequest(
        days=days(1),
        garments=(
            garment("top", "top", 1),
            garment("bottom", "bottom", 1),
            garment("shoes", "shoes", 1),
            garment("jacket", "outerwear", 1),
        ),
        required_category_by_day={0: "outerwear"},
    )
    assert "jacket" in solve_plan(request).days[0].garment_ids


def test_accessories_are_scored_only_against_meaningful_garment_categories():
    items = [
        {"id": "top", "category": "top"},
        {"id": "belt", "category": "accessory"},
        {"id": "shoes", "category": "shoes"},
    ]
    pairs = {(left["id"], right["id"]) for left, right in meaningful_pairs(items)}
    assert ("top", "belt") in pairs
    assert ("belt", "shoes") not in pairs
