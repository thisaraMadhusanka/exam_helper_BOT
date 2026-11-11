"""Regression tests for backend API route registration."""

import os
import sys
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["SESSION_SECRET"] = "test-secret-key-for-testing-only"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "test-service-role-key"
os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["EMBEDDING_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"
os.environ["TOP_K"] = "4"
os.environ["MIN_SIMILARITY"] = "0.0"

from app import app, demo, validate_image_data_urls
from services.vector_store import generate_embeddings_on_zero_gpu
from utils.config import config


def test_search_and_ask_routes_are_registered():
    registered_routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("/search", "POST") in registered_routes
    assert ("/ask", "POST") in registered_routes
    assert ("/admin/login", "POST") in registered_routes
    assert ("/admin/login-code", "POST") in registered_routes
    assert ("/admin/verify", "GET") in registered_routes
    assert ("/admin/documents", "GET") in registered_routes
    assert ("/admin/documents/{document_id}", "DELETE") in registered_routes
    assert ("/admin/lessons/{lesson_id}/assign-document/{document_id}", "POST") in registered_routes
    assert ("/lessons/{lesson_id}/documents/{document_id}", "DELETE") in registered_routes


def test_cors_middleware_uses_configured_origins():
    cors_middleware = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors_middleware.kwargs["allow_origins"] == config.CORS_ORIGINS


def test_cors_env_overrides_default_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://example.vercel.app, https://www.example.com")

    assert config.CORS_ORIGINS == [
        "https://example.vercel.app",
        "https://www.example.com",
    ]


def test_zero_gpu_function_is_registered_as_gradio_event():
    assert any(
        getattr(block_function, "fn", None) is generate_embeddings_on_zero_gpu
        for block_function in demo.fns.values()
    )


def test_image_data_url_validation_accepts_supported_image_signatures():
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-data").decode("ascii")

    assert validate_image_data_urls([f"data:image/png;base64,{png}"]) == [
        f"data:image/png;base64,{png}"
    ]


def test_image_data_url_validation_rejects_bad_signatures_and_too_many_images():
    with pytest.raises(ValueError, match="valid image"):
        validate_image_data_urls(["data:image/png;base64,aW52YWxpZA=="])

    with pytest.raises(ValueError, match="up to 3"):
        validate_image_data_urls([""] * 4)


def test_admin_login_requires_configured_email_and_password(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "test-secret-key-for-testing-only")
    monkeypatch.setattr(config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(config, "ADMIN_USERNAME", "test-admin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "test-password")

    with TestClient(app) as client:
        response = client.post(
            "/admin/login",
            json={"email": " ADMIN@example.com ", "password": "test-password"},
        )
        assert response.status_code == 200
        assert response.json()["username"] == "test-admin"

        token = response.json()["access_token"]
        verified = client.get(
            "/admin/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert verified.status_code == 200
        assert verified.json()["username"] == "test-admin"

        wrong_password = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "wrong-password"},
        )
        assert wrong_password.status_code == 401

        wrong_email = client.post(
            "/admin/login",
            json={"email": "other@example.com", "password": "test-password"},
        )
        assert wrong_email.status_code == 401


def test_admin_code_login_with_access_code(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "test-secret-key-for-testing-only")
    monkeypatch.setattr(config, "ADMIN_USERNAME", "test-admin")
    monkeypatch.setattr(config, "ADMIN_ACCESS_CODE", "ADMIN-TM-NEW")

    with TestClient(app) as client:
        # Correct code
        response = client.post(
            "/admin/login-code",
            json={"code": "ADMIN-TM-NEW"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert data["username"] == "test-admin"
        token = data["access_token"]

        # Verify token works on /admin/verify
        verified = client.get(
            "/admin/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert verified.status_code == 200

        # Incorrect code
        wrong_code = client.post(
            "/admin/login-code",
            json={"code": "WRONG-CODE"},
        )
        assert wrong_code.status_code == 401

        # Code login via /admin/login endpoint also works
        unified = client.post(
            "/admin/login",
            json={"code": "ADMIN-TM-NEW"},
        )
        assert unified.status_code == 200
