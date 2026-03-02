"""Feature store write helpers for Stage 1 long-format features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.data.feature_provider import FeatureMetadata
from src.data.fetcher_base import require_utc


@dataclass(frozen=True)
class FeatureRecord:
    time: datetime
    instrument: str
    interval: str
    namespace: str
    feature_key: str
    value: float


class CursorLike(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None: ...

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...


def build_feature_records(
    *,
    instrument: str,
    interval: str,
    namespace: str,
    values_by_time: dict[datetime, dict[str, float]],
) -> list[FeatureRecord]:
    rows: list[FeatureRecord] = []
    for ts in sorted(values_by_time.keys()):
        for key, value in sorted(values_by_time[ts].items()):
            rows.append(
                FeatureRecord(
                    time=ts,
                    instrument=instrument,
                    interval=interval,
                    namespace=namespace,
                    feature_key=key,
                    value=float(value),
                )
            )
    return rows


def store_feature_records(connection: ConnectionLike, features: list[FeatureRecord]) -> int:
    if not features:
        return 0

    rows = [
        (f.time, f.instrument, f.interval, f.namespace, f.feature_key, f.value)
        for f in features
    ]

    cursor = connection.cursor()
    cursor.executemany(
        """
        INSERT INTO features (time, instrument, interval, namespace, feature_key, value)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (time, instrument, interval, namespace, feature_key) DO UPDATE
        SET value = EXCLUDED.value
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def store_feature_metadata(connection: ConnectionLike, metadata: list[FeatureMetadata]) -> int:
    if not metadata:
        return 0

    deduped = {(m.namespace, m.feature_key): m for m in metadata}
    rows = [
        (
            m.namespace,
            m.feature_key,
            m.display_name,
            m.description,
            m.unit,
            m.params,
            m.provider,
        )
        for m in deduped.values()
    ]

    cursor = connection.cursor()
    cursor.executemany(
        """
        INSERT INTO feature_metadata (namespace, feature_key, display_name, description, unit, params, provider)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (namespace, feature_key) DO UPDATE
        SET
            display_name = EXCLUDED.display_name,
            description = EXCLUDED.description,
            unit = EXCLUDED.unit,
            params = EXCLUDED.params,
            provider = EXCLUDED.provider
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def query_feature_records(
    connection: ConnectionLike,
    *,
    instrument: str,
    interval: str,
    start: datetime,
    end: datetime,
    namespace: str | None = None,
) -> list[FeatureRecord]:
    start_utc = require_utc(start)
    end_utc = require_utc(end)
    if end_utc < start_utc:
        msg = "end must be >= start"
        raise ValueError(msg)

    sql = """
        SELECT time, instrument, interval, namespace, feature_key, value
        FROM features
        WHERE instrument = %s
          AND interval = %s
          AND time >= %s
          AND time <= %s
    """
    params: list[Any] = [instrument, interval, start_utc, end_utc]
    if namespace is not None:
        sql += " AND namespace = %s"
        params.append(namespace)
    sql += " ORDER BY time ASC, namespace ASC, feature_key ASC"

    cursor = connection.cursor()
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    return [
        FeatureRecord(
            time=row[0],
            instrument=row[1],
            interval=row[2],
            namespace=row[3],
            feature_key=row[4],
            value=float(row[5]),
        )
        for row in rows
    ]


def query_feature_snapshot(
    connection: ConnectionLike,
    *,
    instrument: str,
    interval: str,
    time: datetime,
    namespace: str | None = None,
) -> list[FeatureRecord]:
    timestamp_utc = require_utc(time)

    sql = """
        SELECT time, instrument, interval, namespace, feature_key, value
        FROM features
        WHERE instrument = %s
          AND interval = %s
          AND time = %s
    """
    params: list[Any] = [instrument, interval, timestamp_utc]
    if namespace is not None:
        sql += " AND namespace = %s"
        params.append(namespace)
    sql += " ORDER BY namespace ASC, feature_key ASC"

    cursor = connection.cursor()
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    return [
        FeatureRecord(
            time=row[0],
            instrument=row[1],
            interval=row[2],
            namespace=row[3],
            feature_key=row[4],
            value=float(row[5]),
        )
        for row in rows
    ]


def query_feature_metadata_registry(
    connection: ConnectionLike,
    *,
    namespace: str | None = None,
    provider: str | None = None,
) -> list[FeatureMetadata]:
    sql = """
        SELECT namespace, feature_key, display_name, description, unit, params, provider
        FROM feature_metadata
        WHERE 1 = 1
    """
    params: list[Any] = []
    if namespace is not None:
        sql += " AND namespace = %s"
        params.append(namespace)
    if provider is not None:
        sql += " AND provider = %s"
        params.append(provider)
    sql += " ORDER BY namespace ASC, feature_key ASC"

    cursor = connection.cursor()
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()

    out: list[FeatureMetadata] = []
    for row in rows:
        params_value = row[5] if isinstance(row[5], dict) else {}
        out.append(
            FeatureMetadata(
                namespace=row[0],
                feature_key=row[1],
                display_name=row[2],
                description=row[3] or "",
                unit=row[4],
                params=params_value,
                provider=row[6],
            )
        )
    return out
