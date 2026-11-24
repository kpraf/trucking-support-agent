"""Database connections: one short-lived connection per request (add a pool if needed)."""

from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from app import config


def connect(url: str | None = None, **kwargs) -> psycopg.Connection:
    """Connect with dict rows. Timestamps come back tz-aware (UTC); show them with config.MANILA."""
    url = url or config.DATABASE_URL
    return psycopg.connect(url, row_factory=dict_row, autocommit=True, **kwargs)


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency."""
    with connect() as conn:
        yield conn
