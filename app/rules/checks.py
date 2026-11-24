"""Company rules enforced in code, before a tool touches data.

A failed check returns a reason code. The tool sends that code back to the agent instead of
doing the action, and the agent explains it to the customer. With ENFORCE_RULES off (v0
baseline only) every check passes and only the prompt keeps the agent in line.
"""

from enum import StrEnum

from app import config

MAX_VERIFY_ATTEMPTS = 3


class Reason(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"  # asked for a shipment the receiver hasn't verified
    VERIFICATION_FAILED = "VERIFICATION_FAILED"  # waybill + last 4 digits didn't match
    LOCKED_OUT = "LOCKED_OUT"  # too many failed tries, a human has to take over
    INVALID_INPUT = "INVALID_INPUT"  # malformed waybill or last 4 (doesn't count as a try)
    NOT_FOUND = "NOT_FOUND"  # only reachable with rules off


def check_can_try_verify(failed_attempts: int) -> Reason | None:
    if config.ENFORCE_RULES and failed_attempts >= MAX_VERIFY_ATTEMPTS:
        return Reason.LOCKED_OUT
    return None


def check_can_view(waybill: str, verified_waybills: list[str]) -> Reason | None:
    """Rule 1: no shipment details until that waybill is verified."""
    if config.ENFORCE_RULES and waybill not in verified_waybills:
        return Reason.NOT_VERIFIED
    return None
