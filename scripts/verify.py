"""Connect to both databases, print row counts, exit non-zero on problems.

Usage:
    uv run python scripts/verify.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from sqlalchemy import text  # noqa: E402

from api.clickhouse.client import get_client  # noqa: E402
from api.db.session import SessionLocal, engine  # noqa: E402

PG_TABLES = ["orgs", "users", "memberships", "projects", "api_keys"]
CH_TABLES = ["traces", "retrievals", "retrieved_chunks", "citations"]


async def _pg_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    async with SessionLocal() as session:
        for table in PG_TABLES:
            row = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = int(row.scalar_one())
    return counts


def _ch_counts() -> dict[str, int]:
    client = get_client()
    counts: dict[str, int] = {}
    for table in CH_TABLES:
        result = client.query(f"SELECT COUNT(*) FROM {table}")
        counts[table] = int(result.result_rows[0][0])
    return counts


def _report(name: str, counts: dict[str, int]) -> bool:
    print(f"{name}:")
    ok = True
    for table, n in counts.items():
        mark = "OK" if n > 0 else "EMPTY"
        if n == 0:
            ok = False
        print(f"  {table:<20} {n:>6}  {mark}")
    return ok


async def main() -> int:
    try:
        pg = await _pg_counts()
    except Exception as exc:
        print(f"Postgres connection failed: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

    try:
        ch = _ch_counts()
    except Exception as exc:
        print(f"ClickHouse connection failed: {exc}", file=sys.stderr)
        return 2

    pg_ok = _report("Postgres", pg)
    print()
    ch_ok = _report("ClickHouse", ch)

    if not (pg_ok and ch_ok):
        print("\nOne or more tables are empty. Did you run `make seed`?", file=sys.stderr)
        return 1

    print("\nAll tables populated.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
