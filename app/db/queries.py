"""Read queries. Tools and API routes call these; nothing else writes SQL."""

import re

import psycopg

_WAYBILL_RE = re.compile(r"^\s*TRK[\s-]*(\d{5})\s*$", re.IGNORECASE)


def normalize_waybill(raw: str) -> str | None:
    """Accept what people actually type ("trk10293", "TRK 10293", "TRK-10293").

    Returns the canonical "TRK-10293", or None if it doesn't look like a waybill.
    """
    m = _WAYBILL_RE.match(raw)
    return f"TRK-{m.group(1)}" if m else None


def get_shipment(conn: psycopg.Connection, waybill: str) -> dict | None:
    return conn.execute(
        """
        SELECT s.*, r.full_name AS receiver_name, r.mobile AS receiver_mobile
        FROM shipments s
        JOIN receivers r ON r.id = s.receiver_id
        WHERE s.waybill = %s
        """,
        (waybill,),
    ).fetchone()


def get_shipment_events(conn: psycopg.Connection, waybill: str) -> list[dict]:
    return conn.execute(
        """
        SELECT occurred_at, status, location, note
        FROM shipment_events
        WHERE waybill = %s
        ORDER BY occurred_at, id
        """,
        (waybill,),
    ).fetchall()
