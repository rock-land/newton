"""Signal registry and deterministic routing/fallback semantics (SPEC.v4)."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
import logging
from typing import Any

import numpy as np

from src.analysis.bayesian import BayesianModel, predict
from src.analysis.signal_contract import (
    FeatureSnapshot,
    GeneratorConfig,
    Signal,
    SignalAction,
    SignalGenerator,
)
from src.analysis.meta_learner import MetaLearnerModel, predict_meta_learner
from src.analysis.tokenizer import ClassificationRule, tokenize
from src.analysis.xgboost_trainer import predict_xgboost

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
    """Bayesian signal generator (SPEC §5.5).

    When ``config.parameters`` contains ``"model"`` (a ``BayesianModel``) and
    ``"rules"`` (a list of ``ClassificationRule``), the generator uses the full
    Bayesian inference path: tokenize features → predict posterior → Signal.

    Without a model, falls back to scaffold behavior (uses ``features.values["score"]``).
    """

    generator_id = "bayesian_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")

        model: BayesianModel | None = config.parameters.get("model")
        rules: list[ClassificationRule] | None = config.parameters.get("rules")

        thresholds = _extract_thresholds(config)

        if model is not None and rules is not None:
            # Real Bayesian inference path: FeatureSnapshot → tokenize → predict → Signal
            if "_close" not in features.values:
                raise RecoverableSignalError(
                    "_close required in features for Bayesian inference"
                )
            token_set = tokenize(
                instrument=instrument,
                time=features.time,
                features=features.values,
                rules=rules,
                close=features.values["_close"],
            )
            probability = predict(model, token_set.tokens)
            return _build_signal(
                instrument=instrument,
                generator_id=self.id,
                probability=probability,
                confidence=_clamp(features.values.get("confidence", 0.5)),
                component_scores={"bayesian": probability},
                metadata={"source": "bayesian_engine", **features.metadata},
                generated_at=features.time,
                thresholds=thresholds,
            )

        # Scaffold fallback: use raw score from features
        probability = _clamp(features.values.get("score", 0.5))
        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=_clamp(features.values.get("confidence", 0.5)),
            component_scores={"bayesian": probability},
            metadata={"source": "threshold", **features.metadata},
            generated_at=features.time,
            thresholds=thresholds,
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
    """XGBoost ML signal generator (SPEC §5.6). Independent per DEC-005.

    When ``config.parameters`` contains ``"model_bytes"`` (serialized XGBoost
    model) and ``"feature_names"`` (ordered feature name tuple), the generator
    uses real XGBoost inference: extract features → predict → Signal.

    Without a model, falls back to scaffold behavior (uses
    ``features.values["score"]``).
    """

    generator_id = "ml_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")

        model_bytes: bytes | None = config.parameters.get("model_bytes")
        feature_names: tuple[str, ...] | None = config.parameters.get("feature_names")

        thresholds = _extract_thresholds(config)

        if model_bytes is not None and feature_names is not None:
            # Real XGBoost inference path
            try:
                values = [features.values[name] for name in feature_names]
            except KeyError as exc:
                raise RecoverableSignalError(
                    f"Missing feature for ML inference: {exc}"
                ) from exc

            feature_vector = np.array(values, dtype=np.float64)
            probability = predict_xgboost(
                model_bytes=model_bytes,
                feature_vector=feature_vector,
            )
            return _build_signal(
                instrument=instrument,
                generator_id=self.id,
                probability=probability,
                confidence=_clamp(features.values.get("confidence", 0.5)),
                component_scores={"ml": probability},
                metadata={"source": "xgboost_engine", **features.metadata},
                generated_at=features.time,
                thresholds=thresholds,
            )

        # Scaffold fallback: use raw score from features
        probability = _clamp(features.values.get("score", 0.5))
        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=_clamp(features.values.get("confidence", 0.5)),
            component_scores={"ml": probability},
            metadata={"source": "scaffold", **features.metadata},
            generated_at=features.time,
            thresholds=thresholds,
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
    """Meta-learner ensemble generator (SPEC §5.7).

    When ``config.parameters`` contains ``"meta_learner_model"`` (a
    ``MetaLearnerModel``), uses logistic regression stacking:
    bayesian_posterior + ml_probability + regime_confidence → combined
    probability.

    Without a meta-learner model, falls back to weighted blend of
    ``bayesian_score`` and ``ml_score`` from features.
    """

    generator_id = "ensemble_v1"

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        if not config.enabled:
            raise RecoverableSignalError("generator disabled")

        meta_model: MetaLearnerModel | None = config.parameters.get("meta_learner_model")

        if meta_model is not None:
            return self._generate_meta_learner(instrument, features, config, meta_model)
        return self._generate_weighted_blend(instrument, features, config)

    def _generate_meta_learner(
        self,
        instrument: str,
        features: FeatureSnapshot,
        config: GeneratorConfig,
        model: MetaLearnerModel,
    ) -> Signal:
        """Meta-learner inference path."""
        try:
            bayesian_posterior = features.values["bayesian_posterior"]
            ml_probability = features.values["ml_probability"]
            regime_confidence = features.values["regime_confidence"]
        except KeyError as exc:
            raise RecoverableSignalError(
                f"Missing feature for meta-learner inference: {exc}"
            ) from exc

        probability = predict_meta_learner(
            model,
            bayesian_posterior=bayesian_posterior,
            ml_probability=ml_probability,
            regime_confidence=regime_confidence,
        )
        confidence = _clamp(1.0 - abs(bayesian_posterior - ml_probability))

        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=confidence,
            component_scores={
                "bayesian": bayesian_posterior,
                "ml": ml_probability,
                "regime": regime_confidence,
            },
            metadata={"source": "meta_learner", **features.metadata},
            generated_at=features.time,
            thresholds=_extract_thresholds(config),
        )

    def _generate_weighted_blend(
        self,
        instrument: str,
        features: FeatureSnapshot,
        config: GeneratorConfig,
    ) -> Signal:
        """Weighted blend fallback (no meta-learner model)."""
        bayesian_score = _clamp(
            features.values.get("bayesian_score", features.values.get("score", 0.5))
        )
        ml_score = _clamp(
            features.values.get("ml_score", features.values.get("score", 0.5))
        )
        weights = config.parameters.get("weights", [0.6, 0.4])
        if not isinstance(weights, list) or len(weights) != 2:
            raise RecoverableSignalError("invalid ensemble weights")
        if abs(sum(float(w) for w in weights) - 1.0) > 0.01:
            raise RecoverableSignalError("ensemble weights must sum to 1.0")

        probability = _clamp(
            (bayesian_score * float(weights[0])) + (ml_score * float(weights[1]))
        )
        confidence = _clamp(1.0 - abs(bayesian_score - ml_score))

        return _build_signal(
            instrument=instrument,
            generator_id=self.id,
            probability=probability,
            confidence=confidence,
            component_scores={"bayesian": bayesian_score, "ml": ml_score},
            metadata={"source": "weighted_blend", "weights": weights, **features.metadata},
            generated_at=features.time,
            thresholds=_extract_thresholds(config),
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
        existing = self.routing[instrument]
        selected = (
            InstrumentRouting(
                primary=generator_override,
                fallback=existing.fallback,
                strong_buy_threshold=existing.strong_buy_threshold,
                buy_threshold=existing.buy_threshold,
                sell_threshold=existing.sell_threshold,
            )
            if generator_override
            else existing
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
    *,
    thresholds: dict[str, float] | None = None,
) -> Signal:
    clamped_probability = _clamp(probability)
    action = _action_from_probability(
        clamped_probability,
        **(
            {
                "strong_buy_threshold": thresholds["strong_buy"],
                "buy_threshold": thresholds["buy"],
                "sell_threshold": thresholds["sell"],
            }
            if thresholds
            else {}
        ),
    )
    return Signal(
        instrument=instrument,
        action=action,
        probability=clamped_probability,
        confidence=_clamp(confidence),
        component_scores=component_scores,
        metadata=metadata,
        generated_at=generated_at,
        generator_id=generator_id,
    )


def _extract_thresholds(config: GeneratorConfig) -> dict[str, float] | None:
    """Extract action thresholds from config.parameters if present."""
    raw = config.parameters.get("thresholds")
    if isinstance(raw, dict) and all(k in raw for k in ("strong_buy", "buy", "sell")):
        return {"strong_buy": float(raw["strong_buy"]), "buy": float(raw["buy"]), "sell": float(raw["sell"])}
    return None


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
