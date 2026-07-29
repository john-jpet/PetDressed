from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UploadSessionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    file_size_bytes: int = Field(gt=0, le=15 * 1024 * 1024)


class UploadSessionResponse(BaseModel):
    garment_id: UUID
    upload_url: str
    object_key: str
    expires_at: datetime
    upload_method: Literal["POST"] = "POST"
    upload_fields: dict[str, str]


class UploadCompleteRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=1024)


class UploadCompleteResponse(BaseModel):
    garment_id: UUID
    processing_status: str


class GarmentStatusResponse(BaseModel):
    processing_status: str
    progress: int
    stage: str
    error: str | None


class InProgressGarmentResponse(BaseModel):
    garment_id: UUID
    processing_status: str


class PointPrompt(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class BoundingBox(BaseModel):
    x_min: int = Field(ge=0)
    y_min: int = Field(ge=0)
    x_max: int = Field(gt=0)
    y_max: int = Field(gt=0)


class MaskRun(BaseModel):
    start: int = Field(ge=0)
    length: int = Field(gt=0)
    value: Literal[0, 1]


class BrushStroke(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    radius: int = Field(ge=2, le=200)
    value: Literal[0, 1]


class SegmentationCorrectionRequest(BaseModel):
    positive_points: list[PointPrompt] = Field(default_factory=list, max_length=50)
    negative_points: list[PointPrompt] = Field(default_factory=list, max_length=50)
    bbox: BoundingBox | None = None
    mask_runs: list[MaskRun] = Field(default_factory=list, max_length=10_000)
    brush_strokes: list[BrushStroke] = Field(default_factory=list, max_length=2_000)


class SegmentationResultResponse(BaseModel):
    garment_id: UUID
    processed_url: str
    preview_url: str
    mask_url: str
    mask_area_ratio: float
    bbox: BoundingBox
    confidence: float
    review_status: Literal["pending", "accepted", "correction_required"]
    model_name: str
    model_version: str


class SegmentationAcceptResponse(BaseModel):
    garment_id: UUID
    processing_status: str


class ColorResponse(BaseModel):
    hex: str
    lab: tuple[float, float, float]
    proportion: float


class PredictionAlternative(BaseModel):
    value: str
    confidence: float


class MetadataReviewResponse(BaseModel):
    garment_id: UUID
    display_name: str | None
    predicted_category: str
    category_confidence: float
    category_alternatives: list[PredictionAlternative]
    subcategory: str | None
    formality: int
    warmth: int
    breathability: int
    water_resistance: int
    pattern: str
    colors: list[ColorResponse]
    seasons: dict[Literal["spring", "summer", "fall", "winter"], int]
    processed_url: str
    inference_backend: str
    degraded: bool
    inference_warning: str | None


class MetadataConfirmRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    category: Literal["top", "bottom", "one_piece", "outerwear", "shoes", "accessory"]
    subcategory: str | None = Field(default=None, max_length=64)
    formality: int = Field(ge=0, le=5)
    warmth: int = Field(ge=0, le=5)
    breathability: int = Field(ge=0, le=5)
    water_resistance: int = Field(ge=0, le=5)
    pattern: Literal[
        "solid",
        "striped",
        "checked",
        "graphic",
        "floral",
        "abstract",
        "textured",
        "other",
        "unknown",
    ]
    planner_enabled: bool
    seasons: dict[Literal["spring", "summer", "fall", "winter"], int]


class GarmentCardResponse(BaseModel):
    garment_id: UUID
    display_name: str
    category: str
    subcategory: str | None
    availability: str
    planner_enabled: bool
    wear_count: int
    last_worn_at: datetime | None
    colors: list[ColorResponse]
    pattern: str | None
    # `image_url` is the segmented cutout; `original_url` is the photo as
    # uploaded. Segmentation can crop badly, so clients showing a garment for
    # recognition should prefer the original.
    image_url: str
    original_url: str
    similarity: float | None = None


class WardrobeResponse(BaseModel):
    items: list[GarmentCardResponse]
    page: int
    page_size: int
    total: int


class GarmentUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    availability: Literal["available", "laundry", "unavailable", "packed", "archived"] | None = None
    planner_enabled: bool | None = None


class LocationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1, max_length=64)


class DailyRequirementRequest(BaseModel):
    date: date
    minimum_formality: int = Field(default=0, ge=0, le=5)
    maximum_formality: int = Field(default=5, ge=0, le=5)
    label: str | None = Field(default=None, max_length=100)


class PlanItemConstraint(BaseModel):
    date: date
    garment_id: UUID


class PlanGenerateRequest(BaseModel):
    start_date: date
    days: int = Field(default=7, ge=1, le=14)
    location: LocationRequest
    daily_requirements: list[DailyRequirementRequest] = Field(default_factory=list)
    locked_items: list[PlanItemConstraint] = Field(default_factory=list, max_length=100)
    excluded_items: list[PlanItemConstraint] = Field(default_factory=list, max_length=500)


class PlanGarmentResponse(BaseModel):
    garment_id: UUID
    category: str
    subcategory: str | None
    display_name: str
    # Colour and pattern let a client depict the outfit without relying on the
    # photo — see the mannequin renderer.
    colors: list[ColorResponse]
    pattern: str | None
    image_url: str
    original_url: str


class ScoreBreakdownResponse(BaseModel):
    weather: int
    compatibility: int
    rotation: int
    preference: int
    event: int
    total: int


class PlannedDayResponse(BaseModel):
    date: str
    garments: list[PlanGarmentResponse]
    score: ScoreBreakdownResponse
    explanations: list[str]
    provisional_weather: bool
    weather: dict
    is_locked: bool = False


class PlanResponse(BaseModel):
    plan_id: UUID
    status: str
    solve_time_ms: int
    relaxed_constraints: list[str]
    days: list[PlannedDayResponse]


class RegenerateDayRequest(BaseModel):
    preserve_garment_ids: list[UUID] = Field(default_factory=list)
    exclude_previous_selection: bool = True


class ReplaceGarmentRequest(BaseModel):
    garment_id: UUID
    replacement_category: Literal["top", "bottom", "one_piece", "outerwear", "shoes", "accessory"]


class FeedbackRequest(BaseModel):
    feedback_type: Literal[
        "accepted_plan",
        "accepted_day",
        "rejected_day",
        "replaced_item",
        "locked_item",
        "favourited_pair",
        "disliked_pair",
        "manual_outfit",
        "worn_as_planned",
        "not_worn",
    ]
    garment_ids: list[UUID] = Field(min_length=1)
    plan_id: UUID | None = None
    plan_day_id: UUID | None = None
    metadata: dict | None = None


class UserSettingsResponse(BaseModel):
    city: str | None
    latitude: float | None
    longitude: float | None
    timezone: str
    active_start_hour: int
    active_end_hour: int
    repetition_tolerance: int
    preferred_formality: int
    accessory_usage: bool
    weather_strictness: int


class UserSettingsUpdate(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = Field(min_length=1, max_length=64)
    active_start_hour: int = Field(ge=0, le=23)
    active_end_hour: int = Field(ge=0, le=23)
    repetition_tolerance: int = Field(ge=0, le=5)
    preferred_formality: int = Field(ge=0, le=5)
    accessory_usage: bool
    weather_strictness: int = Field(ge=0, le=5)
