"""
Integration tests for the FastAPI endpoints.
Uses TestClient with an in-memory SQLite database.
No external services (LLM, Redis, Celery) are required.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.database import Base, get_db
from backend.models import UserRole


# ── Test database setup ────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///./test_verdictbridge.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    # Dispose all connections before deleting the file (required on Windows)
    engine.dispose()
    db_path = "test_verdictbridge.db"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass  # Windows may still hold the handle briefly; not a test failure


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    """Register and login a test user, return auth headers."""
    client.post("/api/v1/auth/register", json={
        "email": "test@verdictbridge.gov.in",
        "full_name": "Test Officer",
        "password": "Test@1234",
        "department": "Public Works Department",
        "role": "officer",
    })
    # Use the JSON login endpoint (what the frontend uses)
    resp = client.post("/api/v1/auth/login/json", json={
        "email": "test@verdictbridge.gov.in",
        "password": "Test@1234",
    })
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def reviewer_headers(client):
    """Register and login a reviewer user."""
    client.post("/api/v1/auth/register", json={
        "email": "reviewer@verdictbridge.gov.in",
        "full_name": "Test Reviewer",
        "password": "Review@1234",
        "department": "Public Works Department",
        "role": "reviewer",
    })
    resp = client.post("/api/v1/auth/login/json", json={
        "email": "reviewer@verdictbridge.gov.in",
        "password": "Review@1234",
    })
    assert resp.status_code == 200, f"Reviewer login failed: {resp.json()}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Health check ───────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "llm_primary" in data


# ── Auth ───────────────────────────────────────────────────────────────────────

def test_register_duplicate(client, auth_headers):
    resp = client.post("/api/v1/auth/register", json={
        "email": "test@verdictbridge.gov.in",
        "full_name": "Duplicate",
        "password": "Test@1234",
        "department": "PWD",
        "role": "officer",
    })
    assert resp.status_code == 400


def test_login_form_endpoint(client):
    """OAuth2 form-encoded login (used by /docs Authorize button)."""
    resp = client.post("/api/v1/auth/login", data={
        "username": "test@verdictbridge.gov.in",
        "password": "Test@1234",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_json_endpoint(client):
    """JSON login (used by React frontend)."""
    resp = client.post("/api/v1/auth/login/json", json={
        "email": "test@verdictbridge.gov.in",
        "password": "Test@1234",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_case_insensitive_email(client):
    """Email lookup should be case-insensitive."""
    resp = client.post("/api/v1/auth/login/json", json={
        "email": "TEST@VERDICTBRIDGE.GOV.IN",
        "password": "Test@1234",
    })
    assert resp.status_code == 200


def test_login_wrong_password(client):
    resp = client.post("/api/v1/auth/login/json", json={
        "email": "test@verdictbridge.gov.in",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_login_wrong_password_form(client):
    resp = client.post("/api/v1/auth/login", data={
        "username": "test@verdictbridge.gov.in",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_me(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@verdictbridge.gov.in"


def test_protected_without_token(client):
    resp = client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 401


# ── Dashboard ──────────────────────────────────────────────────────────────────

def test_dashboard_stats(client, auth_headers):
    resp = client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_documents" in data
    assert "by_status" in data
    assert "pending_actions" in data
    assert "red_alert_count" in data


def test_list_documents_empty(client, auth_headers):
    resp = client.get("/api/v1/dashboard/documents", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data


# ── Upload ─────────────────────────────────────────────────────────────────────

def test_upload_invalid_type(client, auth_headers):
    resp = client.post(
        "/api/v1/upload/",
        headers=auth_headers,
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 415


def test_upload_pdf(client, auth_headers):
    """Upload a minimal valid PDF — tests the upload path, not extraction."""
    minimal_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )

    # Patch at the module where it's now imported at the top level
    with patch("backend.routes.upload.run_extraction_pipeline") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-task-id-123"
        mock_task.delay.return_value = mock_result

        resp = client.post(
            "/api/v1/upload/",
            headers=auth_headers,
            files={"file": ("judgment.pdf", minimal_pdf, "application/pdf")},
        )

    assert resp.status_code == 201, f"Upload failed: {resp.json()}"
    data = resp.json()
    assert data["original_filename"] == "judgment.pdf"
    assert data["status"] == "queued"


# ── Extraction result ──────────────────────────────────────────────────────────

def test_get_extraction_not_found(client, auth_headers):
    resp = client.get(
        "/api/v1/extraction/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── Audit log ──────────────────────────────────────────────────────────────────

def test_audit_logs(client, auth_headers):
    resp = client.get("/api/v1/dashboard/audit-logs", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
