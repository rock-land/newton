from pathlib import Path

from src.data.database import DEFAULT_MIGRATIONS_DIR, bootstrap_database, discover_migrations


def test_discover_migrations_returns_expected_bootstrap_file() -> None:
    migrations = discover_migrations(DEFAULT_MIGRATIONS_DIR)
    assert migrations
    assert migrations[0].version == "0001"
    assert migrations[0].name == "timescaledb_bootstrap"


def test_bootstrap_database_dry_run_returns_sorted_versions() -> None:
    planned = bootstrap_database("postgresql://ignored", dry_run=True)
    assert planned == sorted(planned)
    assert "0001" in planned


def test_bootstrap_sql_contains_hypertables_and_core_tables() -> None:
    sql_path = Path(DEFAULT_MIGRATIONS_DIR) / "0001_timescaledb_bootstrap.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS timescaledb;" in sql
    assert "create_hypertable('ohlcv', 'time', if_not_exists => TRUE" in sql
    assert "create_hypertable('features', 'time', if_not_exists => TRUE" in sql

    for table_name in [
        "ohlcv",
        "features",
        "feature_metadata",
        "events",
        "tokens",
        "trades",
        "reconciliation_log",
        "regime_log",
        "strategy_versions",
        "spec_deviations",
        "config_changes",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql
