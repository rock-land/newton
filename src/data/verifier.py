"""Data verification pipeline for Stage 1 ingestion cycles (FINAL_SPEC §4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.data.fetcher_base import CandleRecord, require_utc


_INTERVAL_TO_DELTA: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True)
class VerificationIssue:
    issue_type: str
    severity: str
    message: str
    details: dict[str, Any]

    def to_alert_payload(self, *, instrument: str, interval: str) -> dict[str, Any]:
        return {
            "instrument": instrument,
            "interval": interval,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class VerificationResult:
    instrument: str
    interval: str
    total_input: int
    deduplicated: list[CandleRecord]
    verified: list[CandleRecord]
    suspect: list[CandleRecord]
    issues: list[VerificationIssue]

    @property
    def should_halt_signals(self) -> bool:
        return any(issue.issue_type == "stale_data" for issue in self.issues)

    def alert_payloads(self) -> list[dict[str, Any]]:
        return [issue.to_alert_payload(instrument=self.instrument, interval=self.interval) for issue in self.issues]



def interval_to_timedelta(interval: str) -> timedelta:
    try:
        return _INTERVAL_TO_DELTA[interval]
    except KeyError as exc:
        msg = f"unsupported interval: {interval}"
        raise ValueError(msg) from exc



def verify_candles(
    candles: list[CandleRecord],
    *,
    instrument: str,
    interval: str,
    now: datetime | None = None,
    stale_multiplier: float = 2.0,
) -> VerificationResult:
    """Run Stage 1 quality checks: duplicates, OHLC integrity, gaps, staleness."""
    if stale_multiplier <= 0:
        msg = "stale_multiplier must be > 0"
        raise ValueError(msg)

    expected_delta = interval_to_timedelta(interval)
    current_time = require_utc(now or datetime.now(tz=UTC))

    deduplicated, duplicate_count = _deduplicate_keep_latest(candles)
    deduplicated_sorted = sorted(deduplicated, key=lambda c: c.time)

    verified: list[CandleRecord] = []
    suspect: list[CandleRecord] = []
    issues: list[VerificationIssue] = []

    if duplicate_count > 0:
        issues.append(
            VerificationIssue(
                issue_type="duplicate_candles",
                severity="warning",
                message="duplicate candles detected and deduplicated",
                details={"duplicate_count": duplicate_count},
            )
        )

    invalid_times: list[str] = []
    for candle in deduplicated_sorted:
        if _is_valid_ohlc(candle):
            verified.append(candle)
            continue
        suspect.append(candle)
        invalid_times.append(candle.time.isoformat())

    if invalid_times:
        issues.append(
            VerificationIssue(
                issue_type="ohlc_integrity",
                severity="critical",
                message="suspect candle(s) failed OHLC integrity checks; excluded from signal path",
                details={"suspect_count": len(invalid_times), "times": invalid_times},
            )
        )

    if verified:
        missing_count, sample_missing = _count_gaps(verified, expected_delta)
        if missing_count > 0:
            issues.append(
                VerificationIssue(
                    issue_type="gaps",
                    severity="warning",
                    message="missing candles detected",
                    details={
                        "missing_count": missing_count,
                        "sample_missing_times": sample_missing,
                    },
                )
            )

        latest_time = max(c.time for c in verified)
        age = current_time - latest_time
        if age > expected_delta * stale_multiplier:
            issues.append(
                VerificationIssue(
                    issue_type="stale_data",
                    severity="critical",
                    message="no new candle within staleness threshold; halt new signals for instrument",
                    details={
                        "latest_candle_time": latest_time.isoformat(),
                        "age_seconds": int(age.total_seconds()),
                        "threshold_seconds": int((expected_delta * stale_multiplier).total_seconds()),
                    },
                )
            )

    return VerificationResult(
        instrument=instrument,
        interval=interval,
        total_input=len(candles),
        deduplicated=deduplicated_sorted,
        verified=verified,
        suspect=suspect,
        issues=issues,
    )



def _deduplicate_keep_latest(candles: list[CandleRecord]) -> tuple[list[CandleRecord], int]:
    deduped_by_time: dict[datetime, CandleRecord] = {}
    duplicate_count = 0
    for candle in candles:
        if candle.time in deduped_by_time:
            duplicate_count += 1
        deduped_by_time[candle.time] = candle
    return list(deduped_by_time.values()), duplicate_count



def _is_valid_ohlc(candle: CandleRecord) -> bool:
    return candle.high >= max(candle.open, candle.close, candle.low) and candle.low <= min(
        candle.open,
        candle.close,
        candle.high,
    )



def _count_gaps(candles_sorted: list[CandleRecord], expected_delta: timedelta) -> tuple[int, list[str]]:
    if len(candles_sorted) <= 1:
        return 0, []

    missing_count = 0
    sample_missing: list[str] = []
    for prev, curr in zip(candles_sorted, candles_sorted[1:]):
        if curr.time <= prev.time:
            continue
        delta = curr.time - prev.time
        if delta <= expected_delta:
            continue
        missing_between = int(delta.total_seconds() // expected_delta.total_seconds()) - 1
        if missing_between <= 0:
            continue
        missing_count += missing_between

        next_time = prev.time + expected_delta
        for _ in range(missing_between):
            if len(sample_missing) >= 10:
                break
            sample_missing.append(next_time.isoformat())
            next_time += expected_delta

    return missing_count, sample_missing
