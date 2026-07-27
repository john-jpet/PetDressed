import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ProcessingStatus(str, enum.Enum):
    draft = "draft"
    uploading = "uploading"
    uploaded = "uploaded"
    queued = "queued"
    segmenting = "segmenting"
    segmentation_review = "segmentation_review"
    extracting_metadata = "extracting_metadata"
    metadata_review = "metadata_review"
    ready = "ready"
    failed = "failed"
    archived = "archived"


class Availability(str, enum.Enum):
    available = "available"
    laundry = "laundry"
    unavailable = "unavailable"
    packed = "packed"
    archived = "archived"


class GarmentCategory(str, enum.Enum):
    top = "top"
    bottom = "bottom"
    one_piece = "one_piece"
    outerwear = "outerwear"
    shoes = "shoes"
    accessory = "accessory"


class MetadataSource(str, enum.Enum):
    model = "model"
    user = "user"
    default = "default"


class Garment(Base):
    __tablename__ = "garments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="garment_processing_status"),
        nullable=False,
        default=ProcessingStatus.draft,
    )
    processing_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    processed_object_key: Mapped[str | None] = mapped_column(Text)
    preview_object_key: Mapped[str | None] = mapped_column(Text)
    mask_object_key: Mapped[str | None] = mapped_column(Text)
    mask_area_ratio: Mapped[float | None] = mapped_column(Float)
    segmentation_confidence: Mapped[float | None] = mapped_column(Float)
    segmentation_bbox: Mapped[dict | None] = mapped_column(JSONB)
    segmentation_model: Mapped[str | None] = mapped_column(String(100))
    segmentation_model_version: Mapped[str | None] = mapped_column(String(100))
    segmentation_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_name: Mapped[str | None] = mapped_column(String(100))
    availability: Mapped[Availability] = mapped_column(
        Enum(Availability, name="garment_availability"),
        nullable=False,
        default=Availability.available,
    )
    planner_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    category: Mapped[GarmentCategory | None] = mapped_column(
        Enum(GarmentCategory, name="garment_category")
    )
    predicted_category: Mapped[GarmentCategory | None] = mapped_column(
        Enum(GarmentCategory, name="garment_category")
    )
    category_confidence: Mapped[float | None] = mapped_column(Float)
    category_source: Mapped[MetadataSource | None] = mapped_column(
        Enum(MetadataSource, name="metadata_source")
    )
    subcategory: Mapped[str | None] = mapped_column(String(64))
    predicted_subcategory: Mapped[str | None] = mapped_column(String(64))
    formality: Mapped[int | None] = mapped_column(Integer)
    warmth: Mapped[int | None] = mapped_column(Integer)
    breathability: Mapped[int | None] = mapped_column(Integer)
    water_resistance: Mapped[int | None] = mapped_column(Integer)
    pattern: Mapped[str | None] = mapped_column(String(32))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_set_version: Mapped[str | None] = mapped_column(String(50))
    metadata_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_worn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error_code: Mapped[str | None] = mapped_column(String(64))
    processing_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GarmentColor(Base):
    __tablename__ = "garment_colors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("garments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_value: Mapped[str] = mapped_column(String(7), nullable=False)
    lab_l: Mapped[float] = mapped_column(Float, nullable=False)
    lab_a: Mapped[float] = mapped_column(Float, nullable=False)
    lab_b: Mapped[float] = mapped_column(Float, nullable=False)
    proportion: Mapped[float] = mapped_column(Float, nullable=False)


class GarmentPrediction(Base):
    __tablename__ = "garment_predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("garments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attribute_name: Mapped[str] = mapped_column(String(64), nullable=False)
    predicted_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_set_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GarmentSeason(Base):
    __tablename__ = "garment_seasons"

    garment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("garments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    season: Mapped[str] = mapped_column(String(16), primary_key=True)
    suitability: Mapped[int] = mapped_column(Integer, nullable=False)


class OutfitPlan(Base):
    __tablename__ = "outfit_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    solver_version: Mapped[str] = mapped_column(String(50), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    weather_provider: Mapped[str | None] = mapped_column(String(50))
    weather_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solve_time_ms: Mapped[int | None] = mapped_column(Integer)
    objective_value: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OutfitPlanDay(Base):
    __tablename__ = "outfit_plan_days"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfit_plans.id", ondelete="CASCADE"), nullable=False
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    weather_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanations: Mapped[list] = mapped_column(JSONB, nullable=False)
    relaxed_constraints: Mapped[list] = mapped_column(JSONB, nullable=False)


class OutfitPlanGarment(Base):
    __tablename__ = "outfit_plan_garments"

    plan_day_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outfit_plan_days.id", ondelete="CASCADE"),
        primary_key=True,
    )
    garment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garments.id"), primary_key=True
    )
    category: Mapped[GarmentCategory] = mapped_column(
        Enum(GarmentCategory, name="garment_category"), nullable=False
    )
    is_user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)


class OutfitFeedback(Base):
    __tablename__ = "outfit_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfit_plans.id", ondelete="SET NULL")
    )
    plan_day_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfit_plan_days.id", ondelete="SET NULL")
    )
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    garment_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    city: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    active_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    active_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=18)
    repetition_tolerance: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    preferred_formality: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    accessory_usage: Mapped[bool] = mapped_column(nullable=False, default=True)
    weather_strictness: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
