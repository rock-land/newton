from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.data.feature_provider import FeatureMetadata
from src.data.feature_store import (
    FeatureRecord,
    build_feature_records,
    query_feature_metadata_registry,
    query_feature_records,
    query_feature_snapshot,
    store_feature_metadata,
    store_feature_records,
)


class FakeCursor:
    def __init__(self) -> None:
        self.last_sql = ""
        self.last_params: tuple[object, ...] = ()
        self.executemany_rows: list[tuple[object, ...]] = []
        self.fetchall_rows: list[tuple[object, ...]] = []

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.last_sql = sql
        self.last_params = params or ()

    def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.last_sql = sql
        self.executemany_rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.fetchall_rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


def test_build_feature_records_is_sorted_and_stable() -> None:
    t1 = datetime(2026, 1, 1, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 1, tzinfo=UTC)

    rows = build_feature_records(
        instrument="EUR_USD",
        interval="1h",
        namespace="technical",
        values_by_time={
            t2: {"z": 2, "a": 1},
            t1: {"b": 3},
        },
    )

    assert rows == [
        FeatureRecord(time=t1, instrument="EUR_USD", interval="1h", namespace="technical", feature_key="b", value=3.0),
        FeatureRecord(time=t2, instrument="EUR_USD", interval="1h", namespace="technical", feature_key="a", value=1.0),
        FeatureRecord(time=t2, instrument="EUR_USD", interval="1h", namespace="technical", feature_key="z", value=2.0),
    ]


def test_store_feature_records_upserts_and_commits() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    count = store_feature_records(
        conn,
        [FeatureRecord(ts, "EUR_USD", "1h", "technical", "rsi:period=14", 55.5)],
    )

    assert count == 1
    assert conn.commits == 1
    assert len(cursor.executemany_rows) == 1
    assert "INSERT INTO features" in cursor.last_sql


def test_store_feature_metadata_dedupes_by_namespace_and_key() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)

    metadata = [
        FeatureMetadata("technical", "rsi:period=14", "RSI", "a", None, {"period": 14}, "p1"),
        FeatureMetadata("technical", "rsi:period=14", "RSI2", "b", None, {"period": 14}, "p2"),
    ]

    count = store_feature_metadata(conn, metadata)

    assert count == 1
    assert conn.commits == 1
    assert len(cursor.executemany_rows) == 1


def test_query_feature_records_filters_by_instrument_interval_and_time() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    cursor.fetchall_rows = [
        (ts, "EUR_USD", "1h", "technical", "rsi:period=14", 50.0),
    ]

    rows = query_feature_records(
        conn,
        instrument="EUR_USD",
        interval="1h",
        start=ts,
        end=ts,
        namespace="technical",
    )

    assert rows[0].feature_key == "rsi:period=14"
    assert rows[0].value == 50.0
    assert cursor.last_params == ("EUR_USD", "1h", ts, ts, "technical")


def test_query_feature_records_rejects_invalid_range() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)

    with pytest.raises(ValueError, match="end must be >= start"):
        query_feature_records(
            conn,
            instrument="EUR_USD",
            interval="1h",
            start=datetime(2026, 1, 2, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_query_feature_snapshot_for_exact_time() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    cursor.fetchall_rows = [
        (ts, "EUR_USD", "1h", "technical", "atr:period=14", 1.2),
    ]

    rows = query_feature_snapshot(
        conn,
        instrument="EUR_USD",
        interval="1h",
        time=ts,
    )

    assert len(rows) == 1
    assert rows[0].feature_key == "atr:period=14"
    assert cursor.last_params == ("EUR_USD", "1h", ts)


def test_query_feature_metadata_registry_maps_rows() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    cursor.fetchall_rows = [
        ("technical", "rsi:period=14", "RSI", "Relative Strength Index", None, {"period": 14}, "technical_indicator_provider_v1"),
    ]

    rows = query_feature_metadata_registry(conn, namespace="technical")

    assert len(rows) == 1
    assert rows[0].namespace == "technical"
    assert rows[0].params == {"period": 14}
    assert cursor.last_params == ("technical",)
