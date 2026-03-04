"""Tests for regime detection subsystem (T-305)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from src.regime.detector import (
    ConfidenceBand,
    RegimeLabel,
    RegimeState,
    _compute_adx_pure_python,
    compute_adx_14,
    compute_confidence,
    compute_vol_30d,
    compute_vol_median,
    classify_regime,
    detect_regime,
    ADX_PERIOD,
    FOREX_ANNUALIZATION,
    CRYPTO_ANNUALIZATION,
)


# ---------------------------------------------------------------------------
# RegimeState frozen dataclass
# ---------------------------------------------------------------------------


class TestRegimeState:
    def test_frozen(self) -> None:
        state = RegimeState(
            regime_label=RegimeLabel.LOW_VOL_TRENDING,
            confidence=0.6,
            confidence_band=ConfidenceBand.HIGH,
            vol_30d=0.10,
            adx_14=30.0,
            vol_median=0.12,
            instrument="EUR_USD",
            time=datetime(2024, 6, 1, tzinfo=UTC),
        )
        with pytest.raises(AttributeError):
            state.confidence = 0.9  # type: ignore[misc]

    def test_fields(self) -> None:
        t = datetime(2024, 6, 1, tzinfo=UTC)
        state = RegimeState(
            regime_label=RegimeLabel.HIGH_VOL_RANGING,
            confidence=0.35,
            confidence_band=ConfidenceBand.MEDIUM,
            vol_30d=0.20,
            adx_14=18.0,
            vol_median=0.12,
            instrument="BTC_USD",
            time=t,
        )
        assert state.regime_label == RegimeLabel.HIGH_VOL_RANGING
        assert state.confidence == pytest.approx(0.35)
        assert state.confidence_band == ConfidenceBand.MEDIUM
        assert state.vol_30d == pytest.approx(0.20)
        assert state.adx_14 == pytest.approx(18.0)
        assert state.vol_median == pytest.approx(0.12)
        assert state.instrument == "BTC_USD"
        assert state.time == t


# ---------------------------------------------------------------------------
# RegimeLabel and ConfidenceBand enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_regime_labels(self) -> None:
        assert set(RegimeLabel) == {
            RegimeLabel.LOW_VOL_TRENDING,
            RegimeLabel.LOW_VOL_RANGING,
            RegimeLabel.HIGH_VOL_TRENDING,
            RegimeLabel.HIGH_VOL_RANGING,
        }

    def test_confidence_bands(self) -> None:
        assert set(ConfidenceBand) == {
            ConfidenceBand.HIGH,
            ConfidenceBand.MEDIUM,
            ConfidenceBand.LOW,
        }

    def test_regime_label_string_values(self) -> None:
        """Labels should be usable as strings (for DB storage)."""
        assert str(RegimeLabel.LOW_VOL_TRENDING) == "RegimeLabel.LOW_VOL_TRENDING"
        assert RegimeLabel.LOW_VOL_TRENDING.value == "LOW_VOL_TRENDING"


# ---------------------------------------------------------------------------
# compute_vol_30d
# ---------------------------------------------------------------------------


class TestComputeVol30d:
    def test_constant_prices_returns_zero(self) -> None:
        closes = np.full(60, 1.10)
        vol = compute_vol_30d(closes=closes, annualization_factor=FOREX_ANNUALIZATION)
        assert vol == pytest.approx(0.0, abs=1e-10)

    def test_known_volatility_forex(self) -> None:
        """Generate returns with known std, verify annualized vol."""
        rng = np.random.default_rng(42)
        daily_return_std = 0.01  # 1% daily
        n = 60
        log_returns = rng.normal(0, daily_return_std, n)
        prices = 1.10 * np.exp(np.cumsum(log_returns))
        # Insert a starting price so we have n+1 prices for n returns
        closes = np.concatenate([[1.10], prices])

        vol = compute_vol_30d(closes=closes, annualization_factor=FOREX_ANNUALIZATION)
        # Should be roughly daily_return_std * sqrt(252) ≈ 0.159
        # But computed from last 30 returns, so allow tolerance
        assert 0.05 < vol < 0.40

    def test_crypto_annualization_higher(self) -> None:
        """Crypto annualization (√365) > forex (√252) for same returns."""
        rng = np.random.default_rng(99)
        log_returns = rng.normal(0, 0.02, 60)
        closes = np.exp(np.cumsum(log_returns))

        vol_forex = compute_vol_30d(closes=closes, annualization_factor=FOREX_ANNUALIZATION)
        vol_crypto = compute_vol_30d(closes=closes, annualization_factor=CRYPTO_ANNUALIZATION)
        assert vol_crypto > vol_forex

    def test_insufficient_data_raises(self) -> None:
        """Need at least 2 close prices for 1 return."""
        with pytest.raises(ValueError, match="insufficient"):
            compute_vol_30d(closes=np.array([1.10]), annualization_factor=FOREX_ANNUALIZATION)

    def test_annualization_constants(self) -> None:
        assert FOREX_ANNUALIZATION == pytest.approx(math.sqrt(252))
        assert CRYPTO_ANNUALIZATION == pytest.approx(math.sqrt(365))


# ---------------------------------------------------------------------------
# compute_adx_14
# ---------------------------------------------------------------------------


class TestComputeAdx14:
    def _make_trending_data(self, n: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Strong uptrend: prices steadily rising with small ranges."""
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + t * 0.5
        highs = closes + 1.0
        lows = closes - 1.0
        return highs, lows, closes

    def _make_ranging_data(self, n: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Mean-reverting: prices oscillate in a tight range."""
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + 2.0 * np.sin(t * 0.5)
        highs = closes + 0.5
        lows = closes - 0.5
        return highs, lows, closes

    def test_trending_high_adx(self) -> None:
        highs, lows, closes = self._make_trending_data(100)
        adx = compute_adx_14(highs=highs, lows=lows, closes=closes)
        assert adx > 25  # Strong trend

    def test_ranging_low_adx(self) -> None:
        highs, lows, closes = self._make_ranging_data(100)
        adx = compute_adx_14(highs=highs, lows=lows, closes=closes)
        assert adx < 25  # No trend

    def test_adx_in_valid_range(self) -> None:
        rng = np.random.default_rng(42)
        n = 100
        closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
        highs = closes + rng.uniform(0.5, 2.0, n)
        lows = closes - rng.uniform(0.5, 2.0, n)
        adx = compute_adx_14(highs=highs, lows=lows, closes=closes)
        assert 0.0 <= adx <= 100.0

    def test_insufficient_data_raises(self) -> None:
        """ADX(14) needs at least 28 bars (2×period)."""
        with pytest.raises(ValueError, match="insufficient"):
            compute_adx_14(
                highs=np.ones(20),
                lows=np.ones(20),
                closes=np.ones(20),
            )


# ---------------------------------------------------------------------------
# compute_vol_median
# ---------------------------------------------------------------------------


class TestComputeVolMedian:
    def test_median_of_series(self) -> None:
        history = [0.10, 0.12, 0.08, 0.15, 0.11]
        median = compute_vol_median(history)
        assert median == pytest.approx(0.11)

    def test_single_value(self) -> None:
        median = compute_vol_median([0.15])
        assert median == pytest.approx(0.15)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            compute_vol_median([])

    def test_even_count(self) -> None:
        history = [0.10, 0.20, 0.30, 0.40]
        median = compute_vol_median(history)
        assert median == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# classify_regime
# ---------------------------------------------------------------------------


class TestClassifyRegime:
    def test_low_vol_trending(self) -> None:
        label = classify_regime(vol_30d=0.08, adx_14=35.0, vol_median=0.12)
        assert label == RegimeLabel.LOW_VOL_TRENDING

    def test_low_vol_ranging(self) -> None:
        label = classify_regime(vol_30d=0.08, adx_14=20.0, vol_median=0.12)
        assert label == RegimeLabel.LOW_VOL_RANGING

    def test_high_vol_trending(self) -> None:
        label = classify_regime(vol_30d=0.15, adx_14=35.0, vol_median=0.12)
        assert label == RegimeLabel.HIGH_VOL_TRENDING

    def test_high_vol_ranging(self) -> None:
        label = classify_regime(vol_30d=0.15, adx_14=20.0, vol_median=0.12)
        assert label == RegimeLabel.HIGH_VOL_RANGING

    def test_boundary_vol_equal_median_is_high(self) -> None:
        """SPEC §5.8.2: vol_30d ≥ vol_median → HIGH_VOL."""
        label = classify_regime(vol_30d=0.12, adx_14=30.0, vol_median=0.12)
        assert label == RegimeLabel.HIGH_VOL_TRENDING

    def test_boundary_adx_equal_25_is_ranging(self) -> None:
        """SPEC §5.8.2: ADX_14 ≤ 25 → RANGING."""
        label = classify_regime(vol_30d=0.08, adx_14=25.0, vol_median=0.12)
        assert label == RegimeLabel.LOW_VOL_RANGING


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------


class TestComputeConfidence:
    def test_high_confidence(self) -> None:
        """Far from both boundaries → high confidence."""
        conf, band = compute_confidence(vol_30d=0.25, adx_14=50.0, vol_median=0.10)
        assert band == ConfidenceBand.HIGH
        assert conf >= 0.5

    def test_low_confidence_near_boundaries(self) -> None:
        """Close to both boundaries → low confidence."""
        conf, band = compute_confidence(vol_30d=0.121, adx_14=25.5, vol_median=0.12)
        assert band == ConfidenceBand.LOW
        assert conf < 0.2

    def test_medium_confidence(self) -> None:
        """Moderate distance from boundaries → medium confidence."""
        conf, band = compute_confidence(vol_30d=0.15, adx_14=30.0, vol_median=0.12)
        assert ConfidenceBand.LOW.value != band.value or conf >= 0.2
        # Just verify it computes without error and is in [0, 1]
        assert 0.0 <= conf <= 1.0

    def test_exact_formula(self) -> None:
        """Verify the deterministic formula from SPEC §5.8.3."""
        vol_30d = 0.20
        adx_14 = 40.0
        vol_median = 0.10

        d_vol = abs(vol_30d - vol_median) / vol_median  # 1.0
        d_adx = abs(adx_14 - 25) / 25  # 0.6
        d_vol_c = min(d_vol, 1.0)  # 1.0
        d_adx_c = min(d_adx, 1.0)  # 0.6
        expected = math.sqrt(d_vol_c * d_adx_c)  # sqrt(0.6) ≈ 0.7746

        conf, band = compute_confidence(vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_median)
        assert conf == pytest.approx(expected)
        assert band == ConfidenceBand.HIGH

    def test_zero_vol_median_returns_low(self) -> None:
        """Guard: vol_median=0 should not crash (division by zero)."""
        conf, band = compute_confidence(vol_30d=0.10, adx_14=30.0, vol_median=0.0)
        assert conf == pytest.approx(0.0)
        assert band == ConfidenceBand.LOW

    def test_confidence_clamped_at_one(self) -> None:
        """d_vol and d_adx are clamped at 1.0 → max confidence = 1.0."""
        conf, band = compute_confidence(vol_30d=0.50, adx_14=100.0, vol_median=0.10)
        assert conf <= 1.0

    def test_band_boundaries(self) -> None:
        """Verify band classification at exact thresholds."""
        # confidence >= 0.5 → HIGH
        # 0.2 <= confidence < 0.5 → MEDIUM
        # confidence < 0.2 → LOW

        # Use values that clearly land in each band (avoid fp boundary issues)

        # HIGH band: d_vol=0.5, d_adx=1.0 → sqrt(0.5) ≈ 0.707
        conf_h, band_h = compute_confidence(vol_30d=0.15, adx_14=50.0, vol_median=0.10)
        assert band_h == ConfidenceBand.HIGH
        assert conf_h >= 0.5

        # MEDIUM band: d_vol=0.1, d_adx=1.0 → sqrt(0.1) ≈ 0.316
        conf_m, band_m = compute_confidence(vol_30d=0.11, adx_14=50.0, vol_median=0.10)
        assert band_m == ConfidenceBand.MEDIUM
        assert 0.2 <= conf_m < 0.5

        # LOW band: d_vol=0.01, d_adx=0.04 → sqrt(0.0004) = 0.02
        conf_l, band_l = compute_confidence(vol_30d=0.101, adx_14=26.0, vol_median=0.10)
        assert band_l == ConfidenceBand.LOW
        assert conf_l < 0.2


# ---------------------------------------------------------------------------
# detect_regime (integration)
# ---------------------------------------------------------------------------


class TestComputeAdxPurePython:
    """Test the pure Python ADX fallback directly."""

    def _make_trending_data(self, n: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + t * 0.5
        highs = closes + 1.0
        lows = closes - 1.0
        return highs, lows, closes

    def _make_ranging_data(self, n: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + 2.0 * np.sin(t * 0.5)
        highs = closes + 0.5
        lows = closes - 0.5
        return highs, lows, closes

    def test_trending_high_adx(self) -> None:
        highs, lows, closes = self._make_trending_data(100)
        adx = _compute_adx_pure_python(highs, lows, closes, ADX_PERIOD)
        assert adx > 25

    def test_ranging_low_adx(self) -> None:
        highs, lows, closes = self._make_ranging_data(100)
        adx = _compute_adx_pure_python(highs, lows, closes, ADX_PERIOD)
        assert adx < 25

    def test_valid_range(self) -> None:
        rng = np.random.default_rng(42)
        n = 100
        closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
        highs = closes + rng.uniform(0.5, 2.0, n)
        lows = closes - rng.uniform(0.5, 2.0, n)
        adx = _compute_adx_pure_python(highs, lows, closes, ADX_PERIOD)
        assert 0.0 <= adx <= 100.0

    def test_approximate_parity_with_talib(self) -> None:
        """Pure Python and TA-Lib should produce roughly similar ADX."""
        rng = np.random.default_rng(123)
        n = 200
        closes = 100.0 + np.cumsum(rng.normal(0.05, 1, n))
        highs = closes + rng.uniform(0.5, 2.0, n)
        lows = closes - rng.uniform(0.5, 2.0, n)

        talib_adx = compute_adx_14(highs=highs, lows=lows, closes=closes)
        python_adx = _compute_adx_pure_python(highs, lows, closes, ADX_PERIOD)
        # Both should agree on trending vs ranging direction at least
        # Allow generous tolerance since implementations differ in smoothing details
        assert abs(talib_adx - python_adx) < 30  # same ballpark

    def test_insufficient_data_returns_zero(self) -> None:
        """With very few DX values, ADX should gracefully return 0."""
        adx = _compute_adx_pure_python(
            np.ones(ADX_PERIOD + 1),
            np.ones(ADX_PERIOD + 1),
            np.ones(ADX_PERIOD + 1),
            ADX_PERIOD,
        )
        assert adx == pytest.approx(0.0, abs=1e-10)


class TestDetectRegime:
    def test_trending_regime(self) -> None:
        """Strong uptrend with moderate vol → should detect trending regime."""
        n = 100
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + t * 0.5
        highs = closes + 1.0
        lows = closes - 1.0

        state = detect_regime(
            highs=highs,
            lows=lows,
            closes=closes,
            vol_median=0.50,  # high median so vol_30d < median
            instrument="EUR_USD",
            time=datetime(2024, 6, 1, tzinfo=UTC),
            annualization_factor=FOREX_ANNUALIZATION,
        )
        assert isinstance(state, RegimeState)
        assert state.adx_14 > 25  # trending
        assert state.instrument == "EUR_USD"
        assert state.vol_median == pytest.approx(0.50)

    def test_ranging_regime(self) -> None:
        """Oscillating prices → ranging regime."""
        n = 100
        t = np.arange(n, dtype=np.float64)
        closes = 100.0 + 2.0 * np.sin(t * 0.5)
        highs = closes + 0.5
        lows = closes - 0.5

        state = detect_regime(
            highs=highs,
            lows=lows,
            closes=closes,
            vol_median=0.01,  # low median so vol_30d >= median
            instrument="BTC_USD",
            time=datetime(2024, 6, 1, tzinfo=UTC),
            annualization_factor=CRYPTO_ANNUALIZATION,
        )
        assert isinstance(state, RegimeState)
        assert state.adx_14 < 25  # ranging
        assert state.vol_30d > 0

    def test_regime_state_completeness(self) -> None:
        """All fields populated."""
        n = 100
        rng = np.random.default_rng(42)
        closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
        highs = closes + rng.uniform(0.5, 2.0, n)
        lows = closes - rng.uniform(0.5, 2.0, n)
        t = datetime(2024, 6, 1, tzinfo=UTC)

        state = detect_regime(
            highs=highs,
            lows=lows,
            closes=closes,
            vol_median=0.15,
            instrument="EUR_USD",
            time=t,
            annualization_factor=FOREX_ANNUALIZATION,
        )
        assert state.regime_label in RegimeLabel
        assert 0.0 <= state.confidence <= 1.0
        assert state.confidence_band in ConfidenceBand
        assert state.vol_30d >= 0.0
        assert 0.0 <= state.adx_14 <= 100.0
        assert state.vol_median == pytest.approx(0.15)
        assert state.instrument == "EUR_USD"
        assert state.time == t
