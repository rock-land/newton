"""TimescaleDB bootstrap and SQL migration runner for Newton Stage 1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    """A SQL migration file."""

    version: str
    name: str
    path: Path


DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def discover_migrations(migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR) -> list[Migration]:
    """Discover and return sorted SQL migrations from the migrations directory."""
    base = Path(migrations_dir)
    files = sorted(base.glob("*.sql"))

    migrations: list[Migration] = []
    for file in files:
        stem = file.stem
        if "_" not in stem:
            msg = f"invalid migration filename '{file.name}' (expected '<version>_<name>.sql')"
            raise ValueError(msg)
        version, name = stem.split("_", 1)
        migrations.append(Migration(version=version, name=name, path=file))
    return migrations


def bootstrap_database(
    db_url: str,
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Apply pending SQL migrations and return the applied migration versions.

    Migration state is tracked in ``public.schema_migrations``.
    """
    migrations = discover_migrations(migrations_dir)
    planned = [m.version for m in migrations]
    if dry_run:
        return planned

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        msg = "psycopg is required to run database migrations; install requirements.txt"
        raise RuntimeError(msg) from exc

    with psycopg.connect(db_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("SELECT version FROM public.schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

            executed: list[str] = []
            for migration in migrations:
                if migration.version in applied:
                    continue

                sql = migration.path.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO public.schema_migrations (version, name) VALUES (%s, %s)",
                    (migration.version, migration.name),
                )
                executed.append(migration.version)

        conn.commit()

    return executed
