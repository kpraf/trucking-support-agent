"""Shared fixtures.

`seeded` points the app at a separate `<dbname>_test` database on the same server (so dev data
is untouched), resets it to a fixed seed, and skips the test when Postgres isn't running.
"""

from datetime import date

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app import config
from app.db.connection import connect
from app.db.seed import reset_database

SEED_TODAY = date(2026, 12, 2)  # a Wednesday


@pytest.fixture(scope="session")
def seeded():
    test_db = f"{conninfo_to_dict(config.DATABASE_URL).get('dbname', 'trucking')}_test"
    try:
        admin = connect(make_conninfo(config.DATABASE_URL, dbname="postgres"), connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run: docker compose up -d)")
    with admin:
        exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,))
        if exists.fetchone() is None:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_db)))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DATABASE_URL", make_conninfo(config.DATABASE_URL, dbname=test_db))
        mp.setattr(config, "ENFORCE_RULES", True)
        with connect() as conn:
            data = reset_database(conn, SEED_TODAY, seed=42)
        yield data


@pytest.fixture
def conn(seeded):
    with connect() as c:
        yield c


@pytest.fixture
def receivers(seeded):
    return {r["id"]: r for r in seeded.receivers}


@pytest.fixture
def shipment(seeded, receivers):
    """An at_hub shipment plus the last 4 digits of its receiver's mobile."""
    s = next(s for s in seeded.shipments if s["status"] == "at_hub")
    return s | {"last4": receivers[s["receiver_id"]]["mobile"][-4:]}
