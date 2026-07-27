from __future__ import annotations

import json
import time
import uuid
from io import BytesIO

from PIL import Image, ImageDraw
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Garment, GarmentColor, ProcessingStatus
from app.storage import ensure_bucket, internal_client
from app.tasks import (
    delete_garment_artifacts,
    extract_garment_metadata,
    validate_uploaded_garment,
)


def synthetic_shirt() -> bytes:
    image = Image.new("RGB", (480, 600), "#F4F0E7")
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [
            (150, 120),
            (90, 190),
            (130, 270),
            (170, 235),
            (170, 500),
            (310, 500),
            (310, 235),
            (350, 270),
            (390, 190),
            (330, 120),
            (280, 105),
            (265, 145),
            (215, 145),
            (200, 105),
        ],
        fill="#274B77",
    )
    output = BytesIO()
    image.save(output, "JPEG", quality=92)
    return output.getvalue()


def wait_for_status(
    garment_id: uuid.UUID, expected: ProcessingStatus, timeout: int = 45
) -> Garment:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            garment = db.get(Garment, garment_id)
            if garment and garment.processing_status == expected:
                return garment
            if garment and garment.processing_status == ProcessingStatus.failed:
                raise RuntimeError(garment.processing_error_message or "Pipeline failed")
        time.sleep(0.5)
    raise TimeoutError(f"Garment did not reach {expected.value}")


def main() -> None:
    settings = get_settings()
    ensure_bucket()
    with SessionLocal() as db:
        previous = db.scalars(
            select(Garment).where(Garment.original_filename == "synthetic-shirt.jpg")
        ).all()
        previous_ids = [(item.id, item.user_id) for item in previous]
        for item in previous:
            item.processing_status = ProcessingStatus.archived
        db.commit()
    for old_garment_id, old_user_id in previous_ids:
        delete_garment_artifacts.delay(str(old_garment_id), str(old_user_id))
    user_id = uuid.uuid4()
    garment_id = uuid.uuid4()
    data = synthetic_shirt()
    key = f"users/{user_id}/garments/{garment_id}/original.jpg"
    internal_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType="image/jpeg",
    )
    with SessionLocal() as db:
        db.add(
            Garment(
                id=garment_id,
                user_id=user_id,
                processing_status=ProcessingStatus.uploaded,
                processing_revision=1,
                original_filename="synthetic-shirt.jpg",
                original_content_type="image/jpeg",
                original_size_bytes=len(data),
                original_object_key=key,
            )
        )
        db.commit()
    validate_uploaded_garment.delay(str(garment_id), str(user_id), key, 1)
    segmented = wait_for_status(garment_id, ProcessingStatus.segmentation_review)
    with SessionLocal() as db:
        garment = db.get(Garment, garment_id)
        garment.processing_status = ProcessingStatus.extracting_metadata
        db.commit()
    extract_garment_metadata.delay(str(garment_id), str(user_id), segmented.processed_object_key, 1)
    ready_for_review = wait_for_status(garment_id, ProcessingStatus.metadata_review)
    with SessionLocal() as db:
        colors = db.scalars(select(GarmentColor).where(GarmentColor.garment_id == garment_id)).all()
    result = {
        "status": ready_for_review.processing_status.value,
        "segmentation_model": ready_for_review.segmentation_model,
        "mask_area_ratio": ready_for_review.mask_area_ratio,
        "embedding_dimensions": len(ready_for_review.embedding),
        "palette_colors": len(colors),
        "artifacts_created": all(
            [
                ready_for_review.processed_object_key,
                ready_for_review.preview_object_key,
                ready_for_review.mask_object_key,
            ]
        ),
    }
    with SessionLocal() as db:
        garment = db.get(Garment, garment_id)
        garment.processing_status = ProcessingStatus.archived
        db.commit()
    delete_garment_artifacts.delay(str(garment_id), str(user_id))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
