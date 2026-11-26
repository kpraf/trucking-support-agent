from pydantic import BaseModel, Field

from app.db import queries, writes
from app.tools.base import Conn, Session, ToolResult, ok


class HandoffToHuman(BaseModel):
    """Pass the conversation to a human teammate. Use when the customer asks for a person,
    when a request is outside what you can do but still about their delivery, or when a rule
    blocks them and they need more help."""

    reason: str = Field(description="Short reason for the teammate")
    waybill: str = Field(default="", description="The waybill if known, else empty")


def create_handoff(conn: Conn, session: Session, reason: str, waybill: str = "") -> dict:
    """Shared by this tool and the verification lockout."""
    canonical = queries.normalize_waybill(waybill) if waybill else None
    if canonical and queries.get_shipment(conn, canonical) is None:
        canonical = None  # don't store a made-up waybill
    return writes.insert_handoff(conn, canonical, reason, session.conversation_id)


def handoff_to_human(conn: Conn, session: Session, reason: str, waybill: str = "") -> ToolResult:
    message = "A human teammate will continue this conversation."
    if session.handed_off:
        return ToolResult(ok(message="Already passed to a teammate. " + message))
    create_handoff(conn, session, reason, waybill)
    return ToolResult(ok(message=message), {"handed_off": True})
