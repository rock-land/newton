#!/usr/bin/env python3
"""Show Newton DB/Timescale status."""

from __future__ import annotations

from pathlib import Path
import json
import sys


def read_database_url(env_path: Path) -> str:
    if not env_path.exists():
        raise RuntimeError(f"missing env file: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
            break
    raise RuntimeError("DATABASE_URL not set in .env")


def main() -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg not installed; activate .venv and install requirements") from exc

    root = Path(__file__).resolve().parents[1]
    db_url = read_database_url(root / ".env")

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname='timescaledb'")
            ext_ok = cur.fetchone() is not None

            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
            )
            tables = [r[0] for r in cur.fetchall()]

            cur.execute("SELECT version, name, applied_at FROM public.schema_migrations ORDER BY version")
            migrations = [
                {"version": r[0], "name": r[1], "applied_at": r[2].isoformat()}
                for r in cur.fetchall()
            ]

    print(
        json.dumps(
            {
                "timescaledb_extension": ext_ok,
                "tables": tables,
                "schema_migrations": migrations,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
