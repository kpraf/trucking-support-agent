"""What every tool gets and returns.

Tools never see the LLM. They get the arguments the model sent plus the session (who is
verified, what change is waiting for a yes), and return a JSON-able result plus any session
changes.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import psycopg

from app import config
from app.rules.checks import Reason, check_confirmed

Conn = psycopg.Connection


@dataclass
class Session:
    conversation_id: str
    verified_waybills: list[str] = field(default_factory=list)
    failed_verifications: int = 0
    turn: int = 0  # customer messages so far in this conversation
    last_customer_message: str = ""
    pending_action: dict | None = None  # a proposed write waiting for the customer's yes
    handed_off: bool = False


@dataclass
class ToolResult:
    data: dict
    session_updates: dict = field(default_factory=dict)


def ok(**data) -> dict:
    return {"ok": True, **data}


def refused(reason: str, message: str, **extra) -> dict:
    return {"ok": False, "reason": str(reason), "message": message, **extra}


def confirm_or_propose(session: Session, tool: str, key: dict, summary: str) -> ToolResult | None:
    """Rule 6 gate for write tools. Returns None when the write may go ahead; otherwise the
    result to send back (a proposal waiting for a yes, or the customer's no)."""
    action = {"tool": tool, "key": key}
    reason = check_confirmed(
        session.pending_action, action, session.turn, session.last_customer_message
    )
    if reason is None:
        return None
    if reason == Reason.CUSTOMER_DECLINED:
        return ToolResult(
            refused(reason, "The customer did not confirm. Nothing was changed."),
            {"pending_action": None},
        )
    return ToolResult(
        refused(
            Reason.CONFIRMATION_REQUIRED,
            "Nothing is changed yet. Tell the customer this summary and ask for a clear yes. "
            "Only after they say yes, call this tool again with the same details.",
            summary=summary,
        ),
        {"pending_action": action | {"turn": session.turn}},
    )


def day_label(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


def time_label(ts: datetime) -> str:
    t = ts.astimezone(config.MANILA)
    return f"{t:%a}, {t:%b} {t.day}, {t:%I:%M %p}".replace(" 0", " ")
