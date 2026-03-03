"""Tests for BayesianV1Generator integration with Bayesian engine (T-206).

Verifies the full inference path: FeatureSnapshot → tokenize → predict → Signal.
Also covers data-layer edge cases (SR-TG4) and feature_providers.json fix (SR-H6).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.analysis.bayesian import BayesianModel, TokenLikelihood, train
from src.analysis.events import EventLabel
from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig, Signal
from src.analysis.tokenizer import ClassificationRule, TokenSet
from src.data.fetcher_base import CandleRecord
from src.data.verifier import verify_candles
from src.trading.signal import (
    BayesianV1Generator,
    RecoverableSignalError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(
    *,
    event_type: str = "UP_1PCT",
    prior: float = 0.3,
    posterior_cap: float = 0.90,
) -> BayesianModel:
    """Build a simple BayesianModel with one informative token."""
    return BayesianModel(
        event_type=event_type,
        prior=prior,
        likelihoods=(
            TokenLikelihood(token="RSI_BELOW_30", p_given_event=0.8, p_given_no_event=0.2),
            TokenLikelihood(token="MACD_CROSS_UP", p_given_event=0.7, p_given_no_event=0.3),
        ),
        calibration_x=(0.0, 0.5, 1.0),
        calibration_y=(0.0, 0.5, 1.0),
        posterior_cap=posterior_cap,
    )


def _make_rules() -> list[ClassificationRule]:
    """Build minimal classification rules for testing."""
    return [
        ClassificationRule(
            token="RSI_BELOW_30",
            feature_key="rsi:period=14",
            condition="below",
            threshold=30.0,
        ),
        ClassificationRule(
            token="MACD_CROSS_UP",
            feature_key="macd:fast=12,slow=26,signal=9:histogram",
            condition="above",
            threshold=0.0,
        ),
    ]


def _make_features(
    *,
    rsi: float = 25.0,
    macd_hist: float = 0.5,
    close: float = 1.1000,
) -> FeatureSnapshot:
    """Build a FeatureSnapshot with indicator values."""
    return FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        values={
            "rsi:period=14": rsi,
            "macd:fast=12,slow=26,signal=9:histogram": macd_hist,
            "_close": close,
        },
        metadata={},
    )


# ---------------------------------------------------------------------------
# BayesianV1Generator with model — inference path
# ---------------------------------------------------------------------------


class TestBayesianV1GeneratorWithModel:
    """BayesianV1Generator uses tokenize → predict when model and rules in config."""

    def test_generate_with_model_returns_signal(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={
                "model": _make_model(),
                "rules": _make_rules(),
            },
        )
        features = _make_features(rsi=25.0, macd_hist=0.5)
        signal = gen.generate("EUR_USD", features, config)

        assert isinstance(signal, Signal)
        assert signal.instrument == "EUR_USD"
        assert signal.generator_id == "bayesian_v1"
        assert 0.0 <= signal.probability <= 1.0
        assert signal.component_scores.get("bayesian") is not None

    def test_generate_with_model_probability_higher_than_prior(self) -> None:
        """When informative tokens are active, posterior > prior."""
        model = _make_model(prior=0.3)
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": model, "rules": _make_rules()},
        )
        # RSI=25 < 30 → RSI_BELOW_30 active, MACD_HIST=0.5 > 0 → MACD_CROSS_UP active
        features = _make_features(rsi=25.0, macd_hist=0.5)
        signal = gen.generate("EUR_USD", features, config)

        assert signal.probability > model.prior

    def test_generate_with_no_active_tokens_near_prior(self) -> None:
        """When no tokens are active, posterior ≈ prior."""
        model = _make_model(prior=0.3)
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": model, "rules": _make_rules()},
        )
        # RSI=50 > 30 → RSI_BELOW_30 NOT active, MACD_HIST=-0.5 < 0 → MACD_CROSS_UP NOT active
        features = _make_features(rsi=50.0, macd_hist=-0.5)
        signal = gen.generate("EUR_USD", features, config)

        assert signal.probability == pytest.approx(model.prior, abs=0.05)

    def test_generate_respects_posterior_cap(self) -> None:
        """Posterior is capped at model.posterior_cap."""
        model = _make_model(posterior_cap=0.80)
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": model, "rules": _make_rules()},
        )
        features = _make_features(rsi=25.0, macd_hist=0.5)
        signal = gen.generate("EUR_USD", features, config)

        assert signal.probability <= 0.80

    def test_generate_disabled_raises(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=False,
            parameters={"model": _make_model(), "rules": _make_rules()},
        )
        with pytest.raises(RecoverableSignalError, match="disabled"):
            gen.generate("EUR_USD", _make_features(), config)

    def test_generate_metadata_contains_source(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": _make_model(), "rules": _make_rules()},
        )
        signal = gen.generate("EUR_USD", _make_features(), config)
        assert signal.metadata.get("source") == "bayesian_engine"


# ---------------------------------------------------------------------------
# BayesianV1Generator scaffold fallback (no model in config)
# ---------------------------------------------------------------------------


class TestBayesianV1GeneratorScaffoldFallback:
    """Without a model in config, generator falls back to scaffold behavior."""

    def test_fallback_uses_score_from_features(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(enabled=True, parameters={})
        features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"score": 0.7, "confidence": 0.8},
            metadata={},
        )
        signal = gen.generate("EUR_USD", features, config)
        assert signal.probability == pytest.approx(0.7)

    def test_fallback_default_score_is_neutral(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(enabled=True, parameters={})
        features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={},
            metadata={},
        )
        signal = gen.generate("EUR_USD", features, config)
        assert signal.probability == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# generate_batch with model
# ---------------------------------------------------------------------------


class TestBayesianV1GeneratorBatch:
    """generate_batch passes previous features for crossover rules."""

    def test_batch_produces_signals_for_all_snapshots(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": _make_model(), "rules": _make_rules()},
        )
        snapshots = [
            _make_features(rsi=25.0, macd_hist=0.5),
            FeatureSnapshot(
                instrument="EUR_USD",
                interval="1h",
                time=datetime(2026, 3, 1, 13, 0, tzinfo=UTC),
                values={
                    "rsi:period=14": 50.0,
                    "macd:fast=12,slow=26,signal=9:histogram": -0.5,
                    "_close": 1.1050,
                },
                metadata={},
            ),
        ]
        results = gen.generate_batch("EUR_USD", snapshots, config)
        assert len(results) == 2
        assert all(isinstance(ts, datetime) and isinstance(sig, Signal) for ts, sig in results)

    def test_batch_is_deterministic(self) -> None:
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": _make_model(), "rules": _make_rules()},
        )
        snapshots = [_make_features(rsi=25.0), _make_features(rsi=50.0)]
        first = gen.generate_batch("EUR_USD", snapshots, config)
        second = gen.generate_batch("EUR_USD", snapshots, config)
        assert first == second


# ---------------------------------------------------------------------------
# End-to-end integration: train → tokenize → predict → Signal
# ---------------------------------------------------------------------------


class TestEndToEndInferencePath:
    """Full inference pipeline: synthetic data → train → tokenize → predict → Signal."""

    def test_full_pipeline(self) -> None:
        from datetime import timedelta

        rules = _make_rules()
        n = 100
        base = datetime(2026, 1, 1, tzinfo=UTC)

        # Build synthetic token sets and event labels with unique timestamps
        token_sets: list[TokenSet] = []
        event_labels: list[EventLabel] = []
        for i in range(n):
            t = base + timedelta(hours=i)
            # Events correlate with RSI_BELOW_30: when i < 40, RSI_BELOW_30 is active
            has_rsi_below = i < 40
            is_event = i < 30  # strong correlation with RSI_BELOW_30
            tokens: set[str] = set()
            if has_rsi_below:
                tokens.add("RSI_BELOW_30")
            if i % 3 == 0:
                tokens.add("MACD_CROSS_UP")
            token_sets.append(TokenSet(instrument="EUR_USD", time=t, tokens=frozenset(tokens)))
            event_labels.append(EventLabel(event_type="UP_1PCT", time=t, label=is_event))

        selected_tokens = ["RSI_BELOW_30", "MACD_CROSS_UP"]
        model = train(token_sets, event_labels, selected_tokens, "UP_1PCT")

        # Now use the model in BayesianV1Generator
        gen = BayesianV1Generator()
        config = GeneratorConfig(
            enabled=True,
            parameters={"model": model, "rules": rules},
        )

        # Features that should activate RSI_BELOW_30
        features_bullish = _make_features(rsi=25.0, macd_hist=0.5)
        signal_bullish = gen.generate("EUR_USD", features_bullish, config)

        # Features that should NOT activate RSI_BELOW_30
        features_neutral = _make_features(rsi=50.0, macd_hist=-0.5)
        signal_neutral = gen.generate("EUR_USD", features_neutral, config)

        assert signal_bullish.probability > signal_neutral.probability
        assert 0.0 <= signal_bullish.probability <= 1.0
        assert 0.0 <= signal_neutral.probability <= 1.0


# ---------------------------------------------------------------------------
# SR-H6: feature_providers.json class path fix
# ---------------------------------------------------------------------------


class TestFeatureProvidersConfig:
    """Verify feature_providers.json has correct class path."""

    def test_class_path_uses_src_prefix(self) -> None:
        with open("config/feature_providers.json") as f:
            data = json.load(f)
        provider = data["providers"][0]
        assert provider["class"] == "src.data.indicators.TechnicalIndicatorProvider"
        assert not provider["class"].startswith("newton.")


# ---------------------------------------------------------------------------
# SR-TG4: Data-layer edge cases
# ---------------------------------------------------------------------------


class TestVerifierEdgeCases:
    """Edge case tests for verify_candles (SR-TG4)."""

    def test_empty_candle_list(self) -> None:
        result = verify_candles(
            [],
            instrument="EUR_USD",
            interval="1h",
            now=datetime(2026, 3, 1, tzinfo=UTC),
        )
        assert result.total_input == 0
        assert result.deduplicated == []
        assert result.verified == []
        assert result.suspect == []
        assert result.issues == []
        assert result.should_halt_signals is False

    def test_zero_volume_candles_pass_ohlc_integrity(self) -> None:
        """Volume=0 should NOT fail OHLC integrity — volume is not an OHLC field."""
        candle = CandleRecord(
            time=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            instrument="EUR_USD",
            interval="1h",
            open=1.1000,
            high=1.1050,
            low=1.0950,
            close=1.1020,
            volume=0.0,
            spread_avg=None,
            verified=True,
            source="oanda",
        )
        result = verify_candles(
            [candle],
            instrument="EUR_USD",
            interval="1h",
            now=datetime(2026, 3, 1, 0, 30, tzinfo=UTC),
        )
        assert len(result.verified) == 1
        assert len(result.suspect) == 0


class TestIndicatorEdgeCases:
    """Edge case tests for indicator provider (SR-TG4)."""

    def _make_candles(
        self,
        n: int,
        *,
        volume: float = 100.0,
        flat: bool = False,
    ) -> list[CandleRecord]:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        candles: list[CandleRecord] = []
        for i in range(n):
            close = 100.0 if flat else 100.0 + i * 0.1
            candles.append(CandleRecord(
                time=base + __import__("datetime").timedelta(hours=i),
                instrument="EUR_USD",
                interval="1h",
                open=close - 0.05 if not flat else close,
                high=close + 0.1 if not flat else close,
                low=close - 0.1 if not flat else close,
                close=close,
                volume=volume,
                spread_avg=None,
                verified=True,
                source="oanda",
            ))
        return candles

    def test_zero_volume_candles_obv(self) -> None:
        """OBV with zero-volume candles should compute without error."""
        from src.data.indicators import TechnicalIndicatorConfig, TechnicalIndicatorProvider

        provider = TechnicalIndicatorProvider(TechnicalIndicatorConfig(
            rsi_period=2, macd_fast=3, macd_slow=5, macd_signal=2,
            bb_period=3, atr_period=3,
        ))
        candles = self._make_candles(10, volume=0.0)
        result = provider.get_features(
            instrument="EUR_USD", interval="1h", candles=candles, lookback=10,
        )
        assert len(result) > 0
        # OBV should be 0 throughout when volume is 0
        for features in result.values():
            assert features["obv:"] == 0.0

    def test_zero_range_candles_indicators(self) -> None:
        """Candles where open==high==low==close should not crash ATR/BB."""
        from src.data.indicators import TechnicalIndicatorConfig, TechnicalIndicatorProvider

        provider = TechnicalIndicatorProvider(TechnicalIndicatorConfig(
            rsi_period=2, macd_fast=3, macd_slow=5, macd_signal=2,
            bb_period=3, atr_period=3,
        ))
        candles = self._make_candles(10, flat=True)
        result = provider.get_features(
            instrument="EUR_USD", interval="1h", candles=candles, lookback=10,
        )
        assert len(result) > 0
        # ATR should be 0 when there's no price range
        for features in result.values():
            if "atr:period=3" in features:
                assert features["atr:period=3"] == pytest.approx(0.0)
