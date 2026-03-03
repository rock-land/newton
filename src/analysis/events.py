"""Event detection and labeling for Bayesian signal pipeline (SPEC §5.1, §5.4–5.5).

Given OHLCV candles and event definitions from strategy config, labels each
timestamp with binary event occurrence (e.g., "price moved ≥1% in next 24h").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.data.fetcher_base import CandleRecord

# Pattern: {PREFIX}_{UP|DOWN}_{N}PCT_{M}H
_EVENT_PATTERN = re.compile(
    r"^[A-Z0-9]+_(UP|DOWN)_(\d+)PCT_(\d+)H$"
)


@dataclass(frozen=True)
class EventDefinition:
    """Parsed event definition extracted from a strategy config event string."""

    event_type: str
    direction: str  # "UP" or "DOWN"
    threshold_pct: float
    horizon_hours: int


@dataclass(frozen=True)
class EventLabel:
    """Binary event label for a single candle timestamp."""

    event_type: str
    time: datetime
    label: bool


def parse_event_definition(event_str: str) -> EventDefinition:
    """Parse an event string like 'EURUSD_UP_1PCT_24H' into an EventDefinition."""
    match = _EVENT_PATTERN.match(event_str)
    if match is None:
        msg = f"Cannot parse event definition: {event_str!r}"
        raise ValueError(msg)
    direction = match.group(1)
    threshold_pct = float(match.group(2))
    horizon_hours = int(match.group(3))
    return EventDefinition(
        event_type=event_str,
        direction=direction,
        threshold_pct=threshold_pct,
        horizon_hours=horizon_hours,
    )


def label_events(
    candles: list[CandleRecord],
    event_definitions: list[str],
) -> list[EventLabel]:
    """Label each candle timestamp with binary event occurrence for each event type.

    For each candle, looks forward within the event's time horizon and checks
    whether the price moved by the required threshold percentage. Uses ``high``
    for UP events and ``low`` for DOWN events to detect if the level was reached
    at any point in the forward window.

    Candles with no forward data (last candle) receive ``label=False``.
    """
    if not candles or not event_definitions:
        return []

    parsed = [parse_event_definition(e) for e in event_definitions]
    labels: list[EventLabel] = []

    for i, candle in enumerate(candles):
        for defn in parsed:
            horizon = timedelta(hours=defn.horizon_hours)
            threshold_ratio = defn.threshold_pct / 100.0
            ref_close = candle.close
            triggered = False

            for j in range(i + 1, len(candles)):
                future = candles[j]
                if future.time - candle.time > horizon:
                    break

                if defn.direction == "UP":
                    if future.high >= ref_close * (1.0 + threshold_ratio):
                        triggered = True
                        break
                else:  # DOWN
                    if future.low <= ref_close * (1.0 - threshold_ratio):
                        triggered = True
                        break

            labels.append(
                EventLabel(
                    event_type=defn.event_type,
                    time=candle.time,
                    label=triggered,
                )
            )

    return labels
