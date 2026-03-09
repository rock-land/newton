"""Tests for the in-app help docs API endpoint."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app, raise_server_exceptions=False)


class TestListHelpSections:
    """Tests for GET /api/v1/docs/sections."""

    def test_lists_available_sections(self) -> None:
        resp = client.get("/api/v1/docs/sections")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert "count" in data
        assert data["count"] == len(data["sections"])
        # We created 7 help files
        assert data["count"] >= 7
        assert "dashboard" in data["sections"]
        assert "index" in data["sections"]

    def test_returns_empty_when_dir_missing(self) -> None:
        with patch("src.api.v1.docs._HELP_DIR", Path("/nonexistent/path")):
            resp = client.get("/api/v1/docs/sections")
            assert resp.status_code == 200
            data = resp.json()
            assert data["sections"] == []
            assert data["count"] == 0


class TestGetHelpSection:
    """Tests for GET /api/v1/docs/{section}."""

    def test_returns_valid_section(self) -> None:
        resp = client.get("/api/v1/docs/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["section"] == "dashboard"
        assert data["title"] == "Dashboard"
        assert "# Dashboard" in data["content"]
        assert len(data["content"]) > 50

    def test_returns_index_section(self) -> None:
        resp = client.get("/api/v1/docs/index")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Newton Trading System"

    def test_all_help_sections_loadable(self) -> None:
        sections = ["index", "dashboard", "strategy", "trading", "config", "data", "backtest"]
        for section in sections:
            resp = client.get(f"/api/v1/docs/{section}")
            assert resp.status_code == 200, f"Failed to load section: {section}"
            data = resp.json()
            assert data["section"] == section
            assert len(data["title"]) > 0
            assert len(data["content"]) > 0

    def test_404_for_missing_section(self) -> None:
        resp = client.get("/api/v1/docs/nonexistent")
        assert resp.status_code == 404

    def test_400_for_invalid_section_name(self) -> None:
        resp = client.get("/api/v1/docs/../../etc/passwd")
        assert resp.status_code != 200

    def test_400_for_dotdot_traversal(self) -> None:
        resp = client.get("/api/v1/docs/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code != 200

    def test_400_for_special_characters(self) -> None:
        resp = client.get("/api/v1/docs/test%20file")
        assert resp.status_code == 400

    def test_valid_section_names_accepted(self) -> None:
        # Hyphen and underscore should be valid characters
        # These won't exist but should pass validation (get 404, not 400)
        resp = client.get("/api/v1/docs/my-section")
        assert resp.status_code == 404

        resp = client.get("/api/v1/docs/my_section")
        assert resp.status_code == 404


class TestExtractTitle:
    """Tests for the _extract_title helper."""

    def test_extracts_h1(self) -> None:
        from src.api.v1.docs import _extract_title
        assert _extract_title("# Hello World\n\nBody text") == "Hello World"

    def test_ignores_h2(self) -> None:
        from src.api.v1.docs import _extract_title
        assert _extract_title("## Not This\n\n# This One") == "This One"

    def test_returns_empty_for_no_heading(self) -> None:
        from src.api.v1.docs import _extract_title
        assert _extract_title("No heading here") == ""
