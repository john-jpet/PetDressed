from __future__ import annotations

import json
import uuid
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import AuthenticatedUser, get_current_user
from .compatibility import SCORING_VERSION, score_pair
from .config import Settings, get_settings
from .db import get_db
from .models import (
    Availability,
    Garment,
    GarmentCategory,
    GarmentColor,
    OutfitFeedback,
    OutfitPlan,
    OutfitPlanDay,
    OutfitPlanGarment,
    ProcessingStatus,
    UserSettings,
)
from .planner import (
    SOLVER_VERSION,
    LockedConflict,
    PlanningGarment,
    PlanRequest,
    category_reuse_window,
    meaningful_pairs,
    solve_plan,
)
from .schemas import (
    FeedbackRequest,
    LocationRequest,
    PlanGarmentResponse,
    PlanGenerateRequest,
    PlanItemConstraint,
    PlannedDayResponse,
    PlanResponse,
    RegenerateDayRequest,
    ReplaceGarmentRequest,
    ScoreBreakdownResponse,
)
from .storage import public_client
from .weather import DailyWeather, OpenMeteoProvider, weather_suitability

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])
CANDIDATE_LIMITS = {
    GarmentCategory.top: 20,
    GarmentCategory.bottom: 20,
    GarmentCategory.one_piece: 15,
    GarmentCategory.outerwear: 10,
    GarmentCategory.shoes: 12,
    GarmentCategory.accessory: 10,
}
WEATHER_CACHE_TTL_SECONDS = 6 * 60 * 60


def weather_cache_key(payload: PlanGenerateRequest) -> str:
    location = payload.location
    return (
        f"weather:{round(location.latitude, 2)}:{round(location.longitude, 2)}:"
        f"{payload.start_date.isoformat()}:{payload.days}:{location.timezone}"
    )


def cache_weather(settings: Settings, payload: PlanGenerateRequest, weather: list[DailyWeather]) -> None:
    try:
        Redis.from_url(settings.redis_url).setex(
            weather_cache_key(payload),
            WEATHER_CACHE_TTL_SECONDS,
            json.dumps([weather_json(item) for item in weather]),
        )
    except RedisError:
        pass


def cached_weather(settings: Settings, payload: PlanGenerateRequest) -> list[DailyWeather] | None:
    try:
        value = Redis.from_url(settings.redis_url).get(weather_cache_key(payload))
        if not value:
            return None
        decoded = json.loads(value)
        result = [weather_from_snapshot(item) for item in decoded]
        return [item for item in result if item is not None]
    except (RedisError, ValueError, TypeError, KeyError):
        return None


def read_url(key: str, settings: Settings) -> str:
    return public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.upload_url_ttl_seconds,
    )


def weather_json(weather: DailyWeather | None) -> dict:
    if weather is None:
        return {"provisional": True, "unavailable": True}
    result = asdict(weather)
    result["date"] = weather.date.isoformat()
    result["provisional"] = weather.confidence is not None and weather.confidence < 0.5
    return result


def garment_color_map(db: Session, garment_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    colors = db.execute(
        select(GarmentColor.garment_id, GarmentColor.hex_value).where(
            GarmentColor.garment_id.in_(garment_ids), GarmentColor.rank == 0
        )
    ).all()
    return dict(colors)


def prune_candidates(garments: list[Garment], locked_ids: set[uuid.UUID]) -> list[Garment]:
    by_category: dict[GarmentCategory, list[Garment]] = {}
    for garment in garments:
        by_category.setdefault(garment.category, []).append(garment)
    result = []
    for category, items in by_category.items():
        items.sort(
            key=lambda garment: (
                garment.id not in locked_ids,
                garment.wear_count,
                garment.last_worn_at or datetime.min.replace(tzinfo=UTC),
            )
        )
        limit = CANDIDATE_LIMITS.get(category, 10)
        selected = items[:limit]
        selected_ids = {item.id for item in selected}
        selected.extend(
            item for item in items if item.id in locked_ids and item.id not in selected_ids
        )
        result.extend(selected)
    return result


def build_planning_request(
    payload: PlanGenerateRequest,
    garments: list[Garment],
    colors: dict[uuid.UUID, str],
    weather: list[DailyWeather | None],
    preferences: UserSettings | None = None,
) -> PlanRequest:
    days = tuple(payload.start_date + timedelta(days=offset) for offset in range(payload.days))
    requirements = {item.date: item for item in payload.daily_requirements}
    garment_dicts = [
        {
            "id": str(garment.id),
            "category": garment.category.value,
            "color": colors.get(garment.id, "#808080"),
            "formality": garment.formality or 0,
            "pattern": garment.pattern or "unknown",
        }
        for garment in garments
    ]
    planning_garments = []
    for garment, description in zip(garments, garment_dicts, strict=True):
        day_scores = []
        for index, plan_date in enumerate(days):
            weather_score, _ = (
                weather_suitability(
                    {
                        "warmth": garment.warmth,
                        "breathability": garment.breathability,
                        "water_resistance": garment.water_resistance,
                    },
                    weather[index],
                )
                if weather[index]
                else (55, [])
            )
            event_score = 0
            requirement = requirements.get(plan_date)
            if requirement:
                formality = garment.formality or 0
                event_score = (
                    50
                    if requirement.minimum_formality <= formality <= requirement.maximum_formality
                    else -120
                )
            preference_score = 0
            if preferences:
                preference_score = max(
                    0, 20 - abs((garment.formality or 0) - preferences.preferred_formality) * 5
                )
            underuse = max(0, 30 - garment.wear_count * 3)
            day_scores.append(
                weather_score * 10 + event_score * 10 + preference_score * 10 + underuse
            )
        reuse_window = category_reuse_window(description["category"])
        if preferences:
            # Higher tolerance deliberately permits more repetition.
            reuse_window = max(1, reuse_window - max(0, preferences.repetition_tolerance - 2))
        planning_garments.append(
            PlanningGarment(
                str(garment.id),
                description["category"],
                tuple(day_scores),
                reuse_window,
            )
        )
    pair_scores = {}
    for left, right in meaningful_pairs(garment_dicts):
        breakdown = score_pair(left, right)
        pair_scores[left["id"], right["id"]] = breakdown.total
    date_indices = {value: index for index, value in enumerate(days)}
    locked = frozenset(
        (date_indices[item.date], str(item.garment_id))
        for item in payload.locked_items
        if item.date in date_indices
    )
    excluded = frozenset(
        (date_indices[item.date], str(item.garment_id))
        for item in payload.excluded_items
        if item.date in date_indices
    )
    weather_required: dict[int, frozenset[str]] = {}
    for day_index, forecast in enumerate(weather):
        if not forecast:
            continue
        severe_rain = forecast.precipitation_probability >= 80 and forecast.precipitation_mm >= 5
        severe_cold = forecast.planning_temp_c <= 0
        enforce_weather = preferences is None or preferences.weather_strictness >= 2
        if enforce_weather and (severe_rain or severe_cold):
            capable = frozenset(
                str(garment.id)
                for garment in garments
                if garment.category == GarmentCategory.outerwear
                and (
                    (severe_rain and (garment.water_resistance or 0) >= 3)
                    or (severe_cold and (garment.warmth or 0) >= 4)
                )
            )
            weather_required[day_index] = capable
    return PlanRequest(
        days=days,
        garments=tuple(planning_garments),
        pair_scores=pair_scores,
        locked_items=locked,
        excluded_items=excluded,
        weather_required_by_day=weather_required,
    )


def explain_day(
    selected: list[Garment], forecast: DailyWeather | None, compatibility: int
) -> list[str]:
    explanations = []
    if forecast:
        explanations.append(
            f"Planned for an apparent temperature near {round(forecast.planning_temp_c)}°C"
        )
        if forecast.precipitation_probability >= 50:
            explanations.append(f"Rain chance is {round(forecast.precipitation_probability)}%")
    if compatibility >= 500:
        explanations.append("The colours, formality, and patterns coordinate well")
    if all(garment.wear_count == 0 for garment in selected):
        explanations.append("These pieces have not been worn yet")
    return explanations or ["Structurally complete outfit from available garments"]


def persist_solution(
    db: Session,
    user: AuthenticatedUser,
    payload: PlanGenerateRequest,
    solution,
    garments_by_id: dict[str, Garment],
    weather: list[DailyWeather | None],
) -> OutfitPlan:
    plan = OutfitPlan(
        user_id=user.id,
        start_date=payload.start_date,
        end_date=payload.start_date + timedelta(days=payload.days - 1),
        status=solution.status,
        solver_version=SOLVER_VERSION,
        scoring_version=SCORING_VERSION,
        weather_provider=OpenMeteoProvider.name,
        weather_generated_at=datetime.now(UTC) if any(weather) else None,
        solve_time_ms=solution.solve_time_ms,
        objective_value=solution.objective_value,
    )
    db.add(plan)
    db.flush()
    locked_ids = {str(item.garment_id) for item in payload.locked_items}
    for index, solved_day in enumerate(solution.days):
        selected = [garments_by_id[item_id] for item_id in solved_day.garment_ids]
        score = {
            "weather": sum(
                weather_suitability(
                    {
                        "warmth": item.warmth,
                        "breathability": item.breathability,
                        "water_resistance": item.water_resistance,
                    },
                    weather[index],
                )[0]
                for item in selected
            )
            if weather[index]
            else 0,
            "compatibility": solved_day.compatibility_score,
            "rotation": 100 if "rotation" not in solution.relaxed_constraints else 0,
            "preference": 0,
            "event": 0,
            "total": solved_day.total_score,
        }
        day_record = OutfitPlanDay(
            plan_id=plan.id,
            plan_date=solved_day.date,
            weather_snapshot=weather_json(weather[index]),
            score_breakdown=score,
            explanations=explain_day(selected, weather[index], solved_day.compatibility_score),
            relaxed_constraints=list(solution.relaxed_constraints),
        )
        db.add(day_record)
        db.flush()
        for garment in selected:
            db.add(
                OutfitPlanGarment(
                    plan_day_id=day_record.id,
                    garment_id=garment.id,
                    category=garment.category,
                    is_user_locked=str(garment.id) in locked_ids,
                )
            )
    db.commit()
    return plan


def plan_response(db: Session, plan: OutfitPlan, settings: Settings) -> PlanResponse:
    day_records = db.scalars(
        select(OutfitPlanDay)
        .where(OutfitPlanDay.plan_id == plan.id)
        .order_by(OutfitPlanDay.plan_date)
    ).all()
    response_days = []
    relaxed = set()
    for day in day_records:
        rows = db.execute(
            select(OutfitPlanGarment, Garment)
            .join(Garment, Garment.id == OutfitPlanGarment.garment_id)
            .where(OutfitPlanGarment.plan_day_id == day.id)
        ).all()
        response_days.append(
            PlannedDayResponse(
                date=day.plan_date.isoformat(),
                garments=[
                    PlanGarmentResponse(
                        garment_id=garment.id,
                        category=garment.category.value,
                        display_name=garment.display_name or "Unnamed garment",
                        image_url=read_url(garment.processed_object_key, settings),
                    )
                    for _, garment in rows
                ],
                score=ScoreBreakdownResponse(**day.score_breakdown),
                explanations=day.explanations,
                provisional_weather=bool(day.weather_snapshot.get("provisional", False)),
                weather=day.weather_snapshot,
                is_locked=day.is_locked,
            )
        )
        relaxed.update(day.relaxed_constraints)
    return PlanResponse(
        plan_id=plan.id,
        status=plan.status,
        solve_time_ms=plan.solve_time_ms or 0,
        relaxed_constraints=sorted(relaxed),
        days=response_days,
    )


@router.post("/generate", response_model=PlanResponse)
async def generate_plan(
    payload: PlanGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    preferences = db.get(UserSettings, user.id)
    garments = db.scalars(
        select(Garment).where(
            Garment.user_id == user.id,
            Garment.processing_status == ProcessingStatus.ready,
            Garment.planner_enabled.is_(True),
            Garment.availability == Availability.available,
            Garment.category.is_not(None),
            Garment.metadata_confirmed_at.is_not(None),
        )
    ).all()
    if not garments:
        raise HTTPException(status_code=422, detail="No planner-eligible garments are available")
    if preferences and not preferences.accessory_usage:
        garments = [item for item in garments if item.category != GarmentCategory.accessory]
    garments = prune_candidates(list(garments), {item.garment_id for item in payload.locked_items})
    try:
        forecast = await OpenMeteoProvider().get_forecast(
            payload.location.latitude,
            payload.location.longitude,
            payload.start_date,
            payload.days,
            payload.location.timezone,
            preferences.active_start_hour if preferences else 8,
            preferences.active_end_hour if preferences else 18,
        )
        weather: list[DailyWeather | None] = list(forecast)
        cache_weather(settings, payload, list(forecast))
    except (httpx.HTTPError, KeyError, ValueError):
        recent = cached_weather(settings, payload)
        weather = list(recent) if recent and len(recent) == payload.days else [None] * payload.days
    request = build_planning_request(
        payload,
        garments,
        garment_color_map(db, [item.id for item in garments]),
        weather,
        preferences,
    )
    try:
        solution = solve_plan(request)
    except LockedConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if solution.status == "infeasible":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "plan_infeasible",
                "message": "No structurally valid plan could be generated",
                "suggestions": ["Make required categories available", "Remove conflicting locks"],
            },
        )
    plan = persist_solution(
        db, user, payload, solution, {str(item.id): item for item in garments}, weather
    )
    return plan_response(db, plan, settings)


def owned_plan(db: Session, plan_id: uuid.UUID, user_id: uuid.UUID) -> OutfitPlan:
    plan = db.scalar(
        select(OutfitPlan).where(OutfitPlan.id == plan_id, OutfitPlan.user_id == user_id)
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


def weather_from_snapshot(snapshot: dict) -> DailyWeather | None:
    if snapshot.get("unavailable"):
        return None
    fields = {
        key: value
        for key, value in snapshot.items()
        if key in DailyWeather.__dataclass_fields__ and key != "date"
    }
    return DailyWeather(date=date.fromisoformat(snapshot["date"]), **fields)


def regenerate_persisted_day(
    db: Session,
    plan: OutfitPlan,
    day: OutfitPlanDay,
    user: AuthenticatedUser,
    preserve_ids: list[uuid.UUID],
    excluded_ids: list[uuid.UUID],
    force_category: str | None = None,
) -> None:
    if day.is_locked:
        raise HTTPException(status_code=409, detail="Unlock this day before regenerating it")
    garments = db.scalars(
        select(Garment).where(
            Garment.user_id == user.id,
            Garment.processing_status == ProcessingStatus.ready,
            Garment.planner_enabled.is_(True),
            Garment.availability == Availability.available,
            Garment.category.is_not(None),
        )
    ).all()
    weather = weather_from_snapshot(day.weather_snapshot)
    payload = PlanGenerateRequest(
        start_date=day.plan_date,
        days=1,
        location=LocationRequest(latitude=0, longitude=0, timezone="UTC"),
        locked_items=[
            PlanItemConstraint(date=day.plan_date, garment_id=item_id) for item_id in preserve_ids
        ],
        excluded_items=[
            PlanItemConstraint(date=day.plan_date, garment_id=item_id) for item_id in excluded_ids
        ],
    )
    request = build_planning_request(
        payload,
        garments,
        garment_color_map(db, [item.id for item in garments]),
        [weather],
    )
    if force_category:
        request = replace(request, required_category_by_day={0: force_category})
    try:
        solution = solve_plan(request)
    except LockedConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if solution.status == "infeasible":
        raise HTTPException(status_code=422, detail="No alternative outfit is feasible")
    selected = [
        next(item for item in garments if str(item.id) == item_id)
        for item_id in solution.days[0].garment_ids
    ]
    db.execute(delete(OutfitPlanGarment).where(OutfitPlanGarment.plan_day_id == day.id))
    for garment in selected:
        db.add(
            OutfitPlanGarment(
                plan_day_id=day.id,
                garment_id=garment.id,
                category=garment.category,
                is_user_locked=garment.id in preserve_ids,
            )
        )
    day.score_breakdown = {
        "weather": sum(
            weather_suitability(
                {
                    "warmth": item.warmth,
                    "breathability": item.breathability,
                    "water_resistance": item.water_resistance,
                },
                weather,
            )[0]
            for item in selected
        )
        if weather
        else 0,
        "compatibility": solution.days[0].compatibility_score,
        "rotation": 0,
        "preference": 0,
        "event": 0,
        "total": solution.days[0].total_score,
    }
    day.explanations = explain_day(selected, weather, solution.days[0].compatibility_score)
    day.relaxed_constraints = list(solution.relaxed_constraints)
    plan.solve_time_ms = solution.solve_time_ms
    plan.objective_value = solution.objective_value
    db.commit()


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(
    plan_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    return plan_response(db, owned_plan(db, plan_id, user.id), settings)


@router.post("/{plan_id}/days/{plan_date}/lock", response_model=PlanResponse)
def lock_day(
    plan_id: uuid.UUID,
    plan_date: date,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    plan = owned_plan(db, plan_id, user.id)
    day = db.scalar(
        select(OutfitPlanDay).where(
            OutfitPlanDay.plan_id == plan.id, OutfitPlanDay.plan_date == plan_date
        )
    )
    if day is None:
        raise HTTPException(status_code=404, detail="Plan day not found")
    day.is_locked = not day.is_locked
    db.commit()
    return plan_response(db, plan, settings)


@router.post("/{plan_id}/days/{plan_date}/regenerate", response_model=PlanResponse)
def regenerate_day(
    plan_id: uuid.UUID,
    plan_date: date,
    payload: RegenerateDayRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    plan = owned_plan(db, plan_id, user.id)
    day = db.scalar(
        select(OutfitPlanDay).where(
            OutfitPlanDay.plan_id == plan.id, OutfitPlanDay.plan_date == plan_date
        )
    )
    if day is None:
        raise HTTPException(status_code=404, detail="Plan day not found")
    previous = db.scalars(
        select(OutfitPlanGarment.garment_id).where(OutfitPlanGarment.plan_day_id == day.id)
    ).all()
    excluded = (
        [item_id for item_id in previous if item_id not in payload.preserve_garment_ids]
        if payload.exclude_previous_selection
        else []
    )
    regenerate_persisted_day(db, plan, day, user, payload.preserve_garment_ids, list(excluded))
    return plan_response(db, plan, settings)


@router.post("/{plan_id}/days/{plan_date}/replace", response_model=PlanResponse)
def replace_garment(
    plan_id: uuid.UUID,
    plan_date: date,
    payload: ReplaceGarmentRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    plan = owned_plan(db, plan_id, user.id)
    day = db.scalar(
        select(OutfitPlanDay).where(
            OutfitPlanDay.plan_id == plan.id, OutfitPlanDay.plan_date == plan_date
        )
    )
    if day is None:
        raise HTTPException(status_code=404, detail="Plan day not found")
    rows = db.execute(
        select(OutfitPlanGarment, Garment)
        .join(Garment, Garment.id == OutfitPlanGarment.garment_id)
        .where(OutfitPlanGarment.plan_day_id == day.id)
    ).all()
    current = next((garment for _, garment in rows if garment.id == payload.garment_id), None)
    if current is None or current.category.value != payload.replacement_category:
        raise HTTPException(status_code=422, detail="Replacement category does not match garment")
    preserve = [garment.id for _, garment in rows if garment.id != current.id]
    regenerate_persisted_day(
        db,
        plan,
        day,
        user,
        preserve,
        [current.id],
        force_category=payload.replacement_category,
    )
    db.add(
        OutfitFeedback(
            user_id=user.id,
            plan_id=plan.id,
            plan_day_id=day.id,
            feedback_type="replaced_item",
            garment_ids=[current.id],
            metadata_json={"category": payload.replacement_category},
        )
    )
    db.commit()
    return plan_response(db, plan, settings)


@router.post("/feedback", status_code=201)
def record_feedback(
    payload: FeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.plan_id:
        owned_plan(db, payload.plan_id, user.id)
    db.add(
        OutfitFeedback(
            user_id=user.id,
            plan_id=payload.plan_id,
            plan_day_id=payload.plan_day_id,
            feedback_type=payload.feedback_type,
            garment_ids=payload.garment_ids,
            metadata_json=payload.metadata,
        )
    )
    db.commit()
    return {"status": "recorded"}
