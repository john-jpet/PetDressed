from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import get_settings
from .observability import configure_observability
from .plan_routes import router as plan_router
from .storage import ensure_bucket


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bucket()
    yield


settings = get_settings()
app = FastAPI(title="PetDressed API", version="0.1.0", lifespan=lifespan)
configure_observability(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
app.include_router(plan_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
