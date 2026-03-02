"""Shared SignalGenerator contract types (SPEC.v4 / FINAL_SPEC compatible)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

SignalAction = Literal["STRONG_BUY", "BUY", "SELL", "NEUTRAL"]
_ALLOWED_ACTIONS: tuple[SignalAction, ...] = ("STRONG_BUY", "BUY", "SELL", "NEUTRAL")


@dataclass(frozen=True)
class Signal:
    """Output from any signal generator."""

    instrument: str
    action: SignalAction
    probability: float
    confidence: float
    component_scores: dict[str, float]
    metadata: dict[str, Any]
    generated_at: datetime
    generator_id: str


@dataclass(frozen=True)
class GeneratorConfig:
    """Generator enablement and implementation-specific parameters."""

    enabled: bool
    parameters: dict[str, Any]


@dataclass(frozen=True)
class FeatureSnapshot:
    """Typed feature payload passed to a signal generator."""

    instrument: str
    interval: str
    time: datetime
    values: dict[str, float]
    metadata: dict[str, Any]


@runtime_checkable
class SignalGenerator(Protocol):
    """Contract for swappable signal generator implementations."""

    @property
    def id(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    def generate(self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig) -> Signal:
        ...

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        """Generate historical signals only.

        Note: This produces timestamped signals. PnL simulation remains owned by
        the backtest module per FINAL_SPEC §8.
        """

    def validate_config(self, config: dict[str, Any]) -> bool:
        ...


def is_valid_action(action: str) -> bool:
    """Return True when action belongs to the FINAL_SPEC action vocabulary."""

    return action in _ALLOWED_ACTIONS
