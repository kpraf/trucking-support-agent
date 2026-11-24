import re

from pydantic import BaseModel, Field

from app.db import queries
from app.rules.checks import MAX_VERIFY_ATTEMPTS, Reason, check_can_try_verify
from app.tools.base import Conn, Session, ToolResult, ok, refused


class VerifyReceiver(BaseModel):
    """Check that the customer is the receiver of a shipment. They must give the waybill
    number and the last 4 digits of the mobile number on the shipment. Call this before
    sharing any shipment details."""

    waybill: str = Field(description="Waybill number as the customer gave it, e.g. TRK-10293")
    mobile_last4: str = Field(description="Last 4 digits of the receiver's mobile number")


def verify_receiver(conn: Conn, session: Session, waybill: str, mobile_last4: str) -> ToolResult:
    if reason := check_can_try_verify(session.failed_verifications):
        return ToolResult(
            refused(reason, "Too many failed tries. Do not try again: a human teammate must help.")
        )

    canonical = queries.normalize_waybill(waybill)
    digits = re.sub(r"\D", "", mobile_last4)
    if canonical is None or len(digits) != 4:
        return ToolResult(
            refused(
                Reason.INVALID_INPUT,
                "Need a waybill like TRK-12345 and exactly 4 digits. Ask the customer again.",
            )
        )

    if canonical in session.verified_waybills:
        return ToolResult(ok(waybill=canonical, message="Already verified."))

    shipment = queries.get_shipment(conn, canonical)
    if shipment is None or not shipment["receiver_mobile"].endswith(digits):
        # Same answer for "no such waybill" and "wrong digits", so impostors learn nothing.
        failed = session.failed_verifications + 1
        return ToolResult(
            refused(
                Reason.VERIFICATION_FAILED,
                "The waybill and mobile digits do not match our records.",
                tries_left=max(MAX_VERIFY_ATTEMPTS - failed, 0),
            ),
            {"failed_verifications": failed},
        )

    return ToolResult(
        ok(waybill=canonical, message="Verified. You can now share this shipment's status."),
        {"verified_waybills": [*session.verified_waybills, canonical]},
    )
