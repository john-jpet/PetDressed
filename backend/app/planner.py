from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

SOLVER_VERSION = "weekly-cpsat-1"


@dataclass(frozen=True)
class PlanningGarment:
    id: str
    category: str
    utility_by_day: tuple[int, ...]
    reuse_window_days: int = 1


@dataclass(frozen=True)
class PlanRequest:
    days: tuple[date, ...]
    garments: tuple[PlanningGarment, ...]
    pair_scores: dict[tuple[str, str], int] = field(default_factory=dict)
    locked_items: frozenset[tuple[int, str]] = frozenset()
    excluded_items: frozenset[tuple[int, str]] = frozenset()
    weather_required_by_day: dict[int, frozenset[str]] = field(default_factory=dict)
    required_category_by_day: dict[int, str] = field(default_factory=dict)
    max_accessories: int = 1
    max_solve_seconds: float = 5.0


@dataclass(frozen=True)
class PlannedDay:
    date: date
    garment_ids: tuple[str, ...]
    utility_score: int
    compatibility_score: int
    total_score: int


@dataclass(frozen=True)
class PlanSolution:
    status: str
    days: tuple[PlannedDay, ...]
    relaxed_constraints: tuple[str, ...]
    solve_time_ms: int
    objective_value: int | None


class LockedConflict(ValueError):
    pass


def validate_locked_items(request: PlanRequest) -> None:
    by_day: dict[int, list[PlanningGarment]] = {}
    garments = {garment.id: garment for garment in request.garments}
    for day_index, garment_id in request.locked_items:
        garment = garments.get(garment_id)
        if garment is None:
            raise LockedConflict(f"Locked garment {garment_id} is not eligible")
        by_day.setdefault(day_index, []).append(garment)
    for day_index, locked in by_day.items():
        categories = [garment.category for garment in locked]
        if "one_piece" in categories and ("top" in categories or "bottom" in categories):
            raise LockedConflict(f"Day {day_index} locks a one-piece with a top or bottom")
        for category in ("top", "bottom", "one_piece", "shoes", "outerwear"):
            if categories.count(category) > 1:
                raise LockedConflict(f"Day {day_index} locks multiple {category} garments")
        if any((day_index, garment.id) in request.excluded_items for garment in locked):
            raise LockedConflict(f"Day {day_index} both locks and excludes a garment")


def _build_and_solve(
    request: PlanRequest, enforce_rotation: bool, enforce_weather: bool = True
) -> PlanSolution:
    validate_locked_items(request)
    model = cp_model.CpModel()
    garments_by_category: dict[str, list[PlanningGarment]] = {}
    for garment in request.garments:
        garments_by_category.setdefault(garment.category, []).append(garment)
    if not garments_by_category.get("shoes") or not (
        garments_by_category.get("one_piece")
        or (garments_by_category.get("top") and garments_by_category.get("bottom"))
    ):
        return PlanSolution("infeasible", (), (), 0, None)

    x: dict[tuple[int, str], cp_model.IntVar] = {}
    for day_index in range(len(request.days)):
        for garment in request.garments:
            x[day_index, garment.id] = model.new_bool_var(f"x_{day_index}_{garment.id}")
    mode = {
        day_index: model.new_bool_var(f"one_piece_{day_index}")
        for day_index in range(len(request.days))
    }
    for day_index in range(len(request.days)):
        model.add(
            sum(x[day_index, item.id] for item in garments_by_category.get("one_piece", []))
            == mode[day_index]
        )
        model.add(
            sum(x[day_index, item.id] for item in garments_by_category.get("top", []))
            == 1 - mode[day_index]
        )
        model.add(
            sum(x[day_index, item.id] for item in garments_by_category.get("bottom", []))
            == 1 - mode[day_index]
        )
        model.add(sum(x[day_index, item.id] for item in garments_by_category.get("shoes", [])) == 1)
        model.add(
            sum(x[day_index, item.id] for item in garments_by_category.get("outerwear", [])) <= 1
        )
        model.add(
            sum(x[day_index, item.id] for item in garments_by_category.get("accessory", []))
            <= request.max_accessories
        )
    for day_index, garment_id in request.locked_items:
        model.add(x[day_index, garment_id] == 1)
    for day_index, garment_id in request.excluded_items:
        if (day_index, garment_id) in x:
            model.add(x[day_index, garment_id] == 0)
    if enforce_weather:
        for day_index, garment_ids in request.weather_required_by_day.items():
            model.add(sum(x[day_index, garment_id] for garment_id in garment_ids) >= 1)
    for day_index, category in request.required_category_by_day.items():
        model.add(
            sum(x[day_index, garment.id] for garment in garments_by_category.get(category, [])) == 1
        )
    if enforce_rotation:
        for garment in request.garments:
            window = garment.reuse_window_days
            if window <= 1:
                continue
            for start in range(len(request.days) - window + 1):
                model.add(sum(x[start + offset, garment.id] for offset in range(window)) <= 1)

    utility_terms = []
    for day_index in range(len(request.days)):
        for garment in request.garments:
            utility_terms.append(garment.utility_by_day[day_index] * x[day_index, garment.id])
    pair_vars: dict[tuple[int, str, str], cp_model.IntVar] = {}
    pair_terms = []
    for day_index in range(len(request.days)):
        for (left, right), score in request.pair_scores.items():
            if (day_index, left) not in x or (day_index, right) not in x:
                continue
            pair = model.new_bool_var(f"pair_{day_index}_{left}_{right}")
            pair_vars[day_index, left, right] = pair
            model.add(pair <= x[day_index, left])
            model.add(pair <= x[day_index, right])
            model.add(pair >= x[day_index, left] + x[day_index, right] - 1)
            pair_terms.append(score * pair)
    model.maximize(sum(utility_terms) + sum(pair_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = request.max_solve_seconds
    solver.parameters.random_seed = 42
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    status_name = solver.status_name(status).lower()
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PlanSolution("infeasible", (), (), round(solver.wall_time * 1000), None)
    planned_days = []
    for day_index, plan_date in enumerate(request.days):
        selected = tuple(
            garment.id for garment in request.garments if solver.value(x[day_index, garment.id])
        )
        utility = sum(
            garment.utility_by_day[day_index]
            for garment in request.garments
            if garment.id in selected
        )
        compatibility = sum(
            score
            for (left, right), score in request.pair_scores.items()
            if left in selected and right in selected
        )
        planned_days.append(
            PlannedDay(plan_date, selected, utility, compatibility, utility + compatibility)
        )
    return PlanSolution(
        status_name,
        tuple(planned_days),
        (),
        round(solver.wall_time * 1000),
        round(solver.objective_value),
    )


def solve_plan(request: PlanRequest) -> PlanSolution:
    solution = _build_and_solve(request, enforce_rotation=True)
    if solution.status != "infeasible":
        return solution
    relaxed = _build_and_solve(request, enforce_rotation=False)
    if relaxed.status != "infeasible":
        return PlanSolution(
            relaxed.status,
            relaxed.days,
            ("rotation",),
            relaxed.solve_time_ms,
            relaxed.objective_value,
        )
    weather_relaxed = _build_and_solve(request, enforce_rotation=False, enforce_weather=False)
    if weather_relaxed.status == "infeasible":
        return weather_relaxed
    return PlanSolution(
        weather_relaxed.status,
        weather_relaxed.days,
        ("rotation", "weather_protection"),
        weather_relaxed.solve_time_ms,
        weather_relaxed.objective_value,
    )


def category_reuse_window(category: str) -> int:
    return {"top": 3, "bottom": 2, "one_piece": 3}.get(category, 1)


def meaningful_pairs(garments: Iterable[dict]) -> Iterable[tuple[dict, dict]]:
    relationships = {
        ("top", "bottom"),
        ("top", "outerwear"),
        ("one_piece", "outerwear"),
        ("top", "shoes"),
        ("bottom", "shoes"),
        ("one_piece", "shoes"),
        ("top", "accessory"),
        ("bottom", "accessory"),
        ("one_piece", "accessory"),
        ("outerwear", "accessory"),
    }
    items = list(garments)
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if (left["category"], right["category"]) in relationships or (
                right["category"],
                left["category"],
            ) in relationships:
                yield left, right
