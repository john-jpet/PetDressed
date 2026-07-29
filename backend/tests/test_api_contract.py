from app.api import PROGRESS_BY_STATUS
from app.main import app
from app.models import ProcessingStatus


def test_progress_mapping_covers_every_processing_status():
    assert set(PROGRESS_BY_STATUS) == set(ProcessingStatus)


def test_v1_openapi_contains_complete_vertical_slice():
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/garments/uploads",
        "/api/v1/garments/in-progress",
        "/api/v1/garments/{garment_id}/uploads/complete",
        "/api/v1/garments/{garment_id}/status",
        "/api/v1/garments/{garment_id}/segmentation",
        "/api/v1/garments/{garment_id}/segmentation/retry",
        "/api/v1/garments/{garment_id}/segmentation/accept",
        "/api/v1/garments/{garment_id}/metadata",
        "/api/v1/garments/{garment_id}/metadata/confirm",
        "/api/v1/garments",
        "/api/v1/garments/{garment_id}/similar",
        "/api/v1/plans/generate",
        "/api/v1/plans/{plan_id}",
        "/api/v1/plans/{plan_id}/days/{plan_date}/regenerate",
        "/api/v1/plans/{plan_id}/days/{plan_date}/replace",
        "/api/v1/plans/{plan_id}/days/{plan_date}/lock",
        "/api/v1/settings",
    }
    assert expected <= set(paths)


def test_protected_routes_require_bearer_auth(monkeypatch):
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/api/v1/garments").status_code == 401
        assert client.get("/api/v1/settings").status_code == 401


def test_cors_allows_wardrobe_mutation_methods(monkeypatch):
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        for method in ("DELETE", "PATCH", "PUT"):
            response = client.options(
                "/api/v1/garments/00000000-0000-0000-0000-000000000000",
                headers={
                    "Origin": "http://localhost:3001",
                    "Access-Control-Request-Method": method,
                },
            )
            assert response.status_code == 200


def test_garment_payloads_expose_original_photo_and_appearance():
    """Clients need the uncropped photo and enough to depict the garment.

    Segmentation crops badly often enough that the cutout alone is a poor
    choice for recognition, and the mannequin renderer needs colour and
    pattern rather than an image.
    """
    schemas = app.openapi()["components"]["schemas"]

    card = schemas["GarmentCardResponse"]["properties"]
    assert "original_url" in card
    assert "image_url" in card, "the cutout stays available alongside the original"
    assert "pattern" in card

    planned = schemas["PlanGarmentResponse"]["properties"]
    for field in ("original_url", "image_url", "colors", "pattern", "subcategory"):
        assert field in planned, f"PlanGarmentResponse is missing {field}"
