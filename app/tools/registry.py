"""Every tool the agent can call: the schema the model sees and the function that runs."""

from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from app.tools.base import Conn, Session, ToolResult
from app.tools.status import GetShipmentStatus, get_shipment_status
from app.tools.verify import VerifyReceiver, verify_receiver

TOOLS: dict[str, tuple[type[BaseModel], Callable[..., ToolResult]]] = {
    "verify_receiver": (VerifyReceiver, verify_receiver),
    "get_shipment_status": (GetShipmentStatus, get_shipment_status),
}


def schemas() -> list[dict]:
    """Tool definitions in the OpenAI-style shape that LangChain's bind_tools accepts."""
    out = []
    for name, (model, _) in TOOLS.items():
        params = model.model_json_schema()
        params.pop("title", None)
        for prop in params.get("properties", {}).values():
            prop.pop("title", None)
        description = " ".join((model.__doc__ or "").split())
        out.append(
            {
                "type": "function",
                "function": {"name": name, "description": description, "parameters": params},
            }
        )
    return out


def run_tool(conn: Conn, session: Session, name: str, args: dict) -> ToolResult:
    if name not in TOOLS:
        return ToolResult({"ok": False, "reason": "UNKNOWN_TOOL", "message": f"No tool {name}."})
    model, fn = TOOLS[name]
    try:
        parsed = model.model_validate(args)
    except ValidationError as e:
        return ToolResult({"ok": False, "reason": "BAD_ARGUMENTS", "message": str(e)[:300]})
    return fn(conn, session, **parsed.model_dump())
