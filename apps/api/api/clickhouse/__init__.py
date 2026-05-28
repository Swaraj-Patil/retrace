"""ClickHouse access layer (traces store)."""

from api.clickhouse.client import get_client

__all__ = ["get_client"]
