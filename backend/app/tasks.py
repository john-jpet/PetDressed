import uuid
from io import BytesIO

import numpy as np
from celery import Celery
from PIL import Image, ImageDraw, UnidentifiedImageError
from sqlalchemy import delete, select

from .config import get_settings
from .db import SessionLocal
from .metadata import create_metadata_extractor, infer_baseline_metadata
from .models import (
    Garment,
    GarmentCategory,
    GarmentColor,
    GarmentPrediction,
    GarmentSeason,
    MetadataSource,
    OutfitPlanGarment,
    ProcessingStatus,
)
from .segmentation import (
    Prompt,
    apply_mask_runs,
    create_segmenter,
    normalize_image,
    render_artifacts,
)
from .storage import internal_client

settings = get_settings()
celery_app = Celery("petdressed", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True


def validate_image(data: bytes, expected_content_type: str) -> tuple[int, int, str]:
    format_to_mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            detected_type = format_to_mime.get(image.format or "")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded file is not a safe, decodable image") from exc
    if detected_type != expected_content_type:
        raise ValueError("The detected image format does not match its content type")
    if min(width, height) < 256:
        raise ValueError("The image is smaller than 256 pixels")
    if max(width, height) > 6000 or width * height > 30_000_000:
        raise ValueError("The image dimensions exceed the supported limit")
    return width, height, detected_type


@celery_app.task(
    bind=True,
    name="validate_uploaded_garment",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def validate_uploaded_garment(
    self, garment_id: str, user_id: str, object_key: str, revision: int
) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        garment = db.scalar(
            select(Garment).where(
                Garment.id == uuid.UUID(garment_id),
                Garment.user_id == uuid.UUID(user_id),
                Garment.processing_revision == revision,
                Garment.processing_status == ProcessingStatus.uploaded,
            )
        )
        if garment is None:
            return {"status": "stale"}
        try:
            response = internal_client().get_object(Bucket=settings.s3_bucket, Key=object_key)
            data = response["Body"].read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise ValueError("The uploaded image exceeds 15 MB")
            width, height, content_type = validate_image(data, garment.original_content_type)
            garment.processing_status = ProcessingStatus.queued
            garment.processing_error_code = None
            garment.processing_error_message = None
            db.commit()
            segment_garment.delay(garment_id, user_id, object_key, revision)
            return {
                "garment_id": garment_id,
                "status": "queued",
                "width": width,
                "height": height,
                "content_type": content_type,
            }
        except ValueError as exc:
            garment.processing_status = ProcessingStatus.failed
            garment.processing_error_code = "invalid_image"
            garment.processing_error_message = str(exc)
            db.commit()
            return {"garment_id": garment_id, "status": "failed", "error": str(exc)}


@celery_app.task(
    bind=True, name="segment_garment", autoretry_for=(ConnectionError,), retry_backoff=True
)
def segment_garment(
    self,
    garment_id: str,
    user_id: str,
    object_key: str,
    revision: int,
    prompt_data: dict | None = None,
) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        garment = db.scalar(
            select(Garment).where(
                Garment.id == uuid.UUID(garment_id),
                Garment.user_id == uuid.UUID(user_id),
                Garment.processing_revision == revision,
                Garment.processing_status.in_(
                    [ProcessingStatus.queued, ProcessingStatus.segmenting]
                ),
            )
        )
        if garment is None:
            return {"status": "stale"}
        garment.processing_status = ProcessingStatus.segmenting
        db.commit()
        try:
            response = internal_client().get_object(Bucket=settings.s3_bucket, Key=object_key)
            source = response["Body"].read(settings.max_upload_bytes + 1)
            image = normalize_image(source, settings.inference_max_dimension)
            prompt = (
                Prompt(
                    positive_points=tuple(prompt_data.get("positive_points", ())),
                    negative_points=tuple(prompt_data.get("negative_points", ())),
                    bbox=prompt_data.get("bbox"),
                )
                if prompt_data
                else None
            )
            segmenter = create_segmenter(
                settings.segmentation_backend,
                settings.segmentation_checkpoint,
                settings.segmentation_model_config,
                settings.inference_device,
                settings.model_cache_dir,
                settings.embedding_model_name,
            )
            output = segmenter.segment(image, prompt)
            mask = output.mask
            if prompt_data:
                runs = [
                    (run["start"], run["length"], run["value"])
                    for run in prompt_data.get("mask_runs", [])
                ]
                if runs:
                    mask = apply_mask_runs(mask, runs)
                if prompt_data.get("brush_strokes"):
                    mask_image = Image.fromarray((mask * 255).astype(np.uint8))
                    drawing = ImageDraw.Draw(mask_image)
                    for stroke in prompt_data["brush_strokes"]:
                        x, y, radius = stroke["x"], stroke["y"], stroke["radius"]
                        drawing.ellipse(
                            (x - radius, y - radius, x + radius, y + radius),
                            fill=255 if stroke["value"] else 0,
                        )
                    mask = np.asarray(mask_image) > 127
            artifacts = render_artifacts(image, mask)
            prefix = f"users/{user_id}/garments/{garment_id}/revision-{revision}"
            keys = {
                "processed": f"{prefix}/processed.png",
                "preview": f"{prefix}/preview.png",
                "mask": f"{prefix}/mask.png",
            }
            client = internal_client()
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=keys["processed"],
                Body=artifacts.processed_png,
                ContentType="image/png",
            )
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=keys["preview"],
                Body=artifacts.preview_png,
                ContentType="image/png",
            )
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=keys["mask"],
                Body=artifacts.mask_png,
                ContentType="image/png",
            )
            garment.processed_object_key = keys["processed"]
            garment.preview_object_key = keys["preview"]
            garment.mask_object_key = keys["mask"]
            garment.mask_area_ratio = artifacts.mask_area_ratio
            garment.segmentation_bbox = {
                "x_min": artifacts.bbox[0],
                "y_min": artifacts.bbox[1],
                "x_max": artifacts.bbox[2],
                "y_max": artifacts.bbox[3],
            }
            garment.segmentation_confidence = output.confidence
            garment.segmentation_model = output.model_name
            garment.segmentation_model_version = output.model_version
            garment.processing_status = ProcessingStatus.segmentation_review
            db.commit()
            return {"garment_id": garment_id, "status": "segmentation_review"}
        except (ValueError, RuntimeError) as exc:
            garment.processing_status = ProcessingStatus.failed
            garment.processing_error_code = "segmentation_failed"
            garment.processing_error_message = str(exc)
            db.commit()
            return {"garment_id": garment_id, "status": "failed", "error": str(exc)}


@celery_app.task(
    bind=True, name="extract_garment_metadata", autoretry_for=(ConnectionError,), retry_backoff=True
)
def extract_garment_metadata(
    self, garment_id: str, user_id: str, processed_object_key: str, revision: int
) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        garment = db.scalar(
            select(Garment).where(
                Garment.id == uuid.UUID(garment_id),
                Garment.user_id == uuid.UUID(user_id),
                Garment.processing_revision == revision,
                Garment.processing_status == ProcessingStatus.extracting_metadata,
            )
        )
        if garment is None:
            return {"status": "stale"}
        try:
            response = internal_client().get_object(
                Bucket=settings.s3_bucket, Key=processed_object_key
            )
            with Image.open(response["Body"]) as source:
                image = source.convert("RGBA")
            try:
                output = create_metadata_extractor(
                    settings.metadata_backend,
                    settings.embedding_model_name,
                    settings.inference_device,
                    settings.model_cache_dir,
                ).extract(image, garment.original_filename)
                garment.processing_error_code = None
                garment.processing_error_message = None
            except RuntimeError as model_error:
                output = infer_baseline_metadata(image, garment.original_filename)
                garment.processing_error_code = "metadata_backend_unavailable"
                garment.processing_error_message = str(model_error)
            db.execute(delete(GarmentColor).where(GarmentColor.garment_id == garment.id))
            db.execute(delete(GarmentPrediction).where(GarmentPrediction.garment_id == garment.id))
            db.execute(delete(GarmentSeason).where(GarmentSeason.garment_id == garment.id))
            garment.predicted_category = GarmentCategory(output.category.value)
            garment.category_confidence = output.category.confidence
            garment.category_source = MetadataSource.model
            garment.predicted_subcategory = output.subcategory.value or None
            garment.subcategory = output.subcategory.value or None
            garment.formality = output.formality
            garment.warmth = output.warmth
            garment.breathability = output.breathability
            garment.water_resistance = output.water_resistance
            garment.pattern = output.pattern
            garment.embedding = output.embedding
            garment.embedding_model = output.model_name
            garment.embedding_model_version = output.model_version
            garment.prompt_set_version = settings.prompt_set_version
            garment.processing_status = ProcessingStatus.metadata_review
            for rank, color in enumerate(output.colors):
                db.add(
                    GarmentColor(
                        garment_id=garment.id,
                        rank=rank,
                        hex_value=color.hex_value,
                        lab_l=color.lab[0],
                        lab_a=color.lab[1],
                        lab_b=color.lab[2],
                        proportion=color.proportion,
                    )
                )
            season_values = {
                "spring": 4 if output.warmth <= 3 else 3,
                "summer": 5 if output.warmth <= 2 else 2,
                "fall": 4 if output.warmth >= 2 else 3,
                "winter": 4 if output.warmth >= 4 else 1,
            }
            for season, suitability in season_values.items():
                db.add(
                    GarmentSeason(
                        garment_id=garment.id,
                        season=season,
                        suitability=suitability,
                    )
                )
            predictions = [
                ("category", output.category.value, output.category.confidence),
                ("pattern", output.pattern, None),
            ]
            if output.subcategory.value:
                predictions.append(
                    ("subcategory", output.subcategory.value, output.subcategory.confidence)
                )
            predictions.extend(
                ("category_alternative", value, confidence)
                for value, confidence in output.category.alternatives
            )
            for attribute, value, confidence in predictions:
                db.add(
                    GarmentPrediction(
                        garment_id=garment.id,
                        attribute_name=attribute,
                        predicted_value=value,
                        confidence=confidence,
                        model_name=output.model_name,
                        model_version=output.model_version,
                        prompt_set_version=settings.prompt_set_version,
                    )
                )
            db.commit()
            return {"garment_id": garment_id, "status": "metadata_review"}
        except (ValueError, OSError) as exc:
            garment.processing_status = ProcessingStatus.metadata_review
            garment.processing_error_code = "metadata_partial_failure"
            garment.processing_error_message = str(exc)
            db.commit()
            return {"garment_id": garment_id, "status": "metadata_review", "error": str(exc)}


@celery_app.task(
    bind=True, name="delete_garment_artifacts", autoretry_for=(ConnectionError,), retry_backoff=True
)
def delete_garment_artifacts(self, garment_id: str, user_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        garment = db.scalar(
            select(Garment).where(
                Garment.id == uuid.UUID(garment_id),
                Garment.user_id == uuid.UUID(user_id),
                Garment.processing_status == ProcessingStatus.archived,
            )
        )
        if garment is None:
            return {"status": "stale"}
        prefix = f"users/{user_id}/garments/{garment_id}/"
        client = internal_client()
        listed = client.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        objects = [{"Key": item["Key"]} for item in listed.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})
        db.execute(delete(OutfitPlanGarment).where(OutfitPlanGarment.garment_id == garment.id))
        db.delete(garment)
        db.commit()
        return {"garment_id": garment_id, "status": "deleted"}
