"""What every tool gets and returns.

Tools never see the LLM. They get the arguments the model sent plus the session (who is
verified so far), and return a JSON-able result plus any session changes.
"""

from dataclasses import dataclass, field

import psycopg

Conn = psycopg.Connection


@dataclass
class Session:
    conversation_id: str
    verified_waybills: list[str] = field(default_factory=list)
    failed_verifications: int = 0


@dataclass
class ToolResult:
    data: dict
    session_updates: dict = field(default_factory=dict)


def ok(**data) -> dict:
    return {"ok": True, **data}


def refused(reason: str, message: str, **extra) -> dict:
    return {"ok": False, "reason": str(reason), "message": message, **extra}
