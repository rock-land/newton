"""Tests for app version reading from VERSION file (T-405-FIX2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_app_version_matches_version_file() -> None:
    """FastAPI app version should be read from the VERSION file."""
    from pathlib import Path

    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    expected = version_file.read_text().strip()
    assert app.version == expected


def test_openapi_version_matches() -> None:
    """OpenAPI schema should reflect the VERSION file version."""
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    from pathlib import Path

    expected = (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()
    assert schema["info"]["version"] == expected
