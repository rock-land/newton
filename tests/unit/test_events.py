"""Tests for event detection and labeling (T-202)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.analysis.events import label_events, parse_event_definition
from src.data.fetcher_base import CandleRecord


def _make_candle(
    time: datetime,
    *,
    open_: float = 1.0,
    high: float = 1.0,
    low: float = 1.0,
    close: float = 1.0,
    volume: float = 100.0,
    instrument: str = "EUR_USD",
    interval: str = "1h",
) -> CandleRecord:
    return CandleRecord(
        time=time,
        instrument=instrument,
        interval=interval,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        spread_avg=None,
        verified=True,
        source="test",
    )


BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def _hourly_times(n: int) -> list[datetime]:
    return [BASE_TIME + timedelta(hours=i) for i in range(n)]


# ── Parse event definition ──────────────────────────────────────────


class TestParseEventDefinition:
    def test_parse_up_event(self) -> None:
        defn = parse_event_definition("EURUSD_UP_1PCT_24H")
        assert defn.direction == "UP"
        assert defn.threshold_pct == 1.0
        assert defn.horizon_hours == 24
        assert defn.event_type == "EURUSD_UP_1PCT_24H"

    def test_parse_down_event(self) -> None:
        defn = parse_event_definition("BTCUSD_DOWN_3PCT_24H")
        assert defn.direction == "DOWN"
        assert defn.threshold_pct == 3.0
        assert defn.horizon_hours == 24
        assert defn.event_type == "BTCUSD_DOWN_3PCT_24H"

    def test_parse_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse event definition"):
            parse_event_definition("INVALID_EVENT")

    def test_parse_invalid_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse event definition"):
            parse_event_definition("EURUSD_SIDEWAYS_1PCT_24H")

    def test_event_definition_is_frozen(self) -> None:
        defn = parse_event_definition("EURUSD_UP_1PCT_24H")
        with pytest.raises(AttributeError):
            defn.direction = "DOWN"  # type: ignore[misc]


# ── Label events ────────────────────────────────────────────────────


class TestLabelEventsUp:
    """Test UP event detection (price rises by >= threshold %)."""

    def test_up_event_triggered(self) -> None:
        """Price rises 2% within 24h window — UP_1PCT should be True."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            close = 1.0 if i < 5 else 1.025  # 2.5% rise at candle 5
            candles.append(_make_candle(t, close=close, high=close))
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        # Candle 0 should see the rise within its 24h forward window
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is True

    def test_up_event_not_triggered_flat(self) -> None:
        """Flat price — UP_1PCT should be False."""
        times = _hourly_times(30)
        candles = [_make_candle(t, close=1.0, high=1.0) for t in times]
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is False

    def test_up_event_uses_high_not_just_close(self) -> None:
        """High reaches threshold even though close doesn't."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            if i == 10:
                # High spikes to 1.015 (1.5%) but close stays at 1.005
                candles.append(_make_candle(t, close=1.005, high=1.015))
            else:
                candles.append(_make_candle(t, close=1.0, high=1.0))
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is True


class TestLabelEventsDown:
    """Test DOWN event detection (price drops by >= threshold %)."""

    def test_down_event_triggered(self) -> None:
        """Price drops 2% within 24h — DOWN_1PCT should be True."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            close = 1.0 if i < 5 else 0.975  # 2.5% drop at candle 5
            candles.append(_make_candle(t, close=close, low=close))
        labels = label_events(candles, ["EURUSD_DOWN_1PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is True

    def test_down_event_not_triggered_flat(self) -> None:
        """Flat price — DOWN_1PCT should be False."""
        times = _hourly_times(30)
        candles = [_make_candle(t, close=1.0, low=1.0) for t in times]
        labels = label_events(candles, ["EURUSD_DOWN_1PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is False

    def test_down_event_uses_low(self) -> None:
        """Low reaches threshold even though close doesn't drop enough."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            if i == 10:
                candles.append(_make_candle(t, close=0.995, low=0.985))
            else:
                candles.append(_make_candle(t, close=1.0, low=1.0))
        labels = label_events(candles, ["EURUSD_DOWN_1PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is True


class TestLabelEventsBtcThreshold:
    """BTC_USD uses 3% threshold — verify higher bar."""

    def test_btc_up_3pct_triggered(self) -> None:
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            close = 50000.0 if i < 5 else 51600.0  # 3.2% rise
            candles.append(
                _make_candle(t, close=close, high=close, instrument="BTC_USD")
            )
        labels = label_events(candles, ["BTCUSD_UP_3PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is True

    def test_btc_up_3pct_not_triggered_at_2pct(self) -> None:
        """2% rise is below 3% threshold — should be False."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            close = 50000.0 if i < 5 else 51000.0  # 2% rise
            candles.append(
                _make_candle(t, close=close, high=close, instrument="BTC_USD")
            )
        labels = label_events(candles, ["BTCUSD_UP_3PCT_24H"])
        label_at_0 = [lb for lb in labels if lb.time == times[0]][0]
        assert label_at_0.label is False


class TestLabelEventsTailAndEdge:
    """Tail candles and edge cases."""

    def test_tail_candles_are_false(self) -> None:
        """Last candles with insufficient forward data should be False."""
        times = _hourly_times(30)
        candles = []
        for i, t in enumerate(times):
            # Big rise happens only in the last 3 candles
            close = 1.0 if i < 27 else 1.05
            candles.append(_make_candle(t, close=close, high=close))
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        # Candle at index 28 has only 1 candle forward — can't verify 24h
        # It should still look at whatever forward data exists
        # But candle 29 (the last) has zero forward candles
        last_label = [lb for lb in labels if lb.time == times[29]][0]
        assert last_label.label is False

    def test_empty_candles_returns_empty(self) -> None:
        labels = label_events([], ["EURUSD_UP_1PCT_24H"])
        assert labels == []

    def test_single_candle_returns_false(self) -> None:
        candles = [_make_candle(BASE_TIME, close=1.0, high=1.0)]
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        assert len(labels) == 1
        assert labels[0].label is False

    def test_multiple_events_per_candle(self) -> None:
        """Both UP and DOWN events can be labeled for the same candle."""
        times = _hourly_times(30)
        candles = [_make_candle(t, close=1.0, high=1.0, low=1.0) for t in times]
        events = ["EURUSD_UP_1PCT_24H", "EURUSD_DOWN_1PCT_24H"]
        labels = label_events(candles, events)
        # Should have 2 labels per candle (one per event type)
        assert len(labels) == len(candles) * 2

    def test_event_label_is_frozen(self) -> None:
        times = _hourly_times(30)
        candles = [_make_candle(t, close=1.0, high=1.0) for t in times]
        labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
        with pytest.raises(AttributeError):
            labels[0].label = True  # type: ignore[misc]
