"""API tests against the test database (see conftest.py)."""

import pytest
from fastapi.testclient import TestClient


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
