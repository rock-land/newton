"""Data and health endpoints for Newton API v1."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
import os
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import (
    BrokerHealth,
    HealthResponse,
    InstrumentHealth,
    calculate_payload_checksum,
    utc_now,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data"])


@dataclass
class HealthService:
    """Collects system status used by the Stage-1 thin health panel."""

    startup_monotonic: float = field(default_factory=time.monotonic)

    def _database_url(self) -> str | None:
        return os.getenv("DATABASE_URL")

    def check_database(self) -> bool:
        db_url = self._database_url()
        if not db_url:
            return False

        try:
            import psycopg
        except ImportError:
            return False

        try:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() == (1,)
        except Exception:
            logger.exception("Database health check failed")
            return False

    def _query_last_candle_ages(self, instrument_ids: list[str], interval: str) -> dict[str, int | None]:
        db_url = self._database_url()
        if not db_url:
            return {instrument_id: None for instrument_id in instrument_ids}

        try:
            import psycopg
        except ImportError:
            return {instrument_id: None for instrument_id in instrument_ids}

        now = utc_now()
        ages: dict[str, int | None] = {instrument_id: None for instrument_id in instrument_ids}
        try:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    for instrument_id in instrument_ids:
                        cur.execute(
                            """
                            SELECT MAX(time)
                            FROM ohlcv
                            WHERE instrument = %s AND interval = %s AND verified = TRUE
                            """,
                            (instrument_id, interval),
                        )
                        row = cur.fetchone()
                        latest = row[0] if row else None
                        if latest is None:
                            ages[instrument_id] = None
                        else:
                            ages[instrument_id] = max(0, int((now - latest).total_seconds()))
        except Exception:
            logger.exception("Candle age query failed")
            return {instrument_id: None for instrument_id in instrument_ids}

        return ages

    def check_brokers(self) -> dict[str, BrokerHealth]:
        """Return broker connectivity status.

        Stage-1 implementation reports readiness based on key presence.
        """

        return {
            "oanda": BrokerHealth(
                connected=bool(os.getenv("OANDA_API_KEY")),
                last_response_ms=None,
            ),
            "binance": BrokerHealth(
                connected=bool(os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET")),
                last_response_ms=None,
            ),
        }

    def build_health(self) -> HealthResponse:
        interval = os.getenv("NEWTON_HEALTH_INTERVAL", "1h")
        instruments = ["EUR_USD", "BTC_USD"]
        db_ok = self.check_database()
        brokers = self.check_brokers()
        ages = self._query_last_candle_ages(instruments, interval)

        instrument_status = {
            instrument_id: InstrumentHealth(last_candle_age_seconds=ages[instrument_id])
            for instrument_id in instruments
        }

        overall_status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
        if not db_ok or any(not broker.connected for broker in brokers.values()):
            overall_status = "degraded"

        generated_at = utc_now()
        uptime_seconds = int(time.monotonic() - self.startup_monotonic)
        response = HealthResponse(
            status=overall_status,
            db=db_ok,
            brokers=brokers,
            instruments=instrument_status,
            kill_switch_active=False,
            uptime_seconds=uptime_seconds,
            generated_at=generated_at,
            checksum="",
        )

        payload_without_checksum = response.model_dump(mode="json")
        payload_without_checksum.pop("checksum", None)
        response.checksum = calculate_payload_checksum(payload_without_checksum)
        return response


health_service = HealthService()


def _get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    return db_url


def _parse_indicators(indicators: str | None) -> list[str] | None:
    if indicators is None:
        return None
    values = [item.strip() for item in indicators.split(",") if item.strip()]
    return values or None


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return system health and data freshness for Stage-1 client panel."""

    return health_service.build_health()


@router.get("/ohlcv/{instrument}")
def get_ohlcv(
    instrument: str,
    interval: str = Query(..., description="Candle interval, e.g. 1m, 5m, 1h"),
    start: datetime = Query(..., description="Start timestamp (ISO-8601, UTC)"),
    limit: int = Query(500, ge=1, le=10_000, description="Maximum number of rows to return"),
) -> dict[str, Any]:
    """Query historical OHLCV rows for an instrument."""

    db_url = _get_database_url()

    try:
        import psycopg

        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time, instrument, interval, open, high, low, close, volume, spread_avg, verified, source
                    FROM ohlcv
                    WHERE instrument = %s
                      AND interval = %s
                      AND time >= %s
                    ORDER BY time ASC
                    LIMIT %s
                    """,
                    (instrument, interval, start, limit),
                )
                rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query OHLCV: {exc}") from exc

    data = [
        {
            "time": row[0],
            "instrument": row[1],
            "interval": row[2],
            "open": float(row[3]),
            "high": float(row[4]),
            "low": float(row[5]),
            "close": float(row[6]),
            "volume": float(row[7]),
            "spread_avg": float(row[8]) if row[8] is not None else None,
            "verified": bool(row[9]),
            "source": row[10],
        }
        for row in rows
    ]

    return {
        "instrument": instrument,
        "interval": interval,
        "start": start,
        "limit": limit,
        "count": len(data),
        "data": data,
    }


@router.get("/features/metadata")
def get_feature_metadata() -> dict[str, Any]:
    """Return feature metadata registry."""

    db_url = _get_database_url()

    try:
        import psycopg

        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT namespace, feature_key, display_name, description, unit, params, provider
                    FROM feature_metadata
                    ORDER BY namespace ASC, feature_key ASC
                    """
                )
                rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query feature metadata: {exc}") from exc

    registry = [
        {
            "namespace": row[0],
            "feature_key": row[1],
            "display_name": row[2],
            "description": row[3],
            "unit": row[4],
            "params": row[5] if isinstance(row[5], dict) else {},
            "provider": row[6],
        }
        for row in rows
    ]

    return {
        "count": len(registry),
        "registry": registry,
    }


@router.get("/features/{instrument}")
def get_features(
    instrument: str,
    interval: str = Query(..., description="Feature interval, e.g. 1m, 5m, 1h"),
    start: datetime = Query(..., description="Start timestamp (ISO-8601, UTC)"),
    limit: int = Query(500, ge=1, le=10_000, description="Maximum number of rows to return"),
    indicators: str | None = Query(
        default=None,
        description="Optional comma-separated feature keys to filter",
    ),
) -> dict[str, Any]:
    """Query computed features for an instrument."""

    db_url = _get_database_url()
    indicator_values = _parse_indicators(indicators)

    try:
        import psycopg

        sql = """
            SELECT time, instrument, interval, namespace, feature_key, value
            FROM features
            WHERE instrument = %s
              AND interval = %s
              AND time >= %s
        """
        params: list[Any] = [instrument, interval, start]

        if indicator_values:
            sql += " AND feature_key = ANY(%s)"
            params.append(indicator_values)

        sql += " ORDER BY time ASC, namespace ASC, feature_key ASC LIMIT %s"
        params.append(limit)

        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query features: {exc}") from exc

    data = [
        {
            "time": row[0],
            "instrument": row[1],
            "interval": row[2],
            "namespace": row[3],
            "feature_key": row[4],
            "value": float(row[5]),
        }
        for row in rows
    ]

    return {
        "instrument": instrument,
        "interval": interval,
        "start": start,
        "limit": limit,
        "indicators": indicator_values,
        "count": len(data),
        "data": data,
    }
