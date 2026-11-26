from datetime import date

from pydantic import BaseModel, Field

from app import config
from app.db import queries, writes
from app.rules.checks import (
    MAX_RESCHEDULES,
    Reason,
    check_can_reschedule,
    check_can_view,
    check_reschedule_date,
    reschedule_dates,
)
from app.tools.base import Conn, Session, ToolResult, confirm_or_propose, day_label, ok, refused


class ListRescheduleSlots(BaseModel):
    """List the dates a verified shipment can be moved to. Call this before proposing a
    new delivery date."""

    waybill: str = Field(description="A waybill the customer has already verified")


class RescheduleDelivery(BaseModel):
    """Move a verified shipment to a new delivery date. The first call only proposes the
    change; it is saved only when called again with the same date after the customer says
    yes."""

    waybill: str = Field(description="A waybill the customer has already verified")
    new_date: str = Field(description="New delivery date as YYYY-MM-DD, from the listed slots")


def _load(conn: Conn, session: Session, waybill: str) -> tuple[dict | None, ToolResult | None]:
    canonical = queries.normalize_waybill(waybill)
    if canonical is None:
        return None, ToolResult(refused(Reason.INVALID_INPUT, "Not a waybill like TRK-12345."))
    if reason := check_can_view(canonical, session.verified_waybills):
        return None, ToolResult(refused(reason, "Verify this waybill first."))
    shipment = queries.get_shipment(conn, canonical)
    if shipment is None:
        return None, ToolResult(refused(Reason.NOT_FOUND, "No shipment with that waybill."))
    return shipment, None


def _blocked(shipment: dict) -> ToolResult | None:
    if reason := check_can_reschedule(shipment):
        why = {
            Reason.STATUS_NOT_ALLOWED: f"Can't reschedule while the status is "
            f"{shipment['status']}. Only booked, at hub, failed attempt or on hold.",
            Reason.RESCHEDULE_LIMIT: f"Already rescheduled {MAX_RESCHEDULES} times, the limit.",
        }[reason]
        return ToolResult(refused(reason, why + " Offer a human teammate if they need more help."))
    return None


def list_reschedule_slots(conn: Conn, session: Session, waybill: str) -> ToolResult:
    shipment, error = _load(conn, session, waybill)
    if error:
        return error
    if blocked := _blocked(shipment):
        return blocked
    current = shipment["scheduled_date"]
    slots = [d for d in reschedule_dates(config.today()) if d != current]
    return ToolResult(
        ok(
            waybill=shipment["waybill"],
            current_date=day_label(current) if current else None,
            available_dates=[{"date": d.isoformat(), "label": day_label(d)} for d in slots],
            reschedules_left=max(MAX_RESCHEDULES - shipment["reschedule_count"], 0),
        )
    )


def reschedule_delivery(conn: Conn, session: Session, waybill: str, new_date: str) -> ToolResult:
    try:
        target = date.fromisoformat(new_date.strip())
    except ValueError:
        return ToolResult(refused(Reason.INVALID_INPUT, "new_date must be YYYY-MM-DD."))
    shipment, error = _load(conn, session, waybill)
    if error:
        return error
    if blocked := _blocked(shipment):
        return blocked
    if reason := check_reschedule_date(shipment, target, config.today()):
        return ToolResult(
            refused(
                reason,
                "That date isn't allowed: it must be within the next 7 days, Monday to "
                "Saturday, and different from the current date. Use list_reschedule_slots.",
            )
        )

    wb = shipment["waybill"]
    current = shipment["scheduled_date"]
    summary = (
        f"Move delivery of {wb} from {day_label(current) if current else 'no date'} "
        f"to {day_label(target)}."
    )
    key = {"waybill": wb, "date": target.isoformat()}
    if gate := confirm_or_propose(session, "reschedule_delivery", key, summary):
        return gate

    writes.reschedule(conn, wb, target)
    return ToolResult(
        ok(
            waybill=wb,
            message=f"Done. Delivery moved to {day_label(target)}.",
            new_date=day_label(target),
        ),
        {"pending_action": None},
    )
