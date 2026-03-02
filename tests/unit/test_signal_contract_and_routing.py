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
    RecoverableSignalError,
    SignalRouter,
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
