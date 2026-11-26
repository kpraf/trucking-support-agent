"""Write tools and their rules against the test database (reset before each test)."""

from datetime import timedelta

import pytest

from app import config
from app.rules.checks import RESCHEDULABLE
from app.tools.base import Session
from app.tools.registry import run_tool
from tests.conftest import SEED_TODAY


def run(conn, session, name, **args):
    result = run_tool(conn, session, name, args)
    for key, value in result.session_updates.items():
        setattr(session, key, value)
    return result.data


def pick(data, **want):
    def matches(s):
        if "status" in want and s["status"] != want["status"]:
            return False
        if "max_count" in want and s["reschedule_count"] > want["max_count"]:
            return False
        if "count" in want and s["reschedule_count"] != want["count"]:
            return False
        if "delivered_days_ago" in want:
            lo, hi = want["delivered_days_ago"]
            age = (SEED_TODAY - s["delivered_at"].astimezone(config.MANILA).date()).days
            return lo <= age <= hi
        return True

    return next(s for s in data.shipments if matches(s))


def session_for(shipment, turn=1, said="pwede po ba?"):
    return Session(
        "conv-test", verified_waybills=[shipment["waybill"]], turn=turn, last_customer_message=said
    )


def db_shipment(conn, waybill):
    return conn.execute(
        "SELECT scheduled_date, reschedule_count FROM shipments WHERE waybill = %s", (waybill,)
    ).fetchone()


def count(conn, table, waybill):
    sql = f"SELECT count(*) AS n FROM {table} WHERE waybill = %s"
    return conn.execute(sql, (waybill,)).fetchone()["n"]


def next_customer_turn(session, said):
    session.turn += 1
    session.last_customer_message = said


# ---- reschedule -----------------------------------------------------------------


def test_reschedule_writes_only_after_a_yes_in_a_later_turn(fresh_db, conn):
    s = pick(fresh_db, status="at_hub", max_count=1)
    wb, before = s["waybill"], db_shipment(conn, s["waybill"])
    sess = session_for(s)

    slots = run(conn, sess, "list_reschedule_slots", waybill=wb)["available_dates"]
    new_date = slots[-1]["date"]

    first = run(conn, sess, "reschedule_delivery", waybill=wb, new_date=new_date)
    assert (
        first["reason"] == "CONFIRMATION_REQUIRED" and new_date[-2:].lstrip("0") in first["summary"]
    )
    # calling again in the same turn (the model skipping the question) still writes nothing
    again = run(conn, sess, "reschedule_delivery", waybill=wb, new_date=new_date)
    assert again["reason"] == "CONFIRMATION_REQUIRED"
    assert db_shipment(conn, wb) == before

    next_customer_turn(sess, "oo sige po")
    done = run(conn, sess, "reschedule_delivery", waybill=wb, new_date=new_date)
    assert done["ok"], done
    after = db_shipment(conn, wb)
    assert after["scheduled_date"].isoformat() == new_date
    assert after["reschedule_count"] == before["reschedule_count"] + 1
    assert count(conn, "reschedules", wb) == before["reschedule_count"] + 1
    assert sess.pending_action is None


def test_customer_says_no(fresh_db, conn):
    s = pick(fresh_db, status="booked", max_count=1)
    sess = session_for(s)
    new_date = run(conn, sess, "list_reschedule_slots", waybill=s["waybill"])["available_dates"][0]
    run(conn, sess, "reschedule_delivery", waybill=s["waybill"], new_date=new_date["date"])

    next_customer_turn(sess, "ay hindi, wag na po")
    res = run(conn, sess, "reschedule_delivery", waybill=s["waybill"], new_date=new_date["date"])
    assert res["reason"] == "CUSTOMER_DECLINED"
    assert db_shipment(conn, s["waybill"])["scheduled_date"] == s["scheduled_date"]
    assert sess.pending_action is None


def test_a_different_date_needs_its_own_yes(fresh_db, conn):
    s = pick(fresh_db, status="at_hub", max_count=1)
    sess = session_for(s)
    slots = run(conn, sess, "list_reschedule_slots", waybill=s["waybill"])["available_dates"]
    run(conn, sess, "reschedule_delivery", waybill=s["waybill"], new_date=slots[0]["date"])

    next_customer_turn(sess, "oo")
    res = run(conn, sess, "reschedule_delivery", waybill=s["waybill"], new_date=slots[1]["date"])
    assert res["reason"] == "CONFIRMATION_REQUIRED"
    assert db_shipment(conn, s["waybill"])["scheduled_date"] == s["scheduled_date"]


def test_reschedule_rules(fresh_db, conn):
    out = pick(fresh_db, status="out_for_delivery")
    at_limit = next(
        s for s in fresh_db.shipments if s["status"] in RESCHEDULABLE and s["reschedule_count"] == 2
    )
    ok_one = pick(fresh_db, status="at_hub", max_count=1)
    tomorrow = (SEED_TODAY + timedelta(days=1)).isoformat()

    def try_move(s, d):
        return run(conn, session_for(s), "reschedule_delivery", waybill=s["waybill"], new_date=d)

    assert try_move(out, tomorrow)["reason"] == "STATUS_NOT_ALLOWED"
    assert try_move(at_limit, tomorrow)["reason"] == "RESCHEDULE_LIMIT"
    sunday = SEED_TODAY + timedelta(days=(6 - SEED_TODAY.weekday()) % 7 or 7)
    for bad in [sunday, SEED_TODAY, SEED_TODAY + timedelta(days=10), ok_one["scheduled_date"]]:
        assert try_move(ok_one, bad.isoformat())["reason"] == "DATE_NOT_ALLOWED", bad
    assert try_move(ok_one, "next saturday")["reason"] == "INVALID_INPUT"

    stranger = Session("conv-x", turn=1)
    res = run(conn, stranger, "reschedule_delivery", waybill=ok_one["waybill"], new_date=tomorrow)
    assert res["reason"] == "NOT_VERIFIED"


def test_rules_off_baseline_writes_without_asking(fresh_db, conn, monkeypatch):
    """v0 baseline: no checks, so even a bad write goes straight through."""
    monkeypatch.setattr(config, "ENFORCE_RULES", False)
    out = pick(fresh_db, status="out_for_delivery")
    far = (SEED_TODAY + timedelta(days=30)).isoformat()
    res = run(
        conn, Session("c", turn=1), "reschedule_delivery", waybill=out["waybill"], new_date=far
    )
    assert res["ok"]
    assert db_shipment(conn, out["waybill"])["scheduled_date"].isoformat() == far


# ---- claims ---------------------------------------------------------------------


def test_claim_is_filed_with_a_handoff_after_yes(fresh_db, conn):
    s = pick(fresh_db, status="delivered", delivered_days_ago=(0, 5))
    sess = session_for(s)
    args = dict(waybill=s["waybill"], claim_type="damaged", description="basag yung salamin")

    assert run(conn, sess, "open_claim", **args)["reason"] == "CONFIRMATION_REQUIRED"
    assert count(conn, "claims", s["waybill"]) == 0

    next_customer_turn(sess, "opo")
    reworded = args | {"description": "Basag po yung salamin ng cabinet"}
    res = run(conn, sess, "open_claim", **reworded)
    assert res["ok"] and res["claim_ref"].startswith("CLM-")
    assert count(conn, "claims", s["waybill"]) == 1
    handoff = conn.execute(
        "SELECT conversation_id, reason FROM handoffs WHERE waybill = %s", (s["waybill"],)
    ).fetchone()
    assert handoff["conversation_id"] == "conv-test" and "claim" in handoff["reason"]
    assert sess.handed_off

    assert run(conn, sess, "open_claim", **args)["reason"] == "CLAIM_ALREADY_OPEN"


def test_claim_rules(fresh_db, conn):
    old = pick(fresh_db, status="delivered", delivered_days_ago=(8, 60))
    failed = pick(fresh_db, status="failed_attempt")
    hub = pick(fresh_db, status="at_hub")

    def claim(s, kind):
        args = dict(waybill=s["waybill"], claim_type=kind, description="x")
        return run(conn, session_for(s), "open_claim", **args)

    assert claim(old, "damaged")["reason"] == "CLAIM_WINDOW_CLOSED"
    assert claim(failed, "damaged")["reason"] == "CLAIM_TYPE_NOT_ALLOWED"
    assert claim(hub, "missing_item")["reason"] == "CLAIM_TYPE_NOT_ALLOWED"
    assert claim(failed, "failed_delivery_dispute")["reason"] == "CONFIRMATION_REQUIRED"


# ---- handoffs -------------------------------------------------------------------


def test_handoff_once_per_conversation(fresh_db, conn):
    sess = Session("conv-h", turn=1)
    assert run(conn, sess, "handoff_to_human", reason="wants a person", waybill="TRK-99999")["ok"]
    assert run(conn, sess, "handoff_to_human", reason="again")["ok"]
    rows = conn.execute("SELECT waybill FROM handoffs WHERE conversation_id = 'conv-h'").fetchall()
    assert rows == [{"waybill": None}]  # one row, and the made-up waybill wasn't stored


def test_three_failed_tries_hand_off_automatically(fresh_db, conn):
    sess = Session("conv-lock", turn=1)
    for _ in range(3):
        res = run(conn, sess, "verify_receiver", waybill="TRK-99999", mobile_last4="1234")
    assert res["tries_left"] == 0 and sess.handed_off
    n = conn.execute("SELECT count(*) AS n FROM handoffs WHERE conversation_id = 'conv-lock'")
    assert n.fetchone()["n"] == 1


@pytest.mark.parametrize("tool", ["reschedule_delivery", "open_claim"])
def test_writes_need_verification(fresh_db, conn, tool):
    s = pick(fresh_db, status="delivered", delivered_days_ago=(0, 5))
    args = (
        {"new_date": (SEED_TODAY + timedelta(days=1)).isoformat()}
        if tool == "reschedule_delivery"
        else {"claim_type": "damaged", "description": "x"}
    )
    res = run(conn, Session("c", turn=1), tool, waybill=s["waybill"], **args)
    assert res["reason"] == "NOT_VERIFIED"
