"""Tests for data API endpoint validation (T-405-FIX1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


class TestInstrumentValidation:
    """Instrument validation on data endpoints."""

    def test_ohlcv_rejects_unsupported_instrument(self) -> None:
        resp = client.get("/api/v1/ohlcv/INVALID?interval=1h&start=2020-01-01T00:00:00Z")
        assert resp.status_code == 400
        assert "Unsupported instrument" in resp.json()["detail"]

    def test_ohlcv_accepts_supported_instrument(self) -> None:
        """EUR_USD and BTC_USD should pass validation (may fail at DB layer)."""
        resp = client.get("/api/v1/ohlcv/EUR_USD?interval=1h&start=2020-01-01T00:00:00Z")
        # 503 (no DB) or 500 (DB connection failed) are acceptable — not 400
        assert resp.status_code != 400

    def test_features_rejects_unsupported_instrument(self) -> None:
        resp = client.get("/api/v1/features/INVALID?interval=1h&start=2020-01-01T00:00:00Z")
        assert resp.status_code == 400
        assert "Unsupported instrument" in resp.json()["detail"]

    def test_compute_features_rejects_unsupported_instrument(self) -> None:
        resp = client.post(
            "/api/v1/features/compute",
            json={"instrument": "INVALID", "interval": "1h"},
        )
        assert resp.status_code == 400
        assert "Unsupported instrument" in resp.json()["detail"]


class TestErrorMessageSanitization:
    """Error messages must not leak internal exception details."""

    def test_ohlcv_error_message_is_generic(self) -> None:
        """When DB query fails, error message should not contain exception text."""
        import os

        saved = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://invalid:invalid@localhost:1/nonexistent"
        try:
            resp = client.get("/api/v1/ohlcv/EUR_USD?interval=1h&start=2020-01-01T00:00:00Z")
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved
            else:
                os.environ.pop("DATABASE_URL", None)

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "Failed to query OHLCV data" == detail
        # Must not contain connection strings or exception details
        assert "postgresql" not in detail.lower()
        assert "connect" not in detail.lower()

    def test_features_error_message_is_generic(self) -> None:
        import os

        saved = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://invalid:invalid@localhost:1/nonexistent"
        try:
            resp = client.get("/api/v1/features/EUR_USD?interval=1h&start=2020-01-01T00:00:00Z")
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved
            else:
                os.environ.pop("DATABASE_URL", None)

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "Failed to query features" == detail
        assert "postgresql" not in detail.lower()

    def test_compute_features_error_message_is_generic(self) -> None:
        import os

        saved = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://invalid:invalid@localhost:1/nonexistent"
        try:
            resp = client.post(
                "/api/v1/features/compute",
                json={"instrument": "EUR_USD", "interval": "1h"},
            )
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved
            else:
                os.environ.pop("DATABASE_URL", None)

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "Feature computation failed" == detail
        assert "postgresql" not in detail.lower()
