from __future__ import annotations

from datetime import UTC, datetime
import logging

from src.analysis.signal_contract import FeatureSnapshot, Signal, is_valid_action
import pytest

from src.trading.signal import (
    BayesianV1Generator,
    GeneratorConfig,
    GeneratorRegistry,
    InstrumentRouting,
    MLV1Generator,
    RecoverableSignalError,
    SignalRouter,
    _action_from_probability,
    _build_signal,
    build_default_router,
)


def test_signal_contract_vocab_and_required_fields() -> None:
    signal = Signal(
        instrument="EUR_USD",
        action="BUY",
        probability=0.55,
        confidence=0.60,
        component_scores={"bayesian": 0.55},
        metadata={"reason": "test"},
        generated_at=datetime.now(tz=UTC),
        generator_id="bayesian_v1",
    )
    assert is_valid_action(signal.action)
    assert isinstance(signal.component_scores, dict)
    assert isinstance(signal.metadata, dict)


def test_generate_batch_is_deterministic() -> None:
    generator = BayesianV1Generator()
    cfg = GeneratorConfig(enabled=True, parameters={})
    features = [
        FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime(2026, 2, 18, 0, 0, tzinfo=UTC),
            values={"score": 0.7, "confidence": 0.8},
            metadata={},
        ),
        FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime(2026, 2, 18, 1, 0, tzinfo=UTC),
            values={"score": 0.3, "confidence": 0.8},
            metadata={},
        ),
    ]

    first = generator.generate_batch("EUR_USD", features, cfg)
    second = generator.generate_batch("EUR_USD", features, cfg)

    assert first == second
    assert [item[1].action for item in first] == ["STRONG_BUY", "SELL"]


def test_router_fallback_logs_and_returns_neutral_when_all_fail(caplog: pytest.LogCaptureFixture) -> None:
    class AlwaysFailGenerator(BayesianV1Generator):
        generator_id = "always_fail"

        def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
            raise RecoverableSignalError("boom")

    registry = GeneratorRegistry()
    registry.register("always_fail", AlwaysFailGenerator)
    registry.freeze()

    router = SignalRouter(
        registry=registry,
        generators={"always_fail": GeneratorConfig(enabled=True, parameters={})},
        routing={"EUR_USD": InstrumentRouting(primary="always_fail", fallback="always_fail")},
    )

    caplog.set_level(logging.WARNING)
    signal = router.route_signal(
        instrument="EUR_USD",
        features=FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"score": 0.5},
            metadata={},
        ),
    )

    assert signal.action == "NEUTRAL"
    assert signal.confidence == 0.0
    assert "routing_failed" in str(signal.metadata)
    assert any(record.message == "signal_generator_fallback" for record in caplog.records)


def test_default_router_contains_expected_generators() -> None:
    router = build_default_router()
    assert router.registry.list_generators() == ["bayesian_v1", "ensemble_v1", "ml_v1"]


def test_ensemble_confidence_decreases_with_disagreement() -> None:
    router = build_default_router()

    high_agreement = router.route_signal(
        instrument="BTC_USD",
        features=FeatureSnapshot(
            instrument="BTC_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_score": 0.70, "ml_score": 0.68},
            metadata={},
        ),
    )
    strong_disagreement = router.route_signal(
        instrument="BTC_USD",
        features=FeatureSnapshot(
            instrument="BTC_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_score": 0.95, "ml_score": 0.05},
            metadata={},
        ),
    )

    assert high_agreement.confidence > strong_disagreement.confidence
    assert high_agreement.confidence == pytest.approx(0.98)
    assert strong_disagreement.confidence == pytest.approx(0.10)


def test_instrument_specific_thresholds_apply_differently() -> None:
    router = build_default_router()
    shared_probability = 0.53

    eur_signal = router.route_signal(
        instrument="EUR_USD",
        features=FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"score": shared_probability, "confidence": 0.7},
            metadata={},
        ),
    )
    btc_signal = router.route_signal(
        instrument="BTC_USD",
        features=FeatureSnapshot(
            instrument="BTC_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_score": shared_probability, "ml_score": shared_probability},
            metadata={},
        ),
    )

    assert eur_signal.probability == pytest.approx(shared_probability)
    assert btc_signal.probability == pytest.approx(shared_probability)
    assert eur_signal.action == "NEUTRAL"
    assert btc_signal.action == "BUY"


# --- SR-H1: Strict > thresholds per SPEC §5.7 ---


class TestActionFromProbabilityBoundaries:
    """Probability exactly at a threshold should NOT trigger that action (strict >)."""

    def test_exactly_at_strong_buy_threshold_is_not_strong_buy(self) -> None:
        assert _action_from_probability(0.65, strong_buy_threshold=0.65) != "STRONG_BUY"

    def test_just_above_strong_buy_threshold(self) -> None:
        assert _action_from_probability(0.6501, strong_buy_threshold=0.65) == "STRONG_BUY"

    def test_exactly_at_buy_threshold_is_not_buy(self) -> None:
        assert _action_from_probability(0.55, buy_threshold=0.55) != "BUY"

    def test_just_above_buy_threshold(self) -> None:
        assert _action_from_probability(0.5501, buy_threshold=0.55) == "BUY"

    def test_exactly_at_sell_threshold_is_neutral(self) -> None:
        # sell requires < threshold, so exactly at threshold → NEUTRAL
        assert _action_from_probability(0.40, sell_threshold=0.40) == "NEUTRAL"

    def test_just_below_sell_threshold(self) -> None:
        assert _action_from_probability(0.3999, sell_threshold=0.40) == "SELL"

    def test_all_defaults_neutral_zone(self) -> None:
        # Exactly at buy threshold with defaults: 0.55 is not > 0.55
        assert _action_from_probability(0.55) == "NEUTRAL"


# --- SR-M8: Clamp before action computation ---


def test_build_signal_clamps_before_action() -> None:
    """Probability > 1.0 should be clamped to 1.0 before action is computed."""
    signal = _build_signal(
        instrument="EUR_USD",
        generator_id="test",
        probability=1.5,
        confidence=0.8,
        component_scores={},
        metadata={},
        generated_at=datetime.now(tz=UTC),
    )
    assert signal.probability == 1.0
    assert signal.action == "STRONG_BUY"


def test_build_signal_clamps_negative_probability() -> None:
    signal = _build_signal(
        instrument="EUR_USD",
        generator_id="test",
        probability=-0.5,
        confidence=0.8,
        component_scores={},
        metadata={},
        generated_at=datetime.now(tz=UTC),
    )
    assert signal.probability == 0.0
    assert signal.action == "SELL"


# --- SR-M1: MLV1Generator is independent (no inheritance from BayesianV1) ---


def test_mlv1_does_not_inherit_from_bayesian() -> None:
    assert not issubclass(MLV1Generator, BayesianV1Generator)


def test_mlv1_satisfies_signal_generator_protocol() -> None:
    from src.analysis.signal_contract import SignalGenerator

    assert isinstance(MLV1Generator(), SignalGenerator)


def test_mlv1_generates_signal_independently() -> None:
    gen = MLV1Generator()
    cfg = GeneratorConfig(enabled=True, parameters={})
    features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.6, "confidence": 0.7},
        metadata={},
    )
    signal = gen.generate("EUR_USD", features, cfg)
    assert signal.generator_id == "ml_v1"
    assert is_valid_action(signal.action)


# --- SR-M2: Ensemble weights must sum to 1.0 ---


def test_ensemble_rejects_weights_not_summing_to_one() -> None:
    from src.trading.signal import EnsembleV1Generator

    gen = EnsembleV1Generator()
    cfg = GeneratorConfig(enabled=True, parameters={"weights": [1.0, 1.0]})
    features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"bayesian_score": 0.5, "ml_score": 0.5},
        metadata={},
    )
    with pytest.raises(RecoverableSignalError, match="sum to 1.0"):
        gen.generate("EUR_USD", features, cfg)


def test_ensemble_accepts_weights_summing_to_one() -> None:
    from src.trading.signal import EnsembleV1Generator

    gen = EnsembleV1Generator()
    cfg = GeneratorConfig(enabled=True, parameters={"weights": [0.6, 0.4]})
    features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"bayesian_score": 0.5, "ml_score": 0.5},
        metadata={},
    )
    signal = gen.generate("EUR_USD", features, cfg)
    assert signal.probability == pytest.approx(0.5)


# --- SR-TG5: Registry edge cases ---


def test_registry_register_after_freeze_raises() -> None:
    registry = GeneratorRegistry()
    registry.register("bayesian_v1", BayesianV1Generator)
    registry.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register("new_gen", BayesianV1Generator)


def test_registry_get_unknown_generator_raises() -> None:
    registry = GeneratorRegistry()
    registry.freeze()
    with pytest.raises(ValueError, match="Unknown generator"):
        registry.get("nonexistent")


# --- T-206-FIX1: SR-H2 — Generator override preserves instrument thresholds ---


def test_generator_override_preserves_btc_thresholds() -> None:
    """When generator_override is specified, instrument-specific thresholds must be used."""
    router = build_default_router()
    # BTC_USD thresholds: strong_buy=0.60, buy=0.50, sell=0.45
    # Probability 0.53 is BUY for BTC (>0.50) but NEUTRAL for EUR (not >0.55)
    features = FeatureSnapshot(
        instrument="BTC_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.53, "confidence": 0.7},
        metadata={},
    )
    signal = router.route_signal(
        instrument="BTC_USD",
        features=features,
        generator_override="bayesian_v1",
    )
    # With BTC thresholds (buy > 0.50), 0.53 should be BUY
    assert signal.action == "BUY"


def test_generator_override_does_not_use_default_thresholds() -> None:
    """Override must NOT fall back to default thresholds (0.65/0.55/0.40)."""
    router = build_default_router()
    # Probability 0.42 is NEUTRAL for EUR (>0.40 sell threshold) but SELL for BTC (<0.45)
    features = FeatureSnapshot(
        instrument="BTC_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.42, "confidence": 0.7},
        metadata={},
    )
    signal = router.route_signal(
        instrument="BTC_USD",
        features=features,
        generator_override="bayesian_v1",
    )
    # With BTC thresholds (sell < 0.45), 0.42 should be SELL
    assert signal.action == "SELL"


# --- T-206-FIX1: SR-H3 — generate_batch uses instrument thresholds ---


def test_batch_signal_uses_config_thresholds() -> None:
    """generate_batch signals should use thresholds from config when provided."""
    gen = BayesianV1Generator()
    # BTC_USD thresholds passed via config parameters
    config = GeneratorConfig(
        enabled=True,
        parameters={
            "thresholds": {
                "strong_buy": 0.60,
                "buy": 0.50,
                "sell": 0.45,
            },
        },
    )
    # Probability 0.53 — BUY with BTC thresholds, NEUTRAL with defaults
    features = FeatureSnapshot(
        instrument="BTC_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.53, "confidence": 0.7},
        metadata={},
    )
    results = gen.generate_batch("BTC_USD", [features], config)
    assert len(results) == 1
    _, signal = results[0]
    assert signal.action == "BUY"


def test_batch_signal_without_thresholds_uses_defaults() -> None:
    """Without thresholds in config, defaults apply (backward compatible)."""
    gen = BayesianV1Generator()
    config = GeneratorConfig(enabled=True, parameters={})
    features = FeatureSnapshot(
        instrument="BTC_USD",
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.53, "confidence": 0.7},
        metadata={},
    )
    results = gen.generate_batch("BTC_USD", [features], config)
    _, signal = results[0]
    # 0.53 is NEUTRAL with default thresholds (buy > 0.55)
    assert signal.action == "NEUTRAL"


# --- T-306: EnsembleV1Generator meta-learner integration ---


class TestEnsembleMetaLearner:
    """EnsembleV1Generator with and without meta-learner model."""

    @staticmethod
    def _trained_meta_learner_model() -> object:
        from src.analysis.meta_learner import train_meta_learner
        import numpy as np

        rng = np.random.default_rng(42)
        n = 300
        labels_arr = rng.integers(0, 2, size=n).astype(int)
        bayesian = np.where(labels_arr == 1, rng.uniform(0.6, 0.9, n), rng.uniform(0.1, 0.4, n))
        ml = np.where(labels_arr == 1, rng.uniform(0.55, 0.85, n), rng.uniform(0.15, 0.45, n))
        regime = rng.uniform(0.2, 0.8, n)
        return train_meta_learner(
            bayesian_posteriors=tuple(float(x) for x in bayesian),
            ml_probabilities=tuple(float(x) for x in ml),
            regime_confidences=tuple(float(x) for x in regime),
            labels=tuple(int(x) for x in labels_arr),
        )

    def test_with_meta_learner_model_uses_meta_learner_path(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        model = self._trained_meta_learner_model()
        gen = EnsembleV1Generator()
        cfg = GeneratorConfig(
            enabled=True,
            parameters={"meta_learner_model": model, "weights": [0.6, 0.4]},
        )
        features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_posterior": 0.75, "ml_probability": 0.80, "regime_confidence": 0.6},
            metadata={},
        )
        signal = gen.generate("EUR_USD", features, cfg)
        assert signal.metadata["source"] == "meta_learner"
        assert 0.0 <= signal.probability <= 1.0

    def test_without_meta_learner_model_uses_weighted_blend(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        gen = EnsembleV1Generator()
        cfg = GeneratorConfig(
            enabled=True,
            parameters={"weights": [0.6, 0.4]},
        )
        features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_score": 0.7, "ml_score": 0.6},
            metadata={},
        )
        signal = gen.generate("EUR_USD", features, cfg)
        assert signal.metadata["source"] == "weighted_blend"
        expected = 0.7 * 0.6 + 0.6 * 0.4
        assert signal.probability == pytest.approx(expected)

    def test_meta_learner_generate_batch_all_source_meta_learner(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        model = self._trained_meta_learner_model()
        gen = EnsembleV1Generator()
        cfg = GeneratorConfig(
            enabled=True,
            parameters={"meta_learner_model": model, "weights": [0.6, 0.4]},
        )
        snapshots = [
            FeatureSnapshot(
                instrument="EUR_USD",
                interval="1h",
                time=datetime(2026, 3, 4, h, 0, tzinfo=UTC),
                values={"bayesian_posterior": 0.6 + h * 0.01, "ml_probability": 0.7, "regime_confidence": 0.5},
                metadata={},
            )
            for h in range(5)
        ]
        results = gen.generate_batch("EUR_USD", snapshots, cfg)
        assert len(results) == 5
        for _, signal in results:
            assert signal.metadata["source"] == "meta_learner"

    def test_meta_learner_missing_feature_raises(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        model = self._trained_meta_learner_model()
        gen = EnsembleV1Generator()
        cfg = GeneratorConfig(
            enabled=True,
            parameters={"meta_learner_model": model, "weights": [0.6, 0.4]},
        )
        # Missing regime_confidence
        features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_posterior": 0.7, "ml_probability": 0.8},
            metadata={},
        )
        with pytest.raises(RecoverableSignalError, match="regime_confidence"):
            gen.generate("EUR_USD", features, cfg)

    def test_meta_learner_high_inputs_higher_probability(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        model = self._trained_meta_learner_model()
        gen = EnsembleV1Generator()
        cfg = GeneratorConfig(
            enabled=True,
            parameters={"meta_learner_model": model, "weights": [0.6, 0.4]},
        )
        high_features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_posterior": 0.85, "ml_probability": 0.85, "regime_confidence": 0.7},
            metadata={},
        )
        low_features = FeatureSnapshot(
            instrument="EUR_USD",
            interval="1h",
            time=datetime.now(tz=UTC),
            values={"bayesian_posterior": 0.15, "ml_probability": 0.15, "regime_confidence": 0.3},
            metadata={},
        )
        high_signal = gen.generate("EUR_USD", high_features, cfg)
        low_signal = gen.generate("EUR_USD", low_features, cfg)
        assert high_signal.probability > low_signal.probability


# ---------------------------------------------------------------------------
# validate_config (T-306-FIX2)
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """Generator validate_config methods check required parameters."""

    def test_mlv1_validate_config_accepts_valid(self) -> None:
        from src.trading.signal import MLV1Generator

        gen = MLV1Generator()
        assert gen.validate_config({"model_bytes": b"data", "feature_names": ("f0",)}) is True

    def test_mlv1_validate_config_accepts_scaffold(self) -> None:
        """Scaffold mode (no model) is valid."""
        from src.trading.signal import MLV1Generator

        gen = MLV1Generator()
        assert gen.validate_config({}) is True

    def test_mlv1_validate_config_rejects_partial(self) -> None:
        """model_bytes without feature_names is invalid."""
        from src.trading.signal import MLV1Generator

        gen = MLV1Generator()
        assert gen.validate_config({"model_bytes": b"data"}) is False

    def test_ensemble_validate_config_accepts_meta_learner(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        gen = EnsembleV1Generator()
        # meta_learner_model present → valid
        assert gen.validate_config({"meta_learner_model": "dummy", "weights": [0.6, 0.4]}) is True

    def test_ensemble_validate_config_accepts_weighted_blend(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        gen = EnsembleV1Generator()
        assert gen.validate_config({"weights": [0.6, 0.4]}) is True

    def test_ensemble_validate_config_rejects_bad_weights(self) -> None:
        from src.trading.signal import EnsembleV1Generator

        gen = EnsembleV1Generator()
        # weights must be list of 2
        assert gen.validate_config({"weights": [0.5]}) is False

    def test_bayesian_validate_config_accepts_anything(self) -> None:
        """BayesianV1 has optional model/rules — all dict configs are valid."""
        from src.trading.signal import BayesianV1Generator

        gen = BayesianV1Generator()
        assert gen.validate_config({}) is True
        assert gen.validate_config({"model": "x", "rules": []}) is True
