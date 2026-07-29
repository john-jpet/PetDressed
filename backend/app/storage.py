import uuid
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import GarmentColor
from .schemas import ColorResponse


@lru_cache
def internal_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def public_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def presigned_read_url(object_key: str | None, settings: Settings) -> str:
    """Presigned GET for a stored object, addressed on the public endpoint.

    Object keys are nullable on `Garment` because artifacts appear at different
    stages of the pipeline. Returning an empty string keeps a half-processed
    garment renderable instead of failing the whole response.
    """
    if not object_key:
        return ""
    return public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key},
        ExpiresIn=settings.upload_url_ttl_seconds,
    )


def garment_colors_for(
    db: Session, garment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ColorResponse]]:
    """Palettes for many garments in one query, keyed by garment id.

    Callers render lists — a wardrobe page, every garment across a seven-day
    plan — so loading these one garment at a time is an N+1 that grows with the
    page size.
    """
    if not garment_ids:
        return {}
    records = db.scalars(
        select(GarmentColor)
        .where(GarmentColor.garment_id.in_(garment_ids))
        .order_by(GarmentColor.garment_id, GarmentColor.rank)
    ).all()
    palettes: dict[uuid.UUID, list[ColorResponse]] = {}
    for color in records:
        palettes.setdefault(color.garment_id, []).append(
            ColorResponse(
                hex=color.hex_value,
                lab=(color.lab_l, color.lab_a, color.lab_b),
                proportion=color.proportion,
            )
        )
    return palettes


def ensure_bucket() -> None:
    settings = get_settings()
    client = internal_client()
    if settings.s3_bucket not in [bucket["Name"] for bucket in client.list_buckets()["Buckets"]]:
        client.create_bucket(Bucket=settings.s3_bucket)
    try:
        client.put_bucket_cors(
            Bucket=settings.s3_bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedHeaders": ["*"],
                        "AllowedMethods": ["GET", "POST"],
                        "AllowedOrigins": settings.allowed_origins,
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NotImplemented":
            raise
