"""Feature engineering pipeline for ML training and inference (SPEC §5.6).

Builds feature vectors from:
- OHLCV period-over-period returns (not raw prices)
- Technical indicator features from the feature store
- Token presence flags (binary 0/1)

Each sample at timestamp T uses a lookback window of N prior periods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from src.data.fetcher_base import CandleRecord

_OHLCV_RETURN_FIELDS = ("open_ret", "high_ret", "low_ret", "close_ret", "volume_ret")


@dataclass(frozen=True)
class FeatureMatrix:
    """Training-ready feature matrix with named columns."""

    timestamps: tuple[datetime, ...]
    feature_names: tuple[str, ...]
    values: np.ndarray  # shape (n_samples, n_features), float64
    instrument: str


@dataclass(frozen=True)
class FeatureVector:
    """Single-row feature vector for real-time inference."""

    timestamp: datetime
    feature_names: tuple[str, ...]
    values: np.ndarray  # shape (n_features,), float64
    instrument: str


def compute_ohlcv_returns(
    candles: list[CandleRecord],
) -> dict[datetime, dict[str, float]]:
    """Compute period-over-period returns for OHLCV fields.

    Returns a dict keyed by timestamp. The first candle has no predecessor
    and is excluded from the output.
    """
    if len(candles) < 2:
        return {}

    sorted_candles = sorted(candles, key=lambda c: c.time)
    returns: dict[datetime, dict[str, float]] = {}

    for i in range(1, len(sorted_candles)):
        prev = sorted_candles[i - 1]
        curr = sorted_candles[i]

        def _safe_ret(curr_val: float, prev_val: float) -> float:
            if prev_val == 0.0:
                return 0.0
            return (curr_val - prev_val) / prev_val

        returns[curr.time] = {
            "open_ret": _safe_ret(curr.open, prev.open),
            "high_ret": _safe_ret(curr.high, prev.high),
            "low_ret": _safe_ret(curr.low, prev.low),
            "close_ret": _safe_ret(curr.close, prev.close),
            "volume_ret": _safe_ret(curr.volume, prev.volume),
        }

    return returns


def _build_feature_names(
    lookback_periods: int,
    indicator_keys: tuple[str, ...],
    selected_tokens: tuple[str, ...],
) -> tuple[str, ...]:
    """Build ordered feature name list."""
    names: list[str] = []

    # OHLCV returns: lag=1 is most recent, lag=N is oldest
    for lag in range(1, lookback_periods + 1):
        for field in _OHLCV_RETURN_FIELDS:
            names.append(f"ohlcv:{field}:lag={lag}")

    # Indicator features: same lag convention
    for lag in range(1, lookback_periods + 1):
        for key in indicator_keys:
            names.append(f"ind:{key}:lag={lag}")

    # Token presence flags (current period only)
    for token in selected_tokens:
        names.append(f"tok:{token}")

    return tuple(names)


def _extract_row(
    target_time: datetime,
    ohlcv_returns: dict[datetime, dict[str, float]],
    indicator_features: dict[datetime, dict[str, float]],
    token_set: frozenset[str],
    lookback_periods: int,
    sorted_times: list[datetime],
    time_index: dict[datetime, int],
    indicator_keys: tuple[str, ...],
    selected_tokens: tuple[str, ...],
) -> list[float] | None:
    """Extract a single feature row for a target timestamp.

    Returns None if insufficient history is available.
    """
    idx = time_index.get(target_time)
    if idx is None:
        return None

    # Need lookback_periods prior timestamps (with returns)
    if idx < lookback_periods:
        return None

    row: list[float] = []

    _NAN = float("nan")

    # OHLCV returns: lag 1 = most recent prior, lag N = oldest
    for lag in range(1, lookback_periods + 1):
        t = sorted_times[idx - lag]
        ret = ohlcv_returns.get(t, {})
        for field in _OHLCV_RETURN_FIELDS:
            row.append(ret.get(field, _NAN))

    # Indicator features: same lag convention
    for lag in range(1, lookback_periods + 1):
        t = sorted_times[idx - lag]
        ind = indicator_features.get(t, {})
        for key in indicator_keys:
            row.append(ind.get(key, _NAN))

    # Token flags (current period)
    for token in selected_tokens:
        row.append(1.0 if token in token_set else 0.0)

    return row


def build_feature_matrix(
    *,
    candles: list[CandleRecord],
    indicator_features: dict[datetime, dict[str, float]],
    token_sets: dict[datetime, frozenset[str]],
    lookback_periods: int,
    selected_tokens: tuple[str, ...],
) -> FeatureMatrix:
    """Build a training feature matrix from historical data.

    Each row corresponds to one timestamp. Features include lagged OHLCV
    returns, lagged indicator values, and current-period token presence flags.
    """
    if not candles:
        indicator_keys = _sorted_indicator_keys(indicator_features)
        feature_names = _build_feature_names(lookback_periods, indicator_keys, selected_tokens)
        return FeatureMatrix(
            timestamps=(),
            feature_names=feature_names,
            values=np.empty((0, len(feature_names)), dtype=np.float64),
            instrument="",
        )

    instrument = candles[0].instrument
    sorted_candles = sorted(candles, key=lambda c: c.time)
    ohlcv_returns = compute_ohlcv_returns(sorted_candles)
    indicator_keys = _sorted_indicator_keys(indicator_features)
    feature_names = _build_feature_names(lookback_periods, indicator_keys, selected_tokens)

    # Build time index from candles that have returns (exclude first candle)
    sorted_times = [c.time for c in sorted_candles]
    time_index = {t: i for i, t in enumerate(sorted_times)}

    timestamps: list[datetime] = []
    rows: list[list[float]] = []

    for i, t in enumerate(sorted_times):
        if i < lookback_periods:
            continue
        token_set = token_sets.get(t, frozenset())
        row = _extract_row(
            target_time=t,
            ohlcv_returns=ohlcv_returns,
            indicator_features=indicator_features,
            token_set=token_set,
            lookback_periods=lookback_periods,
            sorted_times=sorted_times,
            time_index=time_index,
            indicator_keys=indicator_keys,
            selected_tokens=selected_tokens,
        )
        if row is not None:
            timestamps.append(t)
            rows.append(row)

    if not rows:
        return FeatureMatrix(
            timestamps=(),
            feature_names=feature_names,
            values=np.empty((0, len(feature_names)), dtype=np.float64),
            instrument=instrument,
        )

    return FeatureMatrix(
        timestamps=tuple(timestamps),
        feature_names=feature_names,
        values=np.array(rows, dtype=np.float64),
        instrument=instrument,
    )


def build_feature_vector(
    *,
    target_time: datetime,
    candles: list[CandleRecord],
    indicator_features: dict[datetime, dict[str, float]],
    token_set: frozenset[str],
    lookback_periods: int,
    selected_tokens: tuple[str, ...],
    instrument: str,
) -> FeatureVector:
    """Build a single feature vector for real-time inference.

    Raises ValueError if there is insufficient history for the lookback window.
    """
    sorted_candles = sorted(candles, key=lambda c: c.time)
    ohlcv_returns = compute_ohlcv_returns(sorted_candles)
    indicator_keys = _sorted_indicator_keys(indicator_features)
    feature_names = _build_feature_names(lookback_periods, indicator_keys, selected_tokens)

    sorted_times = [c.time for c in sorted_candles]
    time_index = {t: i for i, t in enumerate(sorted_times)}

    row = _extract_row(
        target_time=target_time,
        ohlcv_returns=ohlcv_returns,
        indicator_features=indicator_features,
        token_set=token_set,
        lookback_periods=lookback_periods,
        sorted_times=sorted_times,
        time_index=time_index,
        indicator_keys=indicator_keys,
        selected_tokens=selected_tokens,
    )

    if row is None:
        msg = f"Insufficient history for lookback={lookback_periods} at {target_time}"
        raise ValueError(msg)

    return FeatureVector(
        timestamp=target_time,
        feature_names=feature_names,
        values=np.array(row, dtype=np.float64),
        instrument=instrument,
    )


def _sorted_indicator_keys(
    indicator_features: dict[datetime, dict[str, float]],
) -> tuple[str, ...]:
    """Extract sorted unique indicator keys from feature dicts."""
    keys: set[str] = set()
    for features in indicator_features.values():
        keys.update(features.keys())
    return tuple(sorted(keys))
