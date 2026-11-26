"""Company rules enforced in code, before a tool touches data.

A failed check returns a reason code. The tool sends that code back to the agent instead of
doing the action, and the agent explains it to the customer. With ENFORCE_RULES off (v0
baseline only) every check passes and only the prompt keeps the agent in line.
"""

from datetime import date, timedelta
from enum import StrEnum

from app import config
from app.rules.confirm import Answer, classify_answer

MAX_VERIFY_ATTEMPTS = 3
MAX_RESCHEDULES = 2
RESCHEDULE_WINDOW_DAYS = 7
CLAIM_WINDOW_DAYS = 7
RESCHEDULABLE = {"booked", "at_hub", "failed_attempt", "on_hold"}
CLAIM_TYPES_BY_STATUS = {
    "delivered": {"damaged", "missing_item"},
    "failed_attempt": {"failed_delivery_dispute"},
}


class Reason(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"  # asked for a shipment the receiver hasn't verified
    VERIFICATION_FAILED = "VERIFICATION_FAILED"  # waybill + last 4 digits didn't match
    LOCKED_OUT = "LOCKED_OUT"  # too many failed tries, a human has taken over
    INVALID_INPUT = "INVALID_INPUT"  # malformed waybill, digits or date (not counted as a try)
    NOT_FOUND = "NOT_FOUND"  # only reachable with rules off
    STATUS_NOT_ALLOWED = "STATUS_NOT_ALLOWED"  # e.g. rescheduling something out for delivery
    RESCHEDULE_LIMIT = "RESCHEDULE_LIMIT"  # already moved twice
    DATE_NOT_ALLOWED = "DATE_NOT_ALLOWED"  # outside the next 7 days, a Sunday, or the same day
    CLAIM_TYPE_NOT_ALLOWED = "CLAIM_TYPE_NOT_ALLOWED"  # wrong claim type for the status
    CLAIM_WINDOW_CLOSED = "CLAIM_WINDOW_CLOSED"  # more than 7 days after delivery
    CLAIM_ALREADY_OPEN = "CLAIM_ALREADY_OPEN"  # one open claim per shipment
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"  # nothing written yet, ask for a yes
    CUSTOMER_DECLINED = "CUSTOMER_DECLINED"  # customer said no, nothing written


def check_can_try_verify(failed_attempts: int) -> Reason | None:
    if config.ENFORCE_RULES and failed_attempts >= MAX_VERIFY_ATTEMPTS:
        return Reason.LOCKED_OUT
    return None


def check_can_view(waybill: str, verified_waybills: list[str]) -> Reason | None:
    """Rule 1: no shipment details (or changes) until that waybill is verified."""
    if config.ENFORCE_RULES and waybill not in verified_waybills:
        return Reason.NOT_VERIFIED
    return None


def reschedule_dates(today: date) -> list[date]:
    """Rule 3: the next 7 days after today, Monday to Saturday."""
    days = (today + timedelta(days=n) for n in range(1, RESCHEDULE_WINDOW_DAYS + 1))
    return [d for d in days if d.weekday() != 6]


def check_can_reschedule(shipment: dict) -> Reason | None:
    if not config.ENFORCE_RULES:
        return None
    if shipment["status"] not in RESCHEDULABLE:
        return Reason.STATUS_NOT_ALLOWED
    if shipment["reschedule_count"] >= MAX_RESCHEDULES:
        return Reason.RESCHEDULE_LIMIT
    return None


def check_reschedule_date(shipment: dict, new_date: date, today: date) -> Reason | None:
    if not config.ENFORCE_RULES:
        return None
    if new_date not in reschedule_dates(today) or new_date == shipment["scheduled_date"]:
        return Reason.DATE_NOT_ALLOWED
    return None


def check_can_claim(shipment: dict, claim_type: str, today: date) -> Reason | None:
    """Rule 5: damaged/missing only for deliveries in the last 7 days, disputes only for
    failed attempts."""
    if not config.ENFORCE_RULES:
        return None
    if claim_type not in CLAIM_TYPES_BY_STATUS.get(shipment["status"], set()):
        return Reason.CLAIM_TYPE_NOT_ALLOWED
    if shipment["status"] == "delivered":
        delivered = shipment["delivered_at"].astimezone(config.MANILA).date()
        if (today - delivered).days > CLAIM_WINDOW_DAYS:
            return Reason.CLAIM_WINDOW_CLOSED
    return None


def check_confirmed(
    pending: dict | None, action: dict, turn: int, customer_message: str
) -> Reason | None:
    """Rule 6: write only when this exact action was proposed in an earlier turn and the
    customer's reply since then is a clear yes. None means go ahead."""
    if not config.ENFORCE_RULES:
        return None
    proposed_earlier = (
        pending is not None
        and pending["tool"] == action["tool"]
        and pending["key"] == action["key"]
        and pending["turn"] < turn
    )
    if not proposed_earlier:
        return Reason.CONFIRMATION_REQUIRED
    answer = classify_answer(customer_message)
    if answer is Answer.YES:
        return None
    if answer is Answer.NO:
        return Reason.CUSTOMER_DECLINED
    return Reason.CONFIRMATION_REQUIRED
