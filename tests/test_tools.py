"""Tools and rule checks against the test database. No LLM involved."""

import json

import pytest

from app import config
from app.tools.base import Session
from app.tools.registry import run_tool, schemas
from app.tools.status import mask_address, mask_name


def verify(conn, session, waybill, last4):
    result = run_tool(conn, session, "verify_receiver", {"waybill": waybill, "mobile_last4": last4})
    for k, v in result.session_updates.items():
        setattr(session, k, v)
    return result.data


def status(conn, session, waybill):
    return run_tool(conn, session, "get_shipment_status", {"waybill": waybill}).data


def test_verify_then_status(conn, shipment):
    s = Session("c1")
    assert status(conn, s, shipment["waybill"])["reason"] == "NOT_VERIFIED"

    res = verify(conn, s, shipment["waybill"].lower().replace("-", " "), shipment["last4"])
    assert res["ok"] and s.verified_waybills == [shipment["waybill"]]

    data = status(conn, s, shipment["waybill"])
    assert data["ok"] and data["status"] == "at_hub"
    assert data["latest_tracking"][-1]["status"] == "at_hub"


def test_status_never_leaks_full_address_or_mobile(conn, shipment, receivers):
    s = Session("c1", verified_waybills=[shipment["waybill"]])
    text = json.dumps(status(conn, s, shipment["waybill"]), ensure_ascii=False)
    house_part = shipment["destination_address"].split(", Brgy.")[0]
    mobile = receivers[shipment["receiver_id"]]["mobile"]
    assert house_part not in text
    assert mobile not in text
    assert receivers[shipment["receiver_id"]]["full_name"] not in text


def test_verifying_one_waybill_does_not_unlock_another(conn, seeded, shipment):
    other = next(x for x in seeded.shipments if x["waybill"] != shipment["waybill"])
    s = Session("c1")
    verify(conn, s, shipment["waybill"], shipment["last4"])
    assert status(conn, s, other["waybill"])["reason"] == "NOT_VERIFIED"


def test_wrong_digits_and_unknown_waybill_look_the_same(conn, shipment):
    s = Session("c1")
    wrong = verify(conn, s, shipment["waybill"], "0000" if shipment["last4"] != "0000" else "1111")
    unknown = verify(conn, s, "TRK-99999", "1234")
    assert wrong["reason"] == unknown["reason"] == "VERIFICATION_FAILED"
    assert wrong["message"] == unknown["message"]
    assert s.failed_verifications == 2


def test_locked_out_after_three_failures(conn, shipment):
    s = Session("c1")
    for _ in range(3):
        assert verify(conn, s, "TRK-99999", "1234")["reason"] == "VERIFICATION_FAILED"
    # even the right digits are refused now
    assert verify(conn, s, shipment["waybill"], shipment["last4"])["reason"] == "LOCKED_OUT"
    assert s.verified_waybills == []


@pytest.mark.parametrize("waybill,last4", [("hello", "1234"), ("TRK-10001", "12"), ("", "")])
def test_bad_input_does_not_count_as_a_try(conn, waybill, last4):
    s = Session("c1")
    assert verify(conn, s, waybill, last4)["reason"] == "INVALID_INPUT"
    assert s.failed_verifications == 0


def test_rules_off_is_the_unprotected_baseline(conn, shipment, monkeypatch):
    monkeypatch.setattr(config, "ENFORCE_RULES", False)
    assert status(conn, Session("c1"), shipment["waybill"])["ok"]


def test_bad_arguments_and_unknown_tool(conn):
    missing_arg = run_tool(conn, Session("c1"), "get_shipment_status", {})
    assert missing_arg.data["reason"] == "BAD_ARGUMENTS"
    assert run_tool(conn, Session("c1"), "delete_everything", {}).data["reason"] == "UNKNOWN_TOOL"


def test_schemas_are_clean():
    names = {t["function"]["name"] for t in schemas()}
    assert names == {
        "verify_receiver",
        "get_shipment_status",
        "list_reschedule_slots",
        "reschedule_delivery",
        "open_claim",
        "handoff_to_human",
    }
    verify_schema = next(t for t in schemas() if t["function"]["name"] == "verify_receiver")
    assert verify_schema["function"]["parameters"]["required"] == ["waybill", "mobile_last4"]


@pytest.mark.parametrize(
    "address,expected",
    [
        ("Blk 3 Lot 7, Mabuhay Homes, Brgy. Anabu, Imus, Cavite", "Brgy. Anabu, Imus, Cavite"),
        ("12 Rizal St., Brgy. Real, Calamba, Laguna", "Brgy. Real, Calamba, Laguna"),
    ],
)
def test_mask_address(address, expected):
    assert mask_address(address) == expected


def test_mask_name():
    assert mask_name("Ma. Cristina R. Dela Cruz") == "Ma. Cristina D."
    assert mask_name("John Paul De Guzman") == "John Paul D."
    assert mask_name("Paolo T. Hernandez") == "Paolo H."
    assert mask_name("Paolo") == "Paolo"
