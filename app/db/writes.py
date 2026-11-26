"""Writes. Each function runs in one transaction, so a failure leaves nothing half-done.

Tools call these only after the rule checks and the customer's confirmation passed.
"""

from datetime import date

import psycopg

from app.db.seed_data import HUBS


def reschedule(conn: psycopg.Connection, waybill: str, new_date: date) -> dict:
    with conn.transaction():
        s = conn.execute(
            "SELECT status, scheduled_date, destination_city FROM shipments "
            "WHERE waybill = %s FOR UPDATE",
            (waybill,),
        ).fetchone()
        old_date = s["scheduled_date"]
        conn.execute(
            "UPDATE shipments SET scheduled_date = %s, reschedule_count = reschedule_count + 1 "
            "WHERE waybill = %s",
            (new_date, waybill),
        )
        conn.execute(
            "INSERT INTO reschedules (waybill, old_date, new_date) VALUES (%s, %s, %s)",
            (waybill, old_date or new_date, new_date),
        )
        conn.execute(
            "INSERT INTO shipment_events (waybill, occurred_at, status, location, note) "
            "VALUES (%s, now(), %s, %s, %s)",
            (
                waybill,
                s["status"],
                HUBS.get(s["destination_city"], "Hub"),
                f"Rescheduled by receiver: {old_date} to {new_date}",
            ),
        )
    return {"old_date": old_date, "new_date": new_date}


def get_open_claim(conn: psycopg.Connection, waybill: str) -> dict | None:
    return conn.execute(
        "SELECT id, type, status FROM claims "
        "WHERE waybill = %s AND status IN ('open', 'in_review') ORDER BY id LIMIT 1",
        (waybill,),
    ).fetchone()


def open_claim_with_handoff(
    conn: psycopg.Connection, waybill: str, claim_type: str, description: str, conversation_id: str
) -> dict:
    """Rule 5: the agent opens the claim and a human takes over, in one step."""
    with conn.transaction():
        claim = conn.execute(
            "INSERT INTO claims (waybill, type, description) VALUES (%s, %s, %s) RETURNING id",
            (waybill, claim_type, description),
        ).fetchone()
        handoff = insert_handoff(
            conn, waybill, f"claim {claim['id']} ({claim_type})", conversation_id
        )
    return {"claim_id": claim["id"], "handoff_id": handoff["id"]}


def insert_handoff(
    conn: psycopg.Connection, waybill: str | None, reason: str, conversation_id: str
) -> dict:
    return conn.execute(
        "INSERT INTO handoffs (waybill, reason, conversation_id) VALUES (%s, %s, %s) RETURNING id",
        (waybill, reason, conversation_id),
    ).fetchone()
