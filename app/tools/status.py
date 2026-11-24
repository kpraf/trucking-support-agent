from datetime import date, datetime

from pydantic import BaseModel, Field

from app import config
from app.db import queries
from app.rules.checks import Reason, check_can_view
from app.tools.base import Conn, Session, ToolResult, ok, refused

STATUS_MEANINGS = {
    "booked": "Booked, waiting for pickup from the shipper",
    "picked_up": "Picked up from the shipper, on the way to our hub",
    "at_hub": "At our hub, waiting to go out for delivery",
    "out_for_delivery": "Out for delivery today",
    "delivered": "Delivered",
    "failed_attempt": "Delivery was attempted but not completed",
    "on_hold": "On hold at the hub",
    "returned_to_shipper": "Returned to the shipper",
}


class GetShipmentStatus(BaseModel):
    """Get the current status, delivery schedule and latest tracking events of a shipment
    the customer has already verified."""

    waybill: str = Field(description="A waybill the customer has already verified")


def mask_address(address: str) -> str:
    """Rule 2: drop the house, lot and street part. Keep barangay, city and province."""
    _, sep, rest = address.partition("Brgy. ")
    return f"Brgy. {rest}" if sep else address.split(", ", 1)[-1]


SURNAME_PREFIXES = {"de", "dela", "del", "delos", "san", "santa", "sta."}


def mask_name(full_name: str) -> str:
    """Given name plus last-name initial: "Ma. Cristina R. Dela Cruz" -> "Ma. Cristina D."."""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    surname_start = len(parts) - 1
    if len(parts) > 2 and parts[-2].lower() in SURNAME_PREFIXES:
        surname_start -= 1
    # drop a middle initial like "R." (but keep "Ma." as part of the given name)
    given = [p for i, p in enumerate(parts[:surname_start]) if i == 0 or len(p) > 2]
    return f"{' '.join(given)} {parts[surname_start][0]}."


def _day(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


def _when(ts: datetime) -> str:
    t = ts.astimezone(config.MANILA)
    return f"{t:%a}, {t:%b} {t.day}, {t:%I:%M %p}".replace(" 0", " ")


def get_shipment_status(conn: Conn, session: Session, waybill: str) -> ToolResult:
    canonical = queries.normalize_waybill(waybill)
    if canonical is None:
        return ToolResult(refused(Reason.INVALID_INPUT, "That is not a waybill like TRK-12345."))
    if reason := check_can_view(canonical, session.verified_waybills):
        return ToolResult(
            refused(reason, "Verify this waybill first: waybill plus last 4 mobile digits.")
        )

    s = queries.get_shipment(conn, canonical)
    if s is None:
        return ToolResult(refused(Reason.NOT_FOUND, "No shipment with that waybill."))
    events = queries.get_shipment_events(conn, canonical)

    item = s["item_description"]
    if not any(ch.isdigit() for ch in item):  # "20 bags" etc. already says how many
        item += f" ({s['pieces']} pc{'s' if s['pieces'] > 1 else ''})"
    return ToolResult(
        ok(
            waybill=canonical,
            status=s["status"],
            status_meaning=STATUS_MEANINGS[s["status"]],
            receiver=mask_name(s["receiver_name"]),
            shipper=s["shipper_name"],
            item=item,
            delivery_area=mask_address(s["destination_address"]),
            scheduled_date=_day(s["scheduled_date"]) if s["scheduled_date"] else None,
            delivered_at=_when(s["delivered_at"]) if s["delivered_at"] else None,
            times_rescheduled=s["reschedule_count"],
            latest_tracking=[
                {
                    "when": _when(e["occurred_at"]),
                    "status": e["status"],
                    "location": e["location"],
                    "note": e["note"],
                }
                for e in events[-4:]
            ],
        )
    )
