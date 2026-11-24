"""API tests against a real Postgres. Skipped when the server isn't running.

Uses a separate `<dbname>_test` database on the same server, so your dev data is untouched.
"""

from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app import config
from app.db.connection import connect
from app.db.seed import reset_database


@pytest.fixture(scope="module")
def seeded():
    params = conninfo_to_dict(config.DATABASE_URL)
    test_db = f"{params.get('dbname', 'trucking')}_test"
    try:
        admin = connect(make_conninfo(config.DATABASE_URL, dbname="postgres"), connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run: docker compose up -d)")
    with admin:
        exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,))
        if exists.fetchone() is None:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_db)))

    test_url = make_conninfo(config.DATABASE_URL, dbname=test_db)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DATABASE_URL", test_url)
        with connect() as conn:
            data = reset_database(conn, date(2026, 12, 2), seed=42)
        yield data


@pytest.fixture(scope="module")
def client(seeded):
    from app.api.main import app

    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_get_shipment(client, seeded):
    expected = seeded.shipments[0]
    res = client.get(f"/dev/shipments/{expected['waybill'].lower().replace('-', '')}")
    assert res.status_code == 200
    body = res.json()
    assert body["waybill"] == expected["waybill"]
    assert body["status"] == expected["status"]
    assert body["events"][-1]["status"] == expected["status"]
    assert body["events"][0]["occurred_at"].endswith("+08:00")


def test_unknown_waybill(client, seeded):
    assert client.get("/dev/shipments/TRK-99999").status_code == 404


def test_bad_waybill(client, seeded):
    assert client.get("/dev/shipments/hello").status_code == 422
