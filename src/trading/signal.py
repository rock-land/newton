"""Signal registry and deterministic routing/fallback semantics (SPEC.v4)."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
import logging
from typing import Any

from src.analysis.signal_contract import (
    FeatureSnapshot,
    GeneratorConfig,
    Signal,
    SignalAction,
    SignalGenerator,
)

logger = logging.getLogger(__name__)


class RecoverableSignalError(Exception):
    """Recoverable failure raised by a signal generator."""


class GeneratorRegistry:
    """Boot-time mutable, runtime read-only signal generator registry."""

    def __init__(self) -> None:
        self._generators: dict[str, type[SignalGenerator]] = {}
        self._frozen = False

    def register(self, generator_id: str, generator_class: type[SignalGenerator]) -> None:
        if self._frozen:
            raise RuntimeError("signal registry is frozen")
        self._generators[generator_id] = generator_class

    def freeze(self) -> None:
        self._frozen = True

    def get(self, generator_id: str) -> type[SignalGenerator]:
        if generator_id not in self._generators:
            raise ValueError(f"Unknown generator: {generator_id}")
        return self._generators[generator_id]

    def list_generators(self) -> list[str]:
        return sorted(self._generators.keys())

    def create_instance(self, generator_id: str) -> SignalGenerator:
        return self.get(generator_id)()


class _BaseGenerator:
    generator_id: str
    generator_version: str = "0.1.0"

    @property
    def id(self) -> str:
        return self.generator_id

    @property
    def version(self) -> str:
        return self.generator_version

    def validate_config(self, config: dict[str, Any]) -> bool:
        return isinstance(config, dict)


class BayesianV1Generator(_BaseGenerator):
    generator_id = "bayesian_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")
        probability = _clamp(features.values.get("score", 0.5))
        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=_clamp(features.values.get("confidence", 0.5)),
            component_scores={"bayesian": probability},
            metadata={"source": "threshold", **features.metadata},
            generated_at=features.time,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [
            (snapshot.time, self.generate(instrument=instrument, features=snapshot, config=config))
            for snapshot in historical_features
        ]


class MLV1Generator(_BaseGenerator):
    """Scaffold ML signal generator (Stage 3). Independent per DEC-005."""

    generator_id = "ml_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")
        probability = _clamp(features.values.get("score", 0.5))
        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=_clamp(features.values.get("confidence", 0.5)),
            component_scores={"ml": probability},
            metadata={"source": "scaffold", **features.metadata},
            generated_at=features.time,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [
            (snapshot.time, self.generate(instrument=instrument, features=snapshot, config=config))
            for snapshot in historical_features
        ]


class EnsembleV1Generator(_BaseGenerator):
    generator_id = "ensemble_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")
        bayesian_score = _clamp(features.values.get("bayesian_score", features.values.get("score", 0.5)))
        ml_score = _clamp(features.values.get("ml_score", features.values.get("score", 0.5)))
        weights = config.parameters.get("weights", [0.6, 0.4])
        if not isinstance(weights, list) or len(weights) != 2:
            raise RecoverableSignalError("invalid ensemble weights")
        if abs(sum(float(w) for w in weights) - 1.0) > 0.01:
            raise RecoverableSignalError("ensemble weights must sum to 1.0")
        probability = _clamp((bayesian_score * float(weights[0])) + (ml_score * float(weights[1])))
        confidence = _clamp(1.0 - abs(bayesian_score - ml_score))
        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=confidence,
            component_scores={"bayesian": bayesian_score, "ml": ml_score},
            metadata={"weights": weights, **features.metadata},
            generated_at=features.time,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [
            (snapshot.time, self.generate(instrument=instrument, features=snapshot, config=config))
            for snapshot in historical_features
        ]


@dataclass(frozen=True)
class InstrumentRouting:
    primary: str
    fallback: str
    strong_buy_threshold: float = 0.65
    buy_threshold: float = 0.55
    sell_threshold: float = 0.40


@dataclass
class SignalRouter:
    registry: GeneratorRegistry
    generators: dict[str, GeneratorConfig]
    routing: dict[str, InstrumentRouting]

    def route_signal(
        self,
        instrument: str,
        features: FeatureSnapshot,
        generator_override: str | None = None,
    ) -> Signal:
        selected = (
            InstrumentRouting(primary=generator_override, fallback=self.routing[instrument].fallback)
            if generator_override
            else self.routing[instrument]
        )
        primary_id = selected.primary
        fallback_id = selected.fallback

        try:
            signal = self._generate_with(primary_id, instrument, features)
        except (RecoverableSignalError, ValueError, KeyError) as exc:
            logger.warning(
                "signal_generator_fallback",
                extra={
                    "instrument": instrument,
                    "primary": primary_id,
                    "fallback": fallback_id,
                    "reason": str(exc),
                },
            )
            try:
                signal = self._generate_with(fallback_id, instrument, features)
            except (RecoverableSignalError, ValueError, KeyError) as fallback_exc:
                return neutral_fail_safe_signal(
                    instrument=instrument,
                    metadata={
                        "error": "routing_failed",
                        "primary": primary_id,
                        "fallback": fallback_id,
                        "reason": str(fallback_exc),
                    },
                )

        if signal.generator_id == "failsafe":
            return signal

        thresholds = selected
        return replace(
            signal,
            action=_action_from_probability(
                signal.probability,
                strong_buy_threshold=thresholds.strong_buy_threshold,
                buy_threshold=thresholds.buy_threshold,
                sell_threshold=thresholds.sell_threshold,
            ),
        )

    def _generate_with(self, generator_id: str, instrument: str, features: FeatureSnapshot) -> Signal:
        generator = self.registry.create_instance(generator_id)
        config = self.generators[generator_id]
        if not generator.validate_config(config.parameters):
            raise RecoverableSignalError("invalid generator config")
        return generator.generate(instrument=instrument, features=features, config=config)


# FINAL_SPEC §8 boundary: signal generation is separate from backtest simulation ownership.
def neutral_fail_safe_signal(instrument: str, metadata: dict[str, Any]) -> Signal:
    now = datetime.now(tz=UTC)
    return Signal(
        instrument=instrument,
        action="NEUTRAL",
        probability=0.0,
        confidence=0.0,
        component_scores={},
        metadata=metadata,
        generated_at=now,
        generator_id="failsafe",
    )


def _action_from_probability(
    probability: float,
    *,
    strong_buy_threshold: float = 0.65,
    buy_threshold: float = 0.55,
    sell_threshold: float = 0.40,
) -> SignalAction:
    if probability > strong_buy_threshold:
        return "STRONG_BUY"
    if probability > buy_threshold:
        return "BUY"
    if probability < sell_threshold:
        return "SELL"
    return "NEUTRAL"


def _build_signal(
    instrument: str,
    generator_id: str,
    probability: float,
    confidence: float,
    component_scores: dict[str, float],
    metadata: dict[str, Any],
    generated_at: datetime,
) -> Signal:
    clamped_probability = _clamp(probability)
    return Signal(
        instrument=instrument,
        action=_action_from_probability(clamped_probability),
        probability=clamped_probability,
        confidence=_clamp(confidence),
        component_scores=component_scores,
        metadata=metadata,
        generated_at=generated_at,
        generator_id=generator_id,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_default_router() -> SignalRouter:
    registry = GeneratorRegistry()
    registry.register("bayesian_v1", BayesianV1Generator)
    registry.register("ml_v1", MLV1Generator)
    registry.register("ensemble_v1", EnsembleV1Generator)
    registry.freeze()

    generators = {
        "bayesian_v1": GeneratorConfig(enabled=True, parameters={}),
        "ml_v1": GeneratorConfig(enabled=False, parameters={}),
        "ensemble_v1": GeneratorConfig(enabled=True, parameters={"weights": [0.6, 0.4]}),
    }
    routing = {
        "EUR_USD": InstrumentRouting(
            primary="bayesian_v1",
            fallback="ensemble_v1",
            strong_buy_threshold=0.65,
            buy_threshold=0.55,
            sell_threshold=0.40,
        ),
        "BTC_USD": InstrumentRouting(
            primary="ensemble_v1",
            fallback="bayesian_v1",
            strong_buy_threshold=0.60,
            buy_threshold=0.50,
            sell_threshold=0.45,
        ),
    }
    return SignalRouter(registry=registry, generators=generators, routing=routing)
