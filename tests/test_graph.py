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
