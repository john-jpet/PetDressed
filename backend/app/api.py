import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import AuthenticatedUser, get_current_user
from .config import Settings, get_settings
from .db import get_db
from .models import (
    Availability,
    Garment,
    GarmentCategory,
    GarmentPrediction,
    GarmentSeason,
    MetadataSource,
    ProcessingStatus,
    UserSettings,
)
from .schemas import (
    ColorResponse,
    GarmentCardResponse,
    GarmentStatusResponse,
    GarmentUpdateRequest,
    InProgressGarmentResponse,
    MetadataConfirmRequest,
    MetadataReviewResponse,
    PredictionAlternative,
    SegmentationAcceptResponse,
    SegmentationCorrectionRequest,
    SegmentationResultResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadSessionRequest,
    UploadSessionResponse,
    UserSettingsResponse,
    UserSettingsUpdate,
    WardrobeResponse,
)
from .storage import garment_colors_for, internal_client, presigned_read_url, public_client
from .tasks import (
    delete_garment_artifacts,
    extract_garment_metadata,
    segment_garment,
    validate_uploaded_garment,
)

router = APIRouter(prefix="/api/v1")
extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
PROGRESS_BY_STATUS = {
    ProcessingStatus.draft: (0, "Draft"),
    ProcessingStatus.uploading: (15, "Waiting for upload"),
    ProcessingStatus.uploaded: (30, "Upload received"),
    ProcessingStatus.queued: (40, "Queued for processing"),
    ProcessingStatus.segmenting: (65, "Removing the background"),
    ProcessingStatus.segmentation_review: (70, "Ready for background review"),
    ProcessingStatus.extracting_metadata: (85, "Describing the garment"),
    ProcessingStatus.metadata_review: (95, "Ready for details review"),
    ProcessingStatus.ready: (100, "Ready in wardrobe"),
    ProcessingStatus.failed: (100, "Processing failed"),
    ProcessingStatus.archived: (100, "Archived"),
}


def owned_garment(db: Session, garment_id: uuid.UUID, user_id: uuid.UUID) -> Garment:
    garment = db.scalar(select(Garment).where(Garment.id == garment_id, Garment.user_id == user_id))
    if garment is None:
        raise HTTPException(status_code=404, detail="Garment not found")
    return garment


@router.post("/garments/uploads", response_model=UploadSessionResponse, status_code=201)
def create_upload_session(
    payload: UploadSessionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadSessionResponse:
    garment_id = uuid.uuid4()
    suffix = extensions[payload.content_type]
    object_key = f"users/{user.id}/garments/{garment_id}/original{suffix}"
    garment = Garment(
        id=garment_id,
        user_id=user.id,
        processing_status=ProcessingStatus.uploading,
        original_filename=Path(payload.filename).name,
        original_content_type=payload.content_type,
        original_size_bytes=payload.file_size_bytes,
        original_object_key=object_key,
    )
    db.add(garment)
    db.commit()
    upload = public_client().generate_presigned_post(
        Bucket=settings.s3_bucket,
        Key=object_key,
        Fields={"Content-Type": payload.content_type},
        Conditions=[
            {"Content-Type": payload.content_type},
            ["content-length-range", 1, settings.max_upload_bytes],
            ["eq", "$key", object_key],
        ],
        ExpiresIn=settings.upload_url_ttl_seconds,
    )
    return UploadSessionResponse(
        garment_id=garment_id,
        upload_url=upload["url"],
        object_key=object_key,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.upload_url_ttl_seconds),
        upload_fields=upload["fields"],
    )


@router.get("/garments/in-progress", response_model=InProgressGarmentResponse | None)
def in_progress_garment(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InProgressGarmentResponse | None:
    garment = db.scalar(
        select(Garment)
        .where(
            Garment.user_id == user.id,
            Garment.processing_status.not_in(
                [ProcessingStatus.ready, ProcessingStatus.archived, ProcessingStatus.failed]
            ),
        )
        .order_by(Garment.updated_at.desc())
        .limit(1)
    )
    if garment is None:
        return None
    return InProgressGarmentResponse(
        garment_id=garment.id,
        processing_status=garment.processing_status.value,
    )


@router.post(
    "/garments/{garment_id}/uploads/complete",
    response_model=UploadCompleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def complete_upload(
    garment_id: uuid.UUID,
    payload: UploadCompleteRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadCompleteResponse:
    garment = owned_garment(db, garment_id, user.id)
    expected_prefix = f"users/{user.id}/garments/{garment.id}/"
    if payload.object_key != garment.original_object_key or not payload.object_key.startswith(
        expected_prefix
    ):
        raise HTTPException(status_code=400, detail="Object key does not match upload session")
    try:
        metadata = internal_client().head_object(
            Bucket=settings.s3_bucket, Key=garment.original_object_key
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Uploaded object not found") from exc
    if metadata["ContentLength"] != garment.original_size_bytes:
        raise HTTPException(status_code=409, detail="Uploaded object size does not match")
    if metadata.get("ContentType") != garment.original_content_type:
        raise HTTPException(status_code=409, detail="Uploaded object content type does not match")
    if not re.fullmatch(
        r"users/[0-9a-f-]+/garments/[0-9a-f-]+/original\.(jpg|png|webp)", payload.object_key
    ):
        raise HTTPException(status_code=400, detail="Invalid object key")
    garment.processing_status = ProcessingStatus.uploaded
    db.commit()
    validate_uploaded_garment.delay(
        str(garment.id), str(user.id), garment.original_object_key, garment.processing_revision
    )
    return UploadCompleteResponse(garment_id=garment.id, processing_status="uploaded")


@router.get("/garments/{garment_id}/status", response_model=GarmentStatusResponse)
def garment_status(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GarmentStatusResponse:
    garment = owned_garment(db, garment_id, user.id)
    progress, stage = PROGRESS_BY_STATUS[garment.processing_status]
    return GarmentStatusResponse(
        processing_status=garment.processing_status.value,
        progress=progress,
        stage=stage,
        error=garment.processing_error_message,
    )


@router.get(
    "/garments/{garment_id}/segmentation",
    response_model=SegmentationResultResponse,
)
def segmentation_result(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SegmentationResultResponse:
    garment = owned_garment(db, garment_id, user.id)
    if (
        garment.processing_status != ProcessingStatus.segmentation_review
        or not garment.processed_object_key
        or not garment.preview_object_key
        or not garment.mask_object_key
        or not garment.segmentation_bbox
    ):
        raise HTTPException(status_code=409, detail="Segmentation is not ready for review")
    return SegmentationResultResponse(
        garment_id=garment.id,
        processed_url=presigned_read_url(garment.processed_object_key, settings),
        preview_url=presigned_read_url(garment.preview_object_key, settings),
        mask_url=presigned_read_url(garment.mask_object_key, settings),
        mask_area_ratio=garment.mask_area_ratio or 0,
        bbox=garment.segmentation_bbox,
        confidence=garment.segmentation_confidence or 0,
        review_status="pending",
        model_name=garment.segmentation_model or "unknown",
        model_version=garment.segmentation_model_version or "unknown",
    )


@router.post(
    "/garments/{garment_id}/segmentation/retry",
    response_model=UploadCompleteResponse,
    status_code=202,
)
def retry_segmentation(
    garment_id: uuid.UUID,
    payload: SegmentationCorrectionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadCompleteResponse:
    garment = owned_garment(db, garment_id, user.id)
    if garment.processing_status not in {
        ProcessingStatus.segmentation_review,
        ProcessingStatus.failed,
    }:
        raise HTTPException(status_code=409, detail="Garment cannot be resegmented in this state")
    garment.processing_revision += 1
    garment.processing_status = ProcessingStatus.queued
    garment.processing_error_code = None
    garment.processing_error_message = None
    db.commit()
    prompt_data = {
        "positive_points": tuple((point.x, point.y) for point in payload.positive_points),
        "negative_points": tuple((point.x, point.y) for point in payload.negative_points),
        "bbox": (
            (
                payload.bbox.x_min,
                payload.bbox.y_min,
                payload.bbox.x_max,
                payload.bbox.y_max,
            )
            if payload.bbox
            else None
        ),
        "mask_runs": [run.model_dump() for run in payload.mask_runs],
        "brush_strokes": [stroke.model_dump() for stroke in payload.brush_strokes],
    }
    segment_garment.delay(
        str(garment.id),
        str(user.id),
        garment.original_object_key,
        garment.processing_revision,
        prompt_data,
    )
    return UploadCompleteResponse(garment_id=garment.id, processing_status="queued")


@router.post(
    "/garments/{garment_id}/segmentation/accept",
    response_model=SegmentationAcceptResponse,
)
def accept_segmentation(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SegmentationAcceptResponse:
    garment = owned_garment(db, garment_id, user.id)
    if garment.processing_status != ProcessingStatus.segmentation_review:
        raise HTTPException(status_code=409, detail="Segmentation is not ready to accept")
    garment.segmentation_accepted_at = datetime.now(UTC)
    garment.processing_status = ProcessingStatus.extracting_metadata
    db.commit()
    extract_garment_metadata.delay(
        str(garment.id),
        str(user.id),
        garment.processed_object_key,
        garment.processing_revision,
    )
    return SegmentationAcceptResponse(
        garment_id=garment.id, processing_status=garment.processing_status.value
    )


def garment_colors(db: Session, garment_id: uuid.UUID) -> list[ColorResponse]:
    return garment_colors_for(db, [garment_id]).get(garment_id, [])


def garment_seasons(db: Session, garment_id: uuid.UUID) -> dict[str, int]:
    return dict(
        db.execute(
            select(GarmentSeason.season, GarmentSeason.suitability).where(
                GarmentSeason.garment_id == garment_id
            )
        ).all()
    )


@router.get("/garments/{garment_id}/metadata", response_model=MetadataReviewResponse)
def metadata_review(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MetadataReviewResponse:
    garment = owned_garment(db, garment_id, user.id)
    if garment.processing_status != ProcessingStatus.metadata_review:
        raise HTTPException(status_code=409, detail="Metadata is not ready for review")
    alternatives = db.scalars(
        select(GarmentPrediction).where(
            GarmentPrediction.garment_id == garment.id,
            GarmentPrediction.attribute_name == "category_alternative",
        )
    ).all()
    return MetadataReviewResponse(
        garment_id=garment.id,
        display_name=garment.display_name,
        predicted_category=(garment.predicted_category or GarmentCategory.top).value,
        category_confidence=garment.category_confidence or 0,
        category_alternatives=[
            PredictionAlternative(value=item.predicted_value, confidence=item.confidence or 0)
            for item in alternatives
        ],
        subcategory=garment.subcategory,
        formality=garment.formality or 0,
        warmth=garment.warmth or 0,
        breathability=garment.breathability or 0,
        water_resistance=garment.water_resistance or 0,
        pattern=garment.pattern or "unknown",
        colors=garment_colors(db, garment.id),
        seasons=garment_seasons(db, garment.id),
        processed_url=presigned_read_url(garment.processed_object_key, settings),
        inference_backend=garment.embedding_model or "unknown",
        degraded=garment.embedding_model == "deterministic-test-fallback",
        inference_warning=garment.processing_error_message,
    )


@router.post("/garments/{garment_id}/metadata/confirm", response_model=GarmentCardResponse)
def confirm_metadata(
    garment_id: uuid.UUID,
    payload: MetadataConfirmRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GarmentCardResponse:
    garment = owned_garment(db, garment_id, user.id)
    if garment.processing_status != ProcessingStatus.metadata_review:
        raise HTTPException(status_code=409, detail="Metadata is not ready to confirm")
    garment.display_name = payload.display_name
    garment.category = GarmentCategory(payload.category)
    garment.category_source = MetadataSource.user
    garment.subcategory = payload.subcategory
    garment.formality = payload.formality
    garment.warmth = payload.warmth
    garment.breathability = payload.breathability
    garment.water_resistance = payload.water_resistance
    garment.pattern = payload.pattern
    garment.planner_enabled = payload.planner_enabled
    garment.metadata_confirmed_at = datetime.now(UTC)
    garment.processing_status = ProcessingStatus.ready
    db.execute(delete(GarmentSeason).where(GarmentSeason.garment_id == garment.id))
    for season, suitability in payload.seasons.items():
        if not 0 <= suitability <= 5:
            raise HTTPException(status_code=422, detail="Season suitability must be 0–5")
        db.add(
            GarmentSeason(
                garment_id=garment.id,
                season=season,
                suitability=suitability,
            )
        )
    db.commit()
    return garment_card(garment, garment_colors(db, garment.id), settings)


def garment_card(
    garment: Garment,
    colors: list[ColorResponse],
    settings: Settings,
    similarity: float | None = None,
) -> GarmentCardResponse:
    return GarmentCardResponse(
        garment_id=garment.id,
        display_name=garment.display_name or "Unnamed garment",
        category=(garment.category or GarmentCategory.top).value,
        subcategory=garment.subcategory,
        availability=garment.availability.value,
        planner_enabled=garment.planner_enabled,
        wear_count=garment.wear_count,
        last_worn_at=garment.last_worn_at,
        colors=colors,
        pattern=garment.pattern,
        image_url=presigned_read_url(garment.processed_object_key, settings),
        original_url=presigned_read_url(garment.original_object_key, settings),
        similarity=similarity,
    )


@router.get("/garments", response_model=WardrobeResponse)
def list_garments(
    category: GarmentCategory | None = None,
    availability: Availability | None = None,
    search: str | None = None,
    season: str | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 30,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WardrobeResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    filters = [
        Garment.user_id == user.id,
        Garment.processing_status == ProcessingStatus.ready,
    ]
    if category:
        filters.append(Garment.category == category)
    if availability:
        filters.append(Garment.availability == availability)
    if search:
        filters.append(Garment.display_name.ilike(f"%{search.strip()}%"))
    if season:
        if season not in {"spring", "summer", "fall", "winter"}:
            raise HTTPException(status_code=422, detail="Invalid season")
        filters.append(
            Garment.id.in_(
                select(GarmentSeason.garment_id).where(
                    GarmentSeason.season == season,
                    GarmentSeason.suitability >= 3,
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(Garment).where(*filters)) or 0
    order = {
        "least_worn": Garment.wear_count.asc(),
        "last_worn": Garment.last_worn_at.desc().nulls_last(),
        "name": Garment.display_name.asc(),
    }.get(sort, Garment.created_at.desc())
    garments = db.scalars(
        select(Garment)
        .where(*filters)
        .order_by(order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    palettes = garment_colors_for(db, [item.id for item in garments])
    return WardrobeResponse(
        items=[garment_card(item, palettes.get(item.id, []), settings) for item in garments],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.patch("/garments/{garment_id}", response_model=GarmentCardResponse)
def update_garment(
    garment_id: uuid.UUID,
    payload: GarmentUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GarmentCardResponse:
    garment = owned_garment(db, garment_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "availability":
            value = Availability(value)
        setattr(garment, field, value)
    db.commit()
    return garment_card(garment, garment_colors(db, garment.id), settings)


@router.post("/garments/{garment_id}/worn", response_model=GarmentCardResponse)
def mark_garment_worn(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GarmentCardResponse:
    garment = owned_garment(db, garment_id, user.id)
    garment.wear_count += 1
    garment.last_worn_at = datetime.now(UTC)
    db.commit()
    return garment_card(garment, garment_colors(db, garment.id), settings)


@router.delete("/garments/{garment_id}", status_code=202)
def delete_garment(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    garment = owned_garment(db, garment_id, user.id)
    garment.processing_status = ProcessingStatus.archived
    garment.availability = Availability.archived
    garment.planner_enabled = False
    db.commit()
    delete_garment_artifacts.delay(str(garment.id), str(user.id))
    return {"garment_id": str(garment.id), "deletion_status": "queued"}


@router.get("/garments/{garment_id}/similar", response_model=list[GarmentCardResponse])
def similar_garments(
    garment_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[GarmentCardResponse]:
    garment = owned_garment(db, garment_id, user.id)
    if garment.embedding is None:
        return []
    distance = Garment.embedding.cosine_distance(garment.embedding).label("distance")
    rows = db.execute(
        select(Garment, distance)
        .where(
            Garment.user_id == user.id,
            Garment.id != garment.id,
            Garment.processing_status == ProcessingStatus.ready,
            Garment.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(10)
    ).all()
    palettes = garment_colors_for(db, [item.id for item, _ in rows])
    return [
        garment_card(item, palettes.get(item.id, []), settings, 1.0 - float(item_distance))
        for item, item_distance in rows
    ]


def settings_response(value: UserSettings) -> UserSettingsResponse:
    return UserSettingsResponse(
        city=value.city,
        latitude=value.latitude,
        longitude=value.longitude,
        timezone=value.timezone,
        active_start_hour=value.active_start_hour,
        active_end_hour=value.active_end_hour,
        repetition_tolerance=value.repetition_tolerance,
        preferred_formality=value.preferred_formality,
        accessory_usage=value.accessory_usage,
        weather_strictness=value.weather_strictness,
    )


@router.get("/settings", response_model=UserSettingsResponse)
def get_user_settings(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    value = db.get(UserSettings, user.id)
    if value is None:
        value = UserSettings(user_id=user.id)
        db.add(value)
        db.commit()
    return settings_response(value)


@router.put("/settings", response_model=UserSettingsResponse)
def update_user_settings(
    payload: UserSettingsUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    if payload.active_end_hour <= payload.active_start_hour:
        raise HTTPException(status_code=422, detail="Active end time must follow start time")
    if (payload.latitude is None) != (payload.longitude is None):
        raise HTTPException(status_code=422, detail="Latitude and longitude must be set together")
    value = db.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    for field, item in payload.model_dump().items():
        setattr(value, field, item)
    db.add(value)
    db.commit()
    return settings_response(value)
