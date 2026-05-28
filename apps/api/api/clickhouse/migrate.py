"""Tiny SQL migration runner for ClickHouse.

Migration files live in ``migrations/`` next to this module, named
``NNNN_description.sql`` where ``NNNN`` is a zero-padded integer. A
``_schema_migrations`` table records which versions have been applied; on each
run, every unapplied file is executed in order. Statements inside a file are
split on ``;`` and run sequentially.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from clickhouse_connect.driver.client import Client

from api.clickhouse.client import get_client

logger = logging.getLogger("retrace.clickhouse.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
TRACKER_TABLE = "_schema_migrations"


def _ensure_tracker(client: Client) -> None:
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {TRACKER_TABLE}
        (
            version    String,
            applied_at DateTime64(3, 'UTC') DEFAULT now64(3)
        )
        ENGINE = MergeTree
        ORDER BY version
        """
    )


def _applied_versions(client: Client) -> set[str]:
    rows = client.query(f"SELECT version FROM {TRACKER_TABLE}").result_rows
    return {row[0] for row in rows}


def _discover_migrations() -> list[tuple[str, Path]]:
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    return [(p.stem, p) for p in files]


def _split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for raw_line in sql.splitlines():
        line = raw_line.rstrip()
        # Drop full-line SQL comments so they do not become empty statements.
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _apply(client: Client, version: str, path: Path) -> None:
    logger.info("applying %s", version)
    sql = path.read_text(encoding="utf-8")
    for statement in _split_statements(sql):
        client.command(statement)
    client.command(
        f"INSERT INTO {TRACKER_TABLE} (version) VALUES",
        data=[[version]],
    )


def run_migrations() -> list[str]:
    """Apply all pending migrations. Return the list of versions applied."""
    client = get_client()
    _ensure_tracker(client)
    applied = _applied_versions(client)
    discovered = _discover_migrations()

    pending = [(v, p) for v, p in discovered if v not in applied]
    if not pending:
        logger.info("no pending migrations (%d already applied)", len(applied))
        return []

    for version, path in pending:
        _apply(client, version, path)

    return [v for v, _ in pending]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    applied = run_migrations()
    if applied:
        print("Applied:", ", ".join(applied))
    else:
        print("Up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
