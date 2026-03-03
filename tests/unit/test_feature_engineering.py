"""Tests for feature engineering pipeline (T-301)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.analysis.feature_engineering import (
    FeatureMatrix,
    FeatureVector,
    build_feature_matrix,
    build_feature_vector,
    compute_ohlcv_returns,
)
from src.data.fetcher_base import CandleRecord


def _make_candle(
    time: datetime,
    instrument: str = "EUR_USD",
    open_: float = 1.1000,
    high: float = 1.1050,
    low: float = 1.0950,
    close: float = 1.1020,
    volume: float = 1000.0,
) -> CandleRecord:
    return CandleRecord(
        time=time,
        instrument=instrument,
        interval="1h",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        spread_avg=None,
        verified=True,
        source="test",
    )


def _make_candle_series(
    n: int,
    instrument: str = "EUR_USD",
    base_price: float = 1.1000,
    step: float = 0.0010,
) -> list[CandleRecord]:
    """Generate n candles with incrementing prices for predictable returns."""
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(n):
        price = base_price + (i * step)
        candles.append(
            _make_candle(
                time=t0 + timedelta(hours=i),
                instrument=instrument,
                open_=price,
                high=price + 0.0020,
                low=price - 0.0020,
                close=price + 0.0005,
                volume=1000.0 + i * 10,
            )
        )
    return candles


def _make_indicator_features(
    candles: list[CandleRecord],
) -> dict[datetime, dict[str, float]]:
    """Generate synthetic indicator features aligned to candle timestamps."""
    features: dict[datetime, dict[str, float]] = {}
    for i, c in enumerate(candles):
        features[c.time] = {
            "rsi:period=14": 50.0 + i * 0.5,
            "macd:fast=12,slow=26,signal=9:line": 0.001 * i,
            "macd:fast=12,slow=26,signal=9:signal": 0.0005 * i,
            "macd:fast=12,slow=26,signal=9:histogram": 0.0005 * i,
            "obv:": 10000.0 + i * 100,
            "atr:period=14": 0.005 + i * 0.0001,
        }
    return features


def _make_token_sets(
    candles: list[CandleRecord],
    active_tokens_fn: None | (type[None]) = None,
) -> dict[datetime, frozenset[str]]:
    """Generate synthetic token sets aligned to candle timestamps."""
    all_tokens = ["EURUSD_RSI14_CL_BLW_30", "EURUSD_MACD12269_CL_ABV_0", "EURUSD_BB2020_CL_ABV_UPR"]
    result: dict[datetime, frozenset[str]] = {}
    for i, c in enumerate(candles):
        # Alternate which tokens are active
        active = frozenset(all_tokens[: (i % len(all_tokens)) + 1])
        result[c.time] = active
    return result


SELECTED_TOKENS = (
    "EURUSD_RSI14_CL_BLW_30",
    "EURUSD_MACD12269_CL_ABV_0",
    "EURUSD_BB2020_CL_ABV_UPR",
)


# --- compute_ohlcv_returns ---


class TestComputeOhlcvReturns:
    def test_basic_returns(self) -> None:
        candles = _make_candle_series(5)
        returns = compute_ohlcv_returns(candles)
        # First candle has no predecessor => no return
        assert candles[0].time not in returns
        # Second candle should have returns
        t1 = candles[1].time
        assert t1 in returns
        r = returns[t1]
        # close return: (close[1] - close[0]) / close[0]
        expected_close_ret = (candles[1].close - candles[0].close) / candles[0].close
        assert r["close_ret"] == pytest.approx(expected_close_ret, rel=1e-9)

    def test_all_ohlcv_fields_present(self) -> None:
        candles = _make_candle_series(3)
        returns = compute_ohlcv_returns(candles)
        t1 = candles[1].time
        for key in ("open_ret", "high_ret", "low_ret", "close_ret", "volume_ret"):
            assert key in returns[t1], f"Missing {key}"

    def test_empty_candles(self) -> None:
        returns = compute_ohlcv_returns([])
        assert returns == {}

    def test_single_candle(self) -> None:
        candles = _make_candle_series(1)
        returns = compute_ohlcv_returns(candles)
        assert returns == {}

    def test_zero_volume_candle(self) -> None:
        """Zero volume at t-1 should produce volume_ret = 0.0 (not division error)."""
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        t1 = datetime(2024, 1, 1, 1, tzinfo=UTC)
        candles = [
            _make_candle(time=t0, volume=0.0),
            _make_candle(time=t1, volume=100.0),
        ]
        returns = compute_ohlcv_returns(candles)
        assert t1 in returns
        # When previous volume is 0, volume_ret should be 0.0 (safe fallback)
        assert returns[t1]["volume_ret"] == 0.0


# --- build_feature_matrix ---


class TestBuildFeatureMatrix:
    def test_shape_and_type(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        lookback = 3
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
        )
        assert isinstance(matrix, FeatureMatrix)
        assert matrix.instrument == "EUR_USD"
        assert matrix.values.ndim == 2
        assert matrix.values.dtype == np.float64
        # Feature names should match columns
        assert len(matrix.feature_names) == matrix.values.shape[1]
        # Timestamps should match rows
        assert len(matrix.timestamps) == matrix.values.shape[0]

    def test_feature_name_categories(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=3,
            selected_tokens=SELECTED_TOKENS,
        )
        names = matrix.feature_names
        # Should contain OHLCV return features
        ohlcv_names = [n for n in names if n.startswith("ohlcv:")]
        assert len(ohlcv_names) > 0
        # Should contain indicator features
        ind_names = [n for n in names if n.startswith("ind:")]
        assert len(ind_names) > 0
        # Should contain token flag features
        tok_names = [n for n in names if n.startswith("tok:")]
        assert len(tok_names) == len(SELECTED_TOKENS)

    def test_ohlcv_return_columns_per_lookback(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        lookback = 4
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
        )
        ohlcv_names = [n for n in matrix.feature_names if n.startswith("ohlcv:")]
        # 5 OHLCV fields * lookback lags
        assert len(ohlcv_names) == 5 * lookback

    def test_indicator_columns_per_lookback(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        lookback = 3
        n_indicators = 6  # rsi, macd_line, macd_signal, macd_hist, obv, atr
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
        )
        ind_names = [n for n in matrix.feature_names if n.startswith("ind:")]
        assert len(ind_names) == n_indicators * lookback

    def test_token_flags_binary(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=3,
            selected_tokens=SELECTED_TOKENS,
        )
        tok_cols = [i for i, n in enumerate(matrix.feature_names) if n.startswith("tok:")]
        for col in tok_cols:
            values = matrix.values[:, col]
            assert all(v in (0.0, 1.0) for v in values), f"Non-binary value in token column {col}"

    def test_empty_candles_returns_empty_matrix(self) -> None:
        matrix = build_feature_matrix(
            candles=[],
            indicator_features={},
            token_sets={},
            lookback_periods=3,
            selected_tokens=SELECTED_TOKENS,
        )
        assert len(matrix.timestamps) == 0
        assert matrix.values.shape[0] == 0

    def test_insufficient_history(self) -> None:
        """With lookback=24 but only 5 candles, should produce fewer samples."""
        candles = _make_candle_series(5)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=24,
            selected_tokens=SELECTED_TOKENS,
        )
        # Not enough history for any sample with 24 lags
        assert matrix.values.shape[0] == 0

    def test_no_selected_tokens(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=3,
            selected_tokens=(),
        )
        tok_names = [n for n in matrix.feature_names if n.startswith("tok:")]
        assert len(tok_names) == 0
        # Should still have OHLCV + indicator features
        assert matrix.values.shape[1] > 0

    def test_values_not_nan(self) -> None:
        """All values in matrix should be finite (no NaN/Inf)."""
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=3,
            selected_tokens=SELECTED_TOKENS,
        )
        assert np.all(np.isfinite(matrix.values))


# --- build_feature_vector ---


class TestBuildFeatureVector:
    def test_shape_and_names(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        lookback = 3
        # Build matrix for comparison
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
        )
        # Build vector for the last timestamp
        target_time = candles[-1].time
        vector = build_feature_vector(
            target_time=target_time,
            candles=candles,
            indicator_features=indicator_features,
            token_set=token_sets.get(target_time, frozenset()),
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
            instrument="EUR_USD",
        )
        assert isinstance(vector, FeatureVector)
        assert vector.values.ndim == 1
        assert vector.feature_names == matrix.feature_names
        assert len(vector.values) == len(vector.feature_names)

    def test_matches_last_matrix_row(self) -> None:
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        token_sets = _make_token_sets(candles)
        lookback = 3
        matrix = build_feature_matrix(
            candles=candles,
            indicator_features=indicator_features,
            token_sets=token_sets,
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
        )
        target_time = matrix.timestamps[-1]
        vector = build_feature_vector(
            target_time=target_time,
            candles=candles,
            indicator_features=indicator_features,
            token_set=token_sets.get(target_time, frozenset()),
            lookback_periods=lookback,
            selected_tokens=SELECTED_TOKENS,
            instrument="EUR_USD",
        )
        np.testing.assert_array_almost_equal(vector.values, matrix.values[-1])

    def test_insufficient_history_raises(self) -> None:
        candles = _make_candle_series(3)
        indicator_features = _make_indicator_features(candles)
        with pytest.raises(ValueError, match="Insufficient history"):
            build_feature_vector(
                target_time=candles[-1].time,
                candles=candles,
                indicator_features=indicator_features,
                token_set=frozenset(),
                lookback_periods=24,
                selected_tokens=SELECTED_TOKENS,
                instrument="EUR_USD",
            )

    def test_unknown_target_time_raises(self) -> None:
        """Target time not in candle list should raise ValueError."""
        candles = _make_candle_series(30)
        indicator_features = _make_indicator_features(candles)
        unknown_time = datetime(2099, 1, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="Insufficient history"):
            build_feature_vector(
                target_time=unknown_time,
                candles=candles,
                indicator_features=indicator_features,
                token_set=frozenset(),
                lookback_periods=3,
                selected_tokens=SELECTED_TOKENS,
                instrument="EUR_USD",
            )


# --- FeatureMatrix / FeatureVector frozen ---


class TestFrozenDataclasses:
    def test_feature_matrix_frozen(self) -> None:
        matrix = FeatureMatrix(
            timestamps=(),
            feature_names=(),
            values=np.empty((0, 0)),
            instrument="EUR_USD",
        )
        with pytest.raises(AttributeError):
            matrix.instrument = "BTC_USD"  # type: ignore[misc]

    def test_feature_vector_frozen(self) -> None:
        vector = FeatureVector(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            feature_names=(),
            values=np.empty(0),
            instrument="EUR_USD",
        )
        with pytest.raises(AttributeError):
            vector.instrument = "BTC_USD"  # type: ignore[misc]
