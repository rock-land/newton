"""Regime detection API endpoints (T-404).

Computes current market regime per instrument from OHLCV data.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException

from src.api.schemas import RegimeResponse, utc_now
from src.regime.detector import (
    CRYPTO_ANNUALIZATION,
    FOREX_ANNUALIZATION,
    VOL_WINDOW,
    compute_adx_14,
    compute_confidence,
    compute_vol_30d,
    compute_vol_median,
    classify_regime,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["regime"])

_SUPPORTED_INSTRUMENTS: dict[str, float] = {
    "EUR_USD": FOREX_ANNUALIZATION,
    "BTC_USD": CRYPTO_ANNUALIZATION,
}

_MIN_BARS_VOL = VOL_WINDOW + 1  # 31
_MIN_BARS_ADX = 28  # 2 * ADX_PERIOD


@router.get("/regime/{instrument}", response_model=RegimeResponse)
def get_regime(instrument: str) -> RegimeResponse:
    """Return current regime state for an instrument.

    Queries OHLCV daily bars from the database, computes volatility,
    ADX, and classifies the regime.  Returns a graceful fallback when
    the database is unavailable or data is insufficient.
    """
    if instrument not in _SUPPORTED_INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {instrument}")

    annualization = _SUPPORTED_INSTRUMENTS[instrument]
    now = utc_now()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return _unknown_regime(instrument, now, "DATABASE_URL not configured")

    try:
        import psycopg

        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT high, low, close
                    FROM ohlcv
                    WHERE instrument = %s AND interval = %s AND verified = TRUE
                    ORDER BY time DESC
                    LIMIT %s
                    """,
                    (instrument, "1h", 12000),
                )
                rows = cur.fetchall()
    except Exception:
        logger.exception("Regime: failed to query OHLCV for %s", instrument)
        return _unknown_regime(instrument, now, "Database query failed")

    if len(rows) < max(_MIN_BARS_VOL, _MIN_BARS_ADX):
        return _unknown_regime(
            instrument,
            now,
            f"Insufficient data ({len(rows)} bars, need {max(_MIN_BARS_VOL, _MIN_BARS_ADX)})",
        )

    # Rows are DESC — reverse to chronological ASC
    rows.reverse()
    highs = np.array([float(r[0]) for r in rows])
    lows = np.array([float(r[1]) for r in rows])
    closes = np.array([float(r[2]) for r in rows])

    vol_30d = compute_vol_30d(closes=closes, annualization_factor=annualization)
    adx_14 = compute_adx_14(highs=highs, lows=lows, closes=closes)

    # Compute vol_median from rolling vol_30d over available history
    vol_history = _rolling_vol_30d(closes, annualization)
    vol_median = compute_vol_median(vol_history) if vol_history else vol_30d

    label = classify_regime(vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_median)
    confidence, band = compute_confidence(vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_median)

    return RegimeResponse(
        instrument=instrument,
        regime_label=label.value,
        confidence=round(confidence, 4),
        confidence_band=band.value,
        vol_30d=round(vol_30d, 6),
        adx_14=round(adx_14, 2),
        vol_median=round(vol_median, 6),
        computed_at=now,
    )


def _unknown_regime(instrument: str, now: Any, error: str) -> RegimeResponse:
    """Return a fallback regime response when computation is not possible."""
    return RegimeResponse(
        instrument=instrument,
        regime_label="UNKNOWN",
        confidence=0.0,
        confidence_band="LOW",
        vol_30d=0.0,
        adx_14=0.0,
        vol_median=0.0,
        computed_at=now,
        error=error,
    )


def _rolling_vol_30d(closes: np.ndarray, annualization: float) -> list[float]:
    """Compute rolling vol_30d values from close prices for vol_median estimation."""
    vols: list[float] = []
    window = VOL_WINDOW + 1
    step = 20  # Compute every ~month (20 trading days)
    for end in range(window, len(closes) + 1, step):
        segment = closes[:end]
        try:
            v = compute_vol_30d(closes=segment, annualization_factor=annualization)
            if not math.isnan(v):
                vols.append(v)
        except ValueError:
            continue
    return vols
