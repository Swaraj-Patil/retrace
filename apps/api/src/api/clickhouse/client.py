"""Thin wrapper around clickhouse-connect for the rest of the app."""

from __future__ import annotations

from functools import lru_cache

from clickhouse_connect import get_client as _get_client
from clickhouse_connect.driver.client import Client

from api.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a process-wide ClickHouse HTTP client."""
    s = get_settings()
    return _get_client(
        host=s.clickhouse_host,
        port=s.clickhouse_http_port,
        username=s.clickhouse_user,
        password=s.clickhouse_password,
        database=s.clickhouse_database,
    )
