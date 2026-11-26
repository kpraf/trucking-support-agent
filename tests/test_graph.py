"""The graph wiring, driven by a scripted fake model (no API key, no network)."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent.graph import MAX_TOOL_CALLS_PER_TURN, build_graph, reply_text, send


class ScriptedModel(BaseChatModel):
    """Returns the next scripted AIMessage on each call and records what it was sent."""

    script: list
    calls: list = []
    tools_bound: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.tools_bound.append(True)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


def tool_call(name, args, id_):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_}])


def tool_results(state):
    return [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]


def test_nasan_na_yung_parcel_ko(seeded, shipment):
    wb, last4 = shipment["waybill"], shipment["last4"]
    model = ScriptedModel(
        script=[
            AIMessage(content="Sige po! Pakibigay po ng waybill at last 4 digits ng mobile."),
            tool_call("verify_receiver", {"waybill": wb, "mobile_last4": last4}, "c1"),
            tool_call("get_shipment_status", {"waybill": wb}, "c2"),
            AIMessage(content="Nasa hub na po yung parcel ninyo."),
        ],
        calls=[],
    )
    graph = build_graph(model)

    state = send(graph, "conv-1", "nasan na yung parcel ko", first=True)
    assert "waybill" in reply_text(state)
    assert state["verified_waybills"] == []

    state = send(graph, "conv-1", f"{wb} tapos {last4}")
    results = tool_results(state)
    assert results[0]["ok"] and results[1]["ok"]
    assert results[1]["status"] == "at_hub"
    assert state["verified_waybills"] == [wb]
    assert reply_text(state) == "Nasa hub na po yung parcel ninyo."
    # the system prompt goes first on every call
    assert all(c[0].type == "system" for c in model.calls)


def test_model_cannot_skip_verification(seeded, shipment):
    """Even if the model calls the status tool straight away, the rule check refuses."""
    model = ScriptedModel(
        script=[
            tool_call("get_shipment_status", {"waybill": shipment["waybill"]}, "c1"),
            AIMessage(content="Kailangan ko po munang i-verify."),
        ],
        calls=[],
    )
    state = send(build_graph(model), "conv-2", f"status ng {shipment['waybill']}", first=True)
    assert tool_results(state)[0]["reason"] == "NOT_VERIFIED"


def test_failed_tries_carry_across_turns(seeded):
    script = []
    for i in range(3):
        script += [
            tool_call("verify_receiver", {"waybill": "TRK-99999", "mobile_last4": "1234"}, f"c{i}"),
            AIMessage(content="Hindi po tugma."),
        ]
    graph = build_graph(ScriptedModel(script=script, calls=[]))
    for i in range(3):
        state = send(graph, "conv-3", "TRK-99999 1234", first=(i == 0))
    assert state["failed_verifications"] == 3


def test_tool_call_cap_per_turn(seeded):
    loop = [
        tool_call("verify_receiver", {"waybill": "x", "mobile_last4": "1"}, f"c{i}")
        for i in range(MAX_TOOL_CALLS_PER_TURN)
    ]
    model = ScriptedModel(script=[*loop, AIMessage(content="Pasensya na po.")], calls=[])
    state = send(build_graph(model), "conv-4", "hi", first=True)
    assert reply_text(state) == "Pasensya na po."
    assert state["tool_calls_this_turn"] == MAX_TOOL_CALLS_PER_TURN


def test_reschedule_lands_in_db_after_customer_says_oo(fresh_db, receivers):
    """Week 3 done-when: a reschedule shows up in the database after the customer says yes."""
    from app.db.connection import connect

    s = next(x for x in fresh_db.shipments if x["status"] == "at_hub" and x["reschedule_count"] < 2)
    wb, last4 = s["waybill"], receivers[s["receiver_id"]]["mobile"][-4:]
    with connect() as conn:
        from app.rules.checks import reschedule_dates
        from tests.conftest import SEED_TODAY

        new_date = next(d for d in reschedule_dates(SEED_TODAY) if d != s["scheduled_date"])
    move = {"waybill": wb, "new_date": new_date.isoformat()}
    model = ScriptedModel(
        script=[
            # turn 1: verify, look up slots, propose, and (wrongly) try to write straight away
            tool_call("verify_receiver", {"waybill": wb, "mobile_last4": last4}, "a1"),
            tool_call("list_reschedule_slots", {"waybill": wb}, "a2"),
            tool_call("reschedule_delivery", move, "a3"),
            tool_call("reschedule_delivery", move, "a4"),
            AIMessage(content="Ililipat ko po sa ibang araw. Okay po ba?"),
            # turn 2: customer said oo
            tool_call("reschedule_delivery", move, "b1"),
            AIMessage(content="Done na po!"),
        ],
        calls=[],
    )
    graph = build_graph(model)

    state = send(graph, "conv-r", f"pwede ilipat? {wb} {last4}", first=True)
    reasons = [r.get("reason") for r in tool_results(state)]
    assert reasons[2:] == ["CONFIRMATION_REQUIRED", "CONFIRMATION_REQUIRED"]
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM reschedules WHERE waybill = %s AND new_date = %s",
                (wb, new_date),
            ).fetchone()["n"]
            == 0
        )

    state = send(graph, "conv-r", "oo sige po")
    assert tool_results(state)[-1]["ok"]
    assert state["pending_action"] is None
    with connect() as conn:
        row = conn.execute(
            "SELECT scheduled_date FROM shipments WHERE waybill = %s", (wb,)
        ).fetchone()
        assert row["scheduled_date"] == new_date
