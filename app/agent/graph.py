"""The agent graph.

    START -> agent --(tool calls?)--> tools -> agent ... -> END

The agent node asks the model what to do next. The tools node runs the tool calls in Python,
with the rule checks, and feeds the results back. State carries the chat plus who is verified,
so verification can't be faked by the model: only verify_receiver can add a verified waybill.
"""

import json
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent.prompts import system_prompt
from app.db.connection import connect
from app.tools import registry
from app.tools.base import Session

MAX_TOOL_CALLS_PER_TURN = 6


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation_id: str
    verified_waybills: list[str]
    failed_verifications: int
    tool_calls_this_turn: int


def build_graph(llm: BaseChatModel, checkpointer=None):
    llm_with_tools = llm.bind_tools(registry.schemas())

    def agent(state: AgentState) -> dict:
        # Past the per-turn cap the model has to answer with what it has.
        model = llm_with_tools if state["tool_calls_this_turn"] < MAX_TOOL_CALLS_PER_TURN else llm
        reply = model.invoke([SystemMessage(system_prompt()), *state["messages"]])
        return {"messages": [reply]}

    def tools(state: AgentState) -> dict:
        last: AIMessage = state["messages"][-1]
        session = Session(
            conversation_id=state["conversation_id"],
            verified_waybills=list(state["verified_waybills"]),
            failed_verifications=state["failed_verifications"],
        )
        results = []
        with connect() as conn:
            for call in last.tool_calls:
                result = registry.run_tool(conn, session, call["name"], call["args"])
                for key, value in result.session_updates.items():
                    setattr(session, key, value)  # later calls in this batch see the change
                results.append(
                    ToolMessage(
                        content=json.dumps(result.data, ensure_ascii=False),
                        tool_call_id=call["id"],
                        name=call["name"],
                    )
                )
        return {
            "messages": results,
            "verified_waybills": session.verified_waybills,
            "failed_verifications": session.failed_verifications,
            "tool_calls_this_turn": state["tool_calls_this_turn"] + len(last.tool_calls),
        }

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, ["tools", END])
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def new_conversation(conversation_id: str) -> dict:
    """Initial state for a conversation. Pass with the first message only."""
    return {
        "conversation_id": conversation_id,
        "verified_waybills": [],
        "failed_verifications": 0,
    }


def send(graph, conversation_id: str, text: str, first: bool = False) -> dict:
    """Run one customer turn and return the final state."""
    turn = {"messages": [("user", text)], "tool_calls_this_turn": 0}
    if first:
        turn |= new_conversation(conversation_id)
    return graph.invoke(turn, {"configurable": {"thread_id": conversation_id}})


def reply_text(state: dict) -> str:
    return state["messages"][-1].text  # flattens Gemini's list-of-parts content to a string
