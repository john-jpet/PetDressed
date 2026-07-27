from functools import lru_cache

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = "postgresql+psycopg://petdressed:petdressed@postgres:5432/petdressed"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "petdressed"
    s3_secret_key: str = "petdressed-local-only"
    s3_bucket: str = "petdressed"
    supabase_url: AnyHttpUrl = "https://example.supabase.co"
    supabase_jwt_audience: str = "authenticated"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    upload_url_ttl_seconds: int = 900
    max_upload_bytes: int = 15 * 1024 * 1024
    segmentation_backend: str = "sam2_transformers"
    segmentation_checkpoint: str | None = None
    segmentation_model_config: str = "facebook/sam2.1-hiera-tiny"
    inference_max_dimension: int = 1200
    metadata_backend: str = "fashion_clip"
    embedding_model_name: str = "patrickjohncyh/fashion-clip"
    inference_device: str = "cpu"
    model_cache_dir: str = "/models/huggingface"
    prompt_set_version: str = "category-prompts-2"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
