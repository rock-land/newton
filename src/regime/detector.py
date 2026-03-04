"""Regime detection subsystem (T-305).

Detects market regime shifts per instrument using volatility and trend
strength indicators.  Operates independently per instrument with a
deterministic classification and confidence formula.

SPEC §5.8: Four regime labels based on vol_30d vs vol_median and ADX_14
vs 25.  Confidence = sqrt(clamp(d_vol) × clamp(d_adx)).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FOREX_ANNUALIZATION: float = math.sqrt(252)
"""Annualization factor for forex (trading days per year)."""

CRYPTO_ANNUALIZATION: float = math.sqrt(365)
"""Annualization factor for crypto (calendar days per year)."""

ADX_THRESHOLD: float = 25.0
"""ADX boundary between trending (> 25) and ranging (≤ 25)."""

ADX_PERIOD: int = 14
"""ADX look-back period."""

CONFIDENCE_HIGH_THRESHOLD: float = 0.5
"""Confidence ≥ 0.5 → HIGH band."""

CONFIDENCE_MEDIUM_THRESHOLD: float = 0.2
"""0.2 ≤ confidence < 0.5 → MEDIUM band."""

VOL_WINDOW: int = 30
"""Rolling window (bars) for realized volatility computation."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RegimeLabel(str, Enum):
    """Market regime classification per SPEC §5.8.2."""

    LOW_VOL_TRENDING = "LOW_VOL_TRENDING"
    LOW_VOL_RANGING = "LOW_VOL_RANGING"
    HIGH_VOL_TRENDING = "HIGH_VOL_TRENDING"
    HIGH_VOL_RANGING = "HIGH_VOL_RANGING"


class ConfidenceBand(str, Enum):
    """Regime confidence band per SPEC §5.8.3."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# Frozen dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeState:
    """Immutable snapshot of detected regime for one instrument at one time."""

    regime_label: RegimeLabel
    confidence: float
    confidence_band: ConfidenceBand
    vol_30d: float
    adx_14: float
    vol_median: float
    instrument: str
    time: datetime


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------


def compute_vol_30d(
    *,
    closes: np.ndarray,
    annualization_factor: float,
) -> float:
    """Compute 30-day annualized realized volatility (close-to-close).

    Uses log returns over the last ``VOL_WINDOW`` periods, then scales by
    the annualization factor (√252 forex, √365 crypto).

    Raises:
        ValueError: If fewer than 2 close prices are provided.
    """
    if len(closes) < 2:
        raise ValueError(
            f"compute_vol_30d: insufficient data ({len(closes)} closes, need ≥2)"
        )

    if np.any(closes <= 0):
        raise ValueError(
            "compute_vol_30d: non-positive price detected in closes (log undefined)"
        )

    # Use up to VOL_WINDOW+1 prices to get VOL_WINDOW returns
    window = closes[-(VOL_WINDOW + 1):]
    log_returns = np.diff(np.log(window))

    if len(log_returns) == 0:
        return 0.0

    std = float(np.std(log_returns, ddof=1)) if len(log_returns) > 1 else 0.0
    return std * annualization_factor


def compute_adx_14(
    *,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> float:
    """Compute 14-period Average Directional Index.

    Tries TA-Lib first; falls back to pure Python (DEC-006).

    Raises:
        ValueError: If fewer than 2×ADX_PERIOD (28) bars are provided.
    """
    min_bars = 2 * ADX_PERIOD
    if len(closes) < min_bars:
        raise ValueError(
            f"compute_adx_14: insufficient data ({len(closes)} bars, need ≥{min_bars})"
        )

    try:
        import talib

        result = talib.ADX(highs, lows, closes, timeperiod=ADX_PERIOD)
        # TA-Lib returns NaN for initial bars; take the last valid value
        valid = result[~np.isnan(result)]
        if len(valid) == 0:
            return 0.0
        return float(valid[-1])
    except ImportError:
        return _compute_adx_pure_python(highs, lows, closes, ADX_PERIOD)


def compute_vol_median(vol_30d_history: Sequence[float]) -> float:
    """Compute median of historical vol_30d values (2-year rolling window).

    Raises:
        ValueError: If the history is empty.
    """
    if len(vol_30d_history) == 0:
        raise ValueError("compute_vol_median: empty vol_30d history")
    return float(np.median(vol_30d_history))


def classify_regime(
    *,
    vol_30d: float,
    adx_14: float,
    vol_median: float,
) -> RegimeLabel:
    """Classify regime into one of four labels per SPEC §5.8.2.

    - vol_30d < vol_median → LOW_VOL; vol_30d ≥ vol_median → HIGH_VOL
    - ADX_14 > 25 → TRENDING; ADX_14 ≤ 25 → RANGING
    """
    high_vol = vol_30d >= vol_median
    trending = adx_14 > ADX_THRESHOLD

    if high_vol:
        return RegimeLabel.HIGH_VOL_TRENDING if trending else RegimeLabel.HIGH_VOL_RANGING
    return RegimeLabel.LOW_VOL_TRENDING if trending else RegimeLabel.LOW_VOL_RANGING


def compute_confidence(
    *,
    vol_30d: float,
    adx_14: float,
    vol_median: float,
) -> tuple[float, ConfidenceBand]:
    """Deterministic confidence per SPEC §5.8.3.

    Returns (confidence_value, confidence_band).
    Guards against vol_median == 0 (returns 0.0 / LOW).
    """
    if vol_median == 0.0:
        return 0.0, ConfidenceBand.LOW

    d_vol = abs(vol_30d - vol_median) / vol_median
    d_adx = abs(adx_14 - ADX_THRESHOLD) / ADX_THRESHOLD

    d_vol_clamped = min(d_vol, 1.0)
    d_adx_clamped = min(d_adx, 1.0)

    confidence = math.sqrt(d_vol_clamped * d_adx_clamped)

    if confidence >= CONFIDENCE_HIGH_THRESHOLD:
        band = ConfidenceBand.HIGH
    elif confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
        band = ConfidenceBand.MEDIUM
    else:
        band = ConfidenceBand.LOW

    return confidence, band


def detect_regime(
    *,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    vol_median: float,
    instrument: str,
    time: datetime,
    annualization_factor: float,
) -> RegimeState:
    """Main entry point: compute regime state from OHLCV candle data.

    Composes vol_30d, ADX_14, classification, and confidence into a
    single ``RegimeState`` snapshot.
    """
    vol_30d = compute_vol_30d(
        closes=closes,
        annualization_factor=annualization_factor,
    )
    adx_14 = compute_adx_14(highs=highs, lows=lows, closes=closes)
    label = classify_regime(vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_median)
    confidence, band = compute_confidence(
        vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_median,
    )

    logger.info(
        "Regime detected for %s: %s (confidence=%.3f/%s, vol_30d=%.4f, adx_14=%.2f)",
        instrument,
        label.value,
        confidence,
        band.value,
        vol_30d,
        adx_14,
    )

    return RegimeState(
        regime_label=label,
        confidence=confidence,
        confidence_band=band,
        vol_30d=vol_30d,
        adx_14=adx_14,
        vol_median=vol_median,
        instrument=instrument,
        time=time,
    )


# ---------------------------------------------------------------------------
# Pure Python ADX fallback (Wilder's smoothing)
# ---------------------------------------------------------------------------


def _compute_adx_pure_python(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int,
) -> float:
    """Pure Python ADX implementation using Wilder's smoothing.

    Steps:
    1. Compute True Range (TR), +DM, -DM per bar.
    2. Apply Wilder's EMA (period) to TR, +DM, -DM.
    3. Compute +DI = smoothed(+DM) / smoothed(TR) × 100.
    4. Compute -DI = smoothed(-DM) / smoothed(TR) × 100.
    5. DX = |+DI − -DI| / (+DI + -DI) × 100.
    6. ADX = Wilder's EMA of DX (period).
    7. Return last ADX value.
    """
    n = len(closes)

    # Step 1: TR, +DM, -DM
    tr = np.empty(n - 1)
    plus_dm = np.empty(n - 1)
    minus_dm = np.empty(n - 1)

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        tr[i - 1] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        plus_dm[i - 1] = high_diff if (high_diff > low_diff and high_diff > 0) else 0.0
        minus_dm[i - 1] = low_diff if (low_diff > high_diff and low_diff > 0) else 0.0

    # Step 2: Wilder's smoothing (SMA for first period, then EMA)
    def wilder_smooth(values: np.ndarray, p: int) -> np.ndarray:
        result = np.empty(len(values) - p + 1)
        result[0] = np.sum(values[:p])
        for j in range(1, len(result)):
            result[j] = result[j - 1] - result[j - 1] / p + values[p + j - 1]
        return result

    smoothed_tr = wilder_smooth(tr, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)

    # Step 3–4: +DI, -DI
    m = len(smoothed_tr)
    plus_di = np.zeros(m)
    minus_di = np.zeros(m)
    for i in range(m):
        if smoothed_tr[i] != 0:
            plus_di[i] = (smoothed_plus_dm[i] / smoothed_tr[i]) * 100.0
            minus_di[i] = (smoothed_minus_dm[i] / smoothed_tr[i]) * 100.0

    # Step 5: DX
    dx = np.zeros(m)
    for i in range(m):
        denom = plus_di[i] + minus_di[i]
        if denom != 0:
            dx[i] = (abs(plus_di[i] - minus_di[i]) / denom) * 100.0

    # Step 6: ADX = Wilder's EMA of DX
    if len(dx) < period:
        return 0.0

    adx_values = wilder_smooth(dx, period)
    if len(adx_values) == 0:
        return 0.0

    # Convert from cumulative Wilder sum to average
    return float(adx_values[-1] / period)
