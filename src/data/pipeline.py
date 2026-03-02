"""Ingestion pipeline orchestration with integrated verification checks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol, Sequence

from src.data.feature_provider import FeatureMetadata, FeatureProvider
from src.data.feature_store import FeatureRecord, build_feature_records
from src.data.fetcher_base import CandleRecord
from src.data.verifier import VerificationResult, verify_candles


class RecentFetcher(Protocol):
    def fetch_recent(self, *, interval: str, count: int = 2) -> list[CandleRecord]: ...


StoreVerifiedCandles = Callable[[object, list[CandleRecord]], int]
StoreFeatureRecords = Callable[[object, Sequence[FeatureRecord]], int]
StoreFeatureMetadata = Callable[[object, Sequence[FeatureMetadata]], int]


@dataclass(frozen=True)
class IngestionCycleResult:
    instrument: str
    interval: str
    fetched_count: int
    stored_count: int
    verification: VerificationResult
    feature_count: int = 0
    metadata_count: int = 0



def run_ingestion_cycle(
    *,
    instrument: str,
    interval: str,
    fetcher: RecentFetcher,
    store_verified_candles: StoreVerifiedCandles,
    db_connection: object,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    recent_count: int = 5,
    feature_provider: FeatureProvider | None = None,
    store_feature_records: StoreFeatureRecords | None = None,
    store_feature_metadata: StoreFeatureMetadata | None = None,
    feature_lookback: int = 120,
) -> IngestionCycleResult:
    """Fetch, verify, persist verified candles, and emit alert-ready logs."""
    log = logger or logging.getLogger(__name__)
    current_time = now or datetime.now(tz=UTC)

    candles = fetcher.fetch_recent(interval=interval, count=recent_count)
    verification = verify_candles(
        candles,
        instrument=instrument,
        interval=interval,
        now=current_time,
    )

    stored_count = store_verified_candles(db_connection, verification.verified)

    feature_count = 0
    metadata_count = 0
    if feature_provider is not None and store_feature_records is not None and store_feature_metadata is not None:
        by_time = feature_provider.get_features(
            instrument=instrument,
            interval=interval,
            candles=verification.verified,
            lookback=feature_lookback,
        )
        feature_rows = build_feature_records(
            instrument=instrument,
            interval=interval,
            namespace=feature_provider.feature_namespace,
            values_by_time=by_time,
        )
        feature_count = store_feature_records(db_connection, feature_rows)
        metadata_count = store_feature_metadata(db_connection, feature_provider.get_feature_metadata())

    summary = {
        "event": "ingestion_cycle",
        "instrument": instrument,
        "interval": interval,
        "fetched_count": len(candles),
        "deduplicated_count": len(verification.deduplicated),
        "stored_count": stored_count,
        "feature_count": feature_count,
        "metadata_count": metadata_count,
        "suspect_count": len(verification.suspect),
        "issue_count": len(verification.issues),
        "halt_signals": verification.should_halt_signals,
    }
    log.info(json.dumps(summary, sort_keys=True))

    for payload in verification.alert_payloads():
        log.warning(json.dumps({"event": "data_verification_alert", **payload}, sort_keys=True))

    return IngestionCycleResult(
        instrument=instrument,
        interval=interval,
        fetched_count=len(candles),
        stored_count=stored_count,
        verification=verification,
        feature_count=feature_count,
        metadata_count=metadata_count,
    )
