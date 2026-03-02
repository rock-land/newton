"""Feature provider contracts and metadata models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from src.data.fetcher_base import CandleRecord


@dataclass(frozen=True)
class FeatureMetadata:
    namespace: str
    feature_key: str
    display_name: str
    description: str
    unit: str | None
    params: dict[str, int | float | str]
    provider: str


class FeatureProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def feature_namespace(self) -> str: ...

    def get_features(
        self,
        *,
        instrument: str,
        interval: str,
        candles: Sequence[CandleRecord],
        lookback: int,
    ) -> dict[datetime, dict[str, float]]: ...

    def get_feature_metadata(self) -> list[FeatureMetadata]: ...
