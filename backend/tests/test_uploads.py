import uuid
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.tasks import validate_image


def test_health(monkeypatch):
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_upload_rejects_unsupported_type(monkeypatch):
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=uuid.uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/garments/uploads",
            json={"filename": "shirt.gif", "content_type": "image/gif", "file_size_bytes": 10},
        )
    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_upload_rejects_oversize_before_storage(monkeypatch):
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=uuid.uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/garments/uploads",
            json={
                "filename": "shirt.jpg",
                "content_type": "image/jpeg",
                "file_size_bytes": 15 * 1024 * 1024 + 1,
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 422


def image_bytes(size=(300, 400), image_format="JPEG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "navy").save(buffer, image_format)
    return buffer.getvalue()


def test_image_validation_accepts_supported_image():
    assert validate_image(image_bytes(), "image/jpeg") == (300, 400, "image/jpeg")


def test_image_validation_rejects_tiny_image():
    try:
        validate_image(image_bytes((100, 100)), "image/jpeg")
    except ValueError as exc:
        assert "smaller than 256" in str(exc)
    else:
        raise AssertionError("Expected a dimension validation error")


def test_image_validation_rejects_spoofed_content_type():
    try:
        validate_image(image_bytes(image_format="PNG"), "image/jpeg")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected a content-type validation error")
