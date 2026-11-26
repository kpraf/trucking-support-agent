from typing import Literal

from pydantic import BaseModel, Field

from app import config
from app.db import queries, writes
from app.rules.checks import Reason, check_can_claim, check_can_view
from app.tools.base import Conn, Session, ToolResult, confirm_or_propose, ok, refused

CLAIM_LABELS = {
    "damaged": "damaged item",
    "missing_item": "missing item",
    "failed_delivery_dispute": "failed delivery dispute",
}


class OpenClaim(BaseModel):
    """Open a claim for a verified shipment and hand the case to a human teammate. Use for a
    damaged or missing item after delivery, or to dispute a failed delivery attempt. The first
    call only proposes the claim; it is filed only when called again after the customer says
    yes. Never promise a refund or compensation."""

    waybill: str = Field(description="A waybill the customer has already verified")
    claim_type: Literal["damaged", "missing_item", "failed_delivery_dispute"]
    description: str = Field(description="What happened, in the customer's own words")


def open_claim(
    conn: Conn, session: Session, waybill: str, claim_type: str, description: str
) -> ToolResult:
    canonical = queries.normalize_waybill(waybill)
    if canonical is None:
        return ToolResult(refused(Reason.INVALID_INPUT, "Not a waybill like TRK-12345."))
    if reason := check_can_view(canonical, session.verified_waybills):
        return ToolResult(refused(reason, "Verify this waybill first."))
    shipment = queries.get_shipment(conn, canonical)
    if shipment is None:
        return ToolResult(refused(Reason.NOT_FOUND, "No shipment with that waybill."))

    # one open claim per shipment: data integrity, so it applies even with rules off
    if existing := writes.get_open_claim(conn, canonical):
        return ToolResult(
            refused(
                Reason.CLAIM_ALREADY_OPEN,
                "This shipment already has an open claim. A teammate is handling it.",
                claim_ref=f"CLM-{existing['id']:05d}",
            )
        )
    if reason := check_can_claim(shipment, claim_type, config.today()):
        why = {
            Reason.CLAIM_TYPE_NOT_ALLOWED: (
                f"A {CLAIM_LABELS[claim_type]} claim isn't possible while the status is "
                f"{shipment['status']}. Damaged or missing items need a delivered shipment; "
                "disputes need a failed delivery attempt."
            ),
            Reason.CLAIM_WINDOW_CLOSED: "Claims must be filed within 7 days of delivery.",
        }[reason]
        return ToolResult(refused(reason, why + " Offer a human teammate if needed."))

    summary = f"Open a {CLAIM_LABELS[claim_type]} claim for {canonical}: {description.strip()}"
    key = {"waybill": canonical, "type": claim_type}  # description wording may change
    if gate := confirm_or_propose(session, "open_claim", key, summary):
        return gate

    result = writes.open_claim_with_handoff(
        conn, canonical, claim_type, description.strip(), session.conversation_id
    )
    return ToolResult(
        ok(
            waybill=canonical,
            claim_ref=f"CLM-{result['claim_id']:05d}",
            message="Claim filed and passed to a human teammate, who will contact the "
            "customer. Do not promise a refund or compensation.",
        ),
        {"pending_action": None, "handed_off": True},
    )
