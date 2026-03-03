from __future__ import annotations

from datetime import UTC, datetime, timedelta
import random

import numpy as np
import talib

from src.data.fetcher_base import CandleRecord
import src.data.indicators as indicators_module
from src.data.indicators import TechnicalIndicatorConfig, TechnicalIndicatorProvider
from src.data.pipeline import run_ingestion_cycle


def _candles() -> list[CandleRecord]:
    closes = [10, 11, 12, 11, 13, 12, 14, 13, 15, 16]
    highs = [v + 0.5 for v in closes]
    lows = [v - 0.5 for v in closes]
    volumes = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]

    base = datetime(2026, 1, 1, tzinfo=UTC)
    out: list[CandleRecord] = []
    for i, close in enumerate(closes):
        out.append(
            CandleRecord(
                time=base + timedelta(hours=i),
                instrument="EUR_USD",
                interval="1h",
                open=close - 0.2,
                high=highs[i],
                low=lows[i],
                close=close,
                volume=volumes[i],
                spread_avg=None,
                verified=True,
                source="oanda",
            )
        )
    return out


def test_technical_indicator_provider_v1_deterministic_outputs() -> None:
    provider = TechnicalIndicatorProvider(
        TechnicalIndicatorConfig(
            rsi_period=2,
            macd_fast=3,
            macd_slow=5,
            macd_signal=2,
            bb_period=3,
            bb_std=2.0,
            atr_period=3,
        )
    )

    first = provider.get_features(instrument="EUR_USD", interval="1h", candles=_candles(), lookback=10)
    second = provider.get_features(instrument="EUR_USD", interval="1h", candles=_candles(), lookback=10)
    assert first == second

    last = first[max(first.keys())]
    assert last["rsi:period=2"] == 87.6470588235294
    assert last["macd:fast=3,slow=5,signal=2:line"] == 0.7333333333333325
    assert last["macd:fast=3,slow=5,signal=2:signal"] == 0.6728395061728389
    assert last["macd:fast=3,slow=5,signal=2:histogram"] == 0.06049382716049356
    assert last["bb:period=3,std=2.0:upper"] == 17.161104924515975
    assert last["bb:period=3,std=2.0:middle"] == 14.666666666666666
    assert last["bb:period=3,std=2.0:lower"] == 12.17222840881736
    assert last["obv:"] == 550.0
    assert last["atr:period=3"] == 1.8648834019204392


def _random_walk_candles(*, count: int, seed: int = 20260218) -> list[CandleRecord]:
    rng = random.Random(seed)
    base = datetime(2026, 1, 1, tzinfo=UTC)

    price = 100.0
    out: list[CandleRecord] = []
    for i in range(count):
        price += rng.uniform(-1.5, 1.5)
        close = max(1.0, price)
        high = close + rng.uniform(0.05, 0.8)
        low = max(0.01, close - rng.uniform(0.05, 0.8))
        open_ = close + rng.uniform(-0.5, 0.5)
        volume = rng.uniform(1_000.0, 50_000.0)
        out.append(
            CandleRecord(
                time=base + timedelta(hours=i),
                instrument="EUR_USD",
                interval="1h",
                open=open_,
                high=max(high, open_, close),
                low=min(low, open_, close),
                close=close,
                volume=volume,
                spread_avg=None,
                verified=True,
                source="oanda",
            )
        )
    return out


def test_technical_indicator_provider_matches_talib_reference() -> None:
    candles = _candles()
    closes = np.asarray([c.close for c in candles], dtype=float)
    highs = np.asarray([c.high for c in candles], dtype=float)
    lows = np.asarray([c.low for c in candles], dtype=float)
    volumes = np.asarray([c.volume for c in candles], dtype=float)

    cfg = TechnicalIndicatorConfig(
        rsi_period=2,
        macd_fast=3,
        macd_slow=5,
        macd_signal=2,
        bb_period=3,
        bb_std=2.0,
        atr_period=3,
    )
    provider = TechnicalIndicatorProvider(cfg)
    out = provider.get_features(instrument="EUR_USD", interval="1h", candles=candles, lookback=10)

    rsi = talib.RSI(closes, timeperiod=cfg.rsi_period)
    macd, macd_signal, macd_hist = talib.MACD(
        closes,
        fastperiod=cfg.macd_fast,
        slowperiod=cfg.macd_slow,
        signalperiod=cfg.macd_signal,
    )
    bb_upper, bb_middle, bb_lower = talib.BBANDS(
        closes,
        timeperiod=cfg.bb_period,
        nbdevup=cfg.bb_std,
        nbdevdn=cfg.bb_std,
        matype=0,
    )
    obv = talib.OBV(closes, volumes)
    atr = talib.ATR(highs, lows, closes, timeperiod=cfg.atr_period)

    for idx, candle in enumerate(candles):
        row = out[candle.time]
        if not np.isnan(rsi[idx]):
            assert row[f"rsi:period={cfg.rsi_period}"] == float(rsi[idx])
        if not np.isnan(macd[idx]) and not np.isnan(macd_signal[idx]) and not np.isnan(macd_hist[idx]):
            prefix = f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}"
            assert row[f"{prefix}:line"] == float(macd[idx])
            assert row[f"{prefix}:signal"] == float(macd_signal[idx])
            assert row[f"{prefix}:histogram"] == float(macd_hist[idx])
        if not np.isnan(bb_upper[idx]) and not np.isnan(bb_middle[idx]) and not np.isnan(bb_lower[idx]):
            prefix = f"bb:period={cfg.bb_period},std={cfg.bb_std}"
            assert row[f"{prefix}:upper"] == float(bb_upper[idx])
            assert row[f"{prefix}:middle"] == float(bb_middle[idx])
            assert row[f"{prefix}:lower"] == float(bb_lower[idx])

        assert row["obv:"] == float(obv[idx])
        if not np.isnan(atr[idx]):
            assert row[f"atr:period={cfg.atr_period}"] == float(atr[idx])


def test_technical_indicator_macd_obv_parity_regression_gate() -> None:
    cfg = TechnicalIndicatorConfig()
    candles = _random_walk_candles(count=512)
    closes = np.asarray([c.close for c in candles], dtype=float)
    volumes = np.asarray([c.volume for c in candles], dtype=float)

    provider = TechnicalIndicatorProvider(cfg)
    out = provider.get_features(instrument="EUR_USD", interval="1h", candles=candles, lookback=len(candles))

    macd_line, macd_signal, macd_hist = talib.MACD(
        closes,
        fastperiod=cfg.macd_fast,
        slowperiod=cfg.macd_slow,
        signalperiod=cfg.macd_signal,
    )
    obv = talib.OBV(closes, volumes)

    warmup = max(cfg.macd_slow + cfg.macd_signal + 5, 40)
    sample_indices = random.Random(20260218).sample(list(range(warmup, len(candles))), 100)

    def pct_dev(newton: float, ref: float) -> float:
        return abs(newton - ref) / max(abs(ref), 1e-12) * 100.0

    macd_devs: list[float] = []
    obv_devs: list[float] = []
    prefix = f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}"
    for idx in sample_indices:
        row = out[candles[idx].time]
        macd_devs.extend(
            [
                pct_dev(row[f"{prefix}:line"], float(macd_line[idx])),
                pct_dev(row[f"{prefix}:signal"], float(macd_signal[idx])),
                pct_dev(row[f"{prefix}:histogram"], float(macd_hist[idx])),
            ]
        )
        obv_devs.append(pct_dev(row["obv:"], float(obv[idx])))

    assert max(macd_devs) < 0.01
    assert max(obv_devs) < 0.01


def test_technical_indicator_metadata_complete_and_stable() -> None:
    provider = TechnicalIndicatorProvider()
    metadata = provider.get_feature_metadata()
    keys = {m.feature_key for m in metadata}

    assert len(metadata) == 9
    assert "rsi:period=14" in keys
    assert "macd:fast=12,slow=26,signal=9:line" in keys
    assert "bb:period=20,std=2.0:upper" in keys
    assert "obv:" in keys
    assert "atr:period=14" in keys
    assert all(m.namespace == "technical" for m in metadata)
    assert all(m.provider == "technical_indicator_provider_v1" for m in metadata)


class _FakeFetcher:
    def __init__(self, candles: list[CandleRecord]) -> None:
        self._candles = candles

    def fetch_recent(self, *, interval: str, count: int = 2) -> list[CandleRecord]:
        return self._candles[:count]


class _FakeStoreCandles:
    def __call__(self, _connection: object, candles: list[CandleRecord]) -> int:
        return len(candles)


class _FakeStoreFeatures:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _connection: object, rows: list[object]) -> int:
        self.count = len(rows)
        return self.count


class _FakeStoreMetadata:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _connection: object, metadata: list[object]) -> int:
        self.count = len(metadata)
        return self.count


def test_ingestion_cycle_wires_features_and_metadata() -> None:
    provider = TechnicalIndicatorProvider(
        TechnicalIndicatorConfig(
            rsi_period=2,
            macd_fast=3,
            macd_slow=5,
            macd_signal=2,
            bb_period=3,
            atr_period=3,
        )
    )
    fetcher = _FakeFetcher(_candles())
    feature_store = _FakeStoreFeatures()
    metadata_store = _FakeStoreMetadata()

    result = run_ingestion_cycle(
        instrument="EUR_USD",
        interval="1h",
        fetcher=fetcher,
        store_verified_candles=_FakeStoreCandles(),
        db_connection=object(),
        now=datetime(2026, 1, 1, 10, tzinfo=UTC),
        recent_count=10,
        feature_provider=provider,
        store_feature_records=feature_store,
        store_feature_metadata=metadata_store,
        feature_lookback=10,
    )

    assert result.stored_count == 10
    assert result.feature_count == feature_store.count
    assert result.metadata_count == metadata_store.count
    assert result.feature_count > 0
    assert result.metadata_count == 9


def test_manual_fallback_produces_valid_outputs(monkeypatch: object) -> None:
    """Exercise the pure-Python fallback path by disabling TA-Lib."""
    import pytest

    monkeypatch = pytest.MonkeyPatch()  # noqa: F841 — need a fresh monkeypatch
    monkeypatch.setattr(indicators_module, "talib", None)

    try:
        candles = _random_walk_candles(count=100, seed=42)
        cfg = TechnicalIndicatorConfig(
            rsi_period=5,
            macd_fast=5,
            macd_slow=10,
            macd_signal=3,
            bb_period=5,
            bb_std=2.0,
            atr_period=5,
        )
        provider = TechnicalIndicatorProvider(cfg)
        out = provider.get_features(instrument="EUR_USD", interval="1h", candles=candles, lookback=100)

        assert len(out) > 0

        # Check a fully-warmed-up timestamp has all expected features
        last_ts = max(out.keys())
        last = out[last_ts]
        assert f"rsi:period={cfg.rsi_period}" in last
        assert f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}:line" in last
        assert f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}:signal" in last
        assert f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}:histogram" in last
        assert f"bb:period={cfg.bb_period},std={cfg.bb_std}:upper" in last
        assert f"bb:period={cfg.bb_period},std={cfg.bb_std}:middle" in last
        assert f"bb:period={cfg.bb_period},std={cfg.bb_std}:lower" in last
        assert "obv:" in last
        assert f"atr:period={cfg.atr_period}" in last

        # Verify RSI is in valid range
        rsi = last[f"rsi:period={cfg.rsi_period}"]
        assert 0 <= rsi <= 100

        # Verify Bollinger Bands ordering
        bb_upper = last[f"bb:period={cfg.bb_period},std={cfg.bb_std}:upper"]
        bb_middle = last[f"bb:period={cfg.bb_period},std={cfg.bb_std}:middle"]
        bb_lower = last[f"bb:period={cfg.bb_period},std={cfg.bb_std}:lower"]
        assert bb_upper >= bb_middle >= bb_lower

        # Verify ATR is positive
        atr_val = last[f"atr:period={cfg.atr_period}"]
        assert atr_val > 0
    finally:
        monkeypatch.undo()


def test_manual_fallback_short_data_returns_nones(monkeypatch: object) -> None:
    """Manual fallback handles too-short data gracefully (returns Nones for warmup)."""
    import pytest

    monkeypatch = pytest.MonkeyPatch()  # noqa: F841
    monkeypatch.setattr(indicators_module, "talib", None)

    try:
        # Only 3 candles — shorter than most indicator periods
        candles = _candles()[:3]
        cfg = TechnicalIndicatorConfig(
            rsi_period=5,
            macd_fast=5,
            macd_slow=10,
            macd_signal=3,
            bb_period=5,
            bb_std=2.0,
            atr_period=5,
        )
        provider = TechnicalIndicatorProvider(cfg)
        out = provider.get_features(instrument="EUR_USD", interval="1h", candles=candles, lookback=10)

        # Should still return data (OBV works on any length)
        assert len(out) > 0
        # OBV should always be present
        for ts_features in out.values():
            assert "obv:" in ts_features
    finally:
        monkeypatch.undo()
