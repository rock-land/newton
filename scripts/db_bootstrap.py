#!/usr/bin/env python3
"""Bootstrap Newton database migrations."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.database import bootstrap_database  # noqa: E402


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
    env_path = ROOT / ".env"
    db_url = read_database_url(env_path)
    applied = bootstrap_database(db_url)
    print("MIGRATIONS_APPLIED", applied)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
