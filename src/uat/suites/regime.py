"""Regime Detection UAT suite — classification, confidence, edge cases."""

from __future__ import annotations

from src.uat.runner import UATTest

SUITE_ID = "regime"
SUITE_NAME = "Regime Detection"


def test_rg_01() -> str:
    """Regime classification assigns correct labels."""
    from src.regime.detector import RegimeLabel, classify_regime

    # Low vol + trending (vol < median, adx > 25)
    result = classify_regime(vol_30d=0.10, adx_14=35.0, vol_median=0.15)
    assert result == RegimeLabel.LOW_VOL_TRENDING, f"Expected LOW_VOL_TRENDING, got {result}"

    # High vol + ranging (vol > median, adx < 25)
    result2 = classify_regime(vol_30d=0.20, adx_14=15.0, vol_median=0.15)
    assert result2 == RegimeLabel.HIGH_VOL_RANGING, f"Expected HIGH_VOL_RANGING, got {result2}"

    # Low vol + ranging (vol < median, adx < 25)
    result3 = classify_regime(vol_30d=0.10, adx_14=15.0, vol_median=0.15)
    assert result3 == RegimeLabel.LOW_VOL_RANGING, f"Expected LOW_VOL_RANGING, got {result3}"

    # High vol + trending (vol > median, adx > 25)
    result4 = classify_regime(vol_30d=0.20, adx_14=35.0, vol_median=0.15)
    assert result4 == RegimeLabel.HIGH_VOL_TRENDING, f"Expected HIGH_VOL_TRENDING, got {result4}"
    return "All 4 regime labels classified correctly"


def test_rg_02() -> str:
    """Confidence bands computed from vol/ADX distance."""
    from src.regime.detector import ConfidenceBand, compute_confidence

    # High confidence: large distance from thresholds
    conf_val, band = compute_confidence(vol_30d=0.05, adx_14=50.0, vol_median=0.15)
    assert band == ConfidenceBand.HIGH, f"Expected HIGH band, got {band}"
    assert conf_val >= 0.5, f"Expected confidence >= 0.5, got {conf_val}"

    # Low confidence: near thresholds
    conf_val2, band2 = compute_confidence(vol_30d=0.149, adx_14=25.5, vol_median=0.15)
    assert band2 == ConfidenceBand.LOW, f"Expected LOW band, got {band2}"
    assert conf_val2 < 0.2, f"Expected confidence < 0.2, got {conf_val2}"
    return f"HIGH: {conf_val:.3f}, LOW: {conf_val2:.3f}"


def test_rg_03() -> str:
    """Vol computation rejects non-positive prices."""
    import numpy as np

    from src.regime.detector import compute_vol_30d

    # Should raise ValueError for non-positive prices
    try:
        compute_vol_30d(closes=np.array([100.0, 0.0, 99.0]), annualization_factor=252**0.5)
        raise AssertionError("Should have raised ValueError for zero price")  # noqa: TRY301
    except ValueError:
        pass  # Expected

    try:
        compute_vol_30d(closes=np.array([100.0, -1.0, 99.0]), annualization_factor=252**0.5)
        raise AssertionError("Should have raised ValueError for negative price")  # noqa: TRY301
    except ValueError:
        pass  # Expected

    return "ValueError raised for zero and negative prices"


def test_rg_04() -> str:
    """ADX computation produces values in expected range [0, 100]."""
    import numpy as np

    from src.regime.detector import compute_adx_14

    rng = np.random.default_rng(42)
    n = 60
    base = 100.0 + np.cumsum(rng.standard_normal(n) * 0.5)
    highs = base + rng.uniform(0.5, 2.0, n)
    lows = base - rng.uniform(0.5, 2.0, n)
    closes = base + rng.uniform(-0.5, 0.5, n)

    adx = compute_adx_14(highs=highs, lows=lows, closes=closes)
    assert 0 <= adx <= 100, f"ADX should be in [0, 100], got {adx}"
    return f"ADX={adx:.2f} (in valid range)"


TESTS = [
    UATTest(id="RG-01", name="Regime classification assigns correct labels",
            suite=SUITE_ID, fn=test_rg_01),
    UATTest(id="RG-02", name="Confidence bands computed correctly",
            suite=SUITE_ID, fn=test_rg_02),
    UATTest(id="RG-03", name="Vol computation rejects non-positive prices",
            suite=SUITE_ID, fn=test_rg_03),
    UATTest(id="RG-04", name="ADX computation produces valid range",
            suite=SUITE_ID, fn=test_rg_04),
]
