"""End-to-End UAT suite — full pipeline, fallback chain, multi-instrument, routing."""

from __future__ import annotations

from src.uat.runner import UATTest

SUITE_ID = "end_to_end"
SUITE_NAME = "End-to-End"


def test_e2e_01() -> str:
    """Neutral fail-safe signal produces valid Signal object."""
    from src.analysis.signal_contract import Signal
    from src.trading.signal import neutral_fail_safe_signal

    signal = neutral_fail_safe_signal("EUR_USD", {"reason": "UAT test"})
    assert isinstance(signal, Signal)
    assert signal.instrument == "EUR_USD"
    assert signal.action == "NEUTRAL"
    assert signal.probability == 0.0
    assert signal.confidence == 0.0
    assert signal.metadata["reason"] == "UAT test"
    return f"Fail-safe: action={signal.action}, prob={signal.probability}, conf={signal.confidence}"


def test_e2e_02() -> str:
    """Fallback chain activates on primary generator error."""
    from datetime import UTC, datetime

    from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig, Signal
    from src.trading.signal import (
        GeneratorRegistry,
        InstrumentRouting,
        RecoverableSignalError,
        SignalRouter,
    )

    class FailingGenerator:
        id = "failing_gen"
        version = "0.1.0"

        def generate(
            self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig,
        ) -> Signal:
            raise RecoverableSignalError("Primary failed")

        def generate_batch(
            self, instrument: str, historical_features: list[FeatureSnapshot],
            config: GeneratorConfig,
        ) -> list[tuple[datetime, Signal]]:
            return []

        def validate_config(self, config: dict[str, object]) -> bool:
            return True

    class FallbackGenerator:
        id = "fallback_gen"
        version = "0.1.0"

        def generate(
            self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig,
        ) -> Signal:
            return Signal(
                instrument=instrument,
                action="BUY",
                probability=0.6,
                confidence=0.5,
                component_scores={"fallback": 0.6},
                metadata={"source": "fallback"},
                generated_at=datetime.now(tz=UTC),
                generator_id="fallback_gen",
            )

        def generate_batch(
            self, instrument: str, historical_features: list[FeatureSnapshot],
            config: GeneratorConfig,
        ) -> list[tuple[datetime, Signal]]:
            return []

        def validate_config(self, config: dict[str, object]) -> bool:
            return True

    registry = GeneratorRegistry()
    registry.register("failing_gen", FailingGenerator)
    registry.register("fallback_gen", FallbackGenerator)
    registry.freeze()

    gen_configs = {
        "failing_gen": GeneratorConfig(enabled=True, parameters={}),
        "fallback_gen": GeneratorConfig(enabled=True, parameters={}),
    }
    routing = {
        "EUR_USD": InstrumentRouting(primary="failing_gen", fallback="fallback_gen"),
    }
    router = SignalRouter(registry, gen_configs, routing)

    features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime(2025, 6, 1, tzinfo=UTC),
        values={"rsi_14": 50.0, "_close": 1.1},
        metadata={},
    )
    signal = router.route_signal("EUR_USD", features)
    assert signal.action == "BUY", f"Expected BUY from fallback, got {signal.action}"
    assert signal.generator_id == "fallback_gen"
    return f"Fallback activated: action={signal.action}, generator={signal.generator_id}"


def test_e2e_03() -> str:
    """Multi-instrument routing produces independent signals."""
    from datetime import UTC, datetime

    from src.analysis.signal_contract import FeatureSnapshot
    from src.trading.signal import build_default_router

    router = build_default_router()

    eur_features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime(2025, 6, 1, tzinfo=UTC),
        values={"rsi_14": 50.0, "_close": 1.1},
        metadata={},
    )
    btc_features = FeatureSnapshot(
        instrument="BTC_USD",
        interval="1h",
        time=datetime(2025, 6, 1, tzinfo=UTC),
        values={"rsi_14": 50.0, "_close": 42000.0},
        metadata={},
    )

    eur_signal = router.route_signal("EUR_USD", eur_features)
    btc_signal = router.route_signal("BTC_USD", btc_features)

    assert eur_signal.instrument == "EUR_USD"
    assert btc_signal.instrument == "BTC_USD"
    return (
        f"EUR_USD: {eur_signal.action} (prob={eur_signal.probability:.3f}), "
        f"BTC_USD: {btc_signal.action} (prob={btc_signal.probability:.3f})"
    )


def test_e2e_04() -> str:
    """Generator registry lists all registered generators."""
    from src.trading.signal import build_default_router

    router = build_default_router()
    generators = router.registry.list_generators()
    assert len(generators) >= 3, f"Expected >= 3 generators, got {len(generators)}"
    expected = {"bayesian_v1", "ml_v1", "ensemble_v1"}
    found = set(generators)
    assert expected.issubset(found), f"Missing generators: {expected - found}"
    return f"Registered generators: {sorted(generators)}"


TESTS = [
    UATTest(id="E2E-01", name="Neutral fail-safe signal is valid",
            suite=SUITE_ID, fn=test_e2e_01),
    UATTest(id="E2E-02", name="Fallback chain activates on primary error",
            suite=SUITE_ID, fn=test_e2e_02),
    UATTest(id="E2E-03", name="Multi-instrument signals generated independently",
            suite=SUITE_ID, fn=test_e2e_03),
    UATTest(id="E2E-04", name="Generator registry lists all generators",
            suite=SUITE_ID, fn=test_e2e_04),
]
