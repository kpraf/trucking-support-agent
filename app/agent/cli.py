"""Chat with the agent in the terminal.

    uv run python -m app.agent.cli                    # chat
    uv run python -m app.agent.cli --debug            # also show tool calls and results
    uv run python -m app.agent.cli --debug --record assets/demo.svg
        # save the whole conversation as a terminal screenshot (SVG) when you /quit
    uv run python -m app.agent.cli --debug --say "nasan na parcel ko" --say "TRK-10006 6548"
        # send these messages one by one, then exit (no typing needed)

Commands: /new starts a fresh conversation, /quit exits.
"""

import argparse
import io
import json
import time
import uuid

from langchain_core.messages import AIMessage, ToolMessage
from rich.console import Console
from rich.markup import escape
from rich.terminal_theme import MONOKAI

from app import config
from app.agent.graph import build_graph, reply_text, send
from app.agent.llm import make_llm

HIDDEN_IN_DEBUG = {"latest_tracking", "status_meaning", "message"}


class Output:
    """Prints to the screen and, when recording, to an off-screen copy saved as SVG."""

    def __init__(self, record: bool):
        self.screen = Console(highlight=False)
        self.copy = (
            Console(record=True, width=100, file=io.StringIO(), highlight=False) if record else None
        )

    def print(self, text: str = "", screen: bool = True):
        if screen:
            self.screen.print(text)
        if self.copy:
            self.copy.print(text)

    def save(self, path: str, title: str):
        self.copy.save_svg(path, title=title, theme=MONOKAI)


def show_turn(
    out: Output, state: dict, seen: int, debug: bool, seconds: float, was_handed_off: bool
):
    if debug:
        for msg in state["messages"][seen:]:
            if isinstance(msg, AIMessage):
                for call in msg.tool_calls:
                    args = escape(json.dumps(call["args"], ensure_ascii=False))
                    out.print(f"  [cyan]-> {call['name']}[/]({args})")
            elif isinstance(msg, ToolMessage):
                data = json.loads(msg.content)
                color = (
                    "green"
                    if data.get("ok")
                    else ("yellow" if data.get("reason") == "CONFIRMATION_REQUIRED" else "red")
                )
                # the model gets everything; the screen skips the long fields
                shown = {k: v for k, v in data.items() if k not in HIDDEN_IN_DEBUG}
                text = json.dumps(shown, ensure_ascii=False)
                text = text if len(text) <= 400 else text[:400] + " ..."
                out.print(f"  [{color}]<- {escape(text)}[/]")
        verified = ", ".join(state["verified_waybills"]) or "none"
        pending = state.get("pending_action")
        waiting = f" | waiting for yes: {pending['tool']}" if pending else ""
        out.print(
            f"  [dim]verified: {verified} | failed tries: {state['failed_verifications']}"
            f"{waiting} | {seconds:.1f}s[/]"
        )
    out.print(f"[bold magenta]Agent:[/] {escape(reply_text(state))}\n")
    if state.get("handed_off") and not was_handed_off:
        out.print("[yellow](A human teammate has been notified and will continue this chat.)[/]\n")


def main():
    parser = argparse.ArgumentParser(description="Chat with the support agent")
    parser.add_argument("--debug", action="store_true", help="show tool calls and results")
    parser.add_argument("--record", metavar="FILE.svg", help="save the chat as an SVG on exit")
    parser.add_argument("--say", action="append", metavar="MESSAGE", help="send, then exit")
    args = parser.parse_args()

    graph = build_graph(make_llm())
    out = Output(record=bool(args.record))
    rules = "on" if config.ENFORCE_RULES else "OFF (baseline)"
    out.print(f"[bold]{config.COMPANY_NAME} support[/] | model {config.GEMINI_MODEL}")
    out.print(f"[dim]rule checks {rules}[/]")
    if not args.say:
        out.print("Type /new for a new conversation, /quit to exit.")
    out.print()

    scripted = list(args.say or [])
    conversation_id, first, seen, handed_off = str(uuid.uuid4()), True, 0, False
    while True:
        if args.say:
            if not scripted:
                break
            text = scripted.pop(0)
            out.print(f"[bold cyan]You:[/] {escape(text)}")
        else:
            try:
                text = out.screen.input("[bold cyan]You:[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text and text not in ("/quit", "/new"):
                out.print(f"[bold cyan]You:[/] {escape(text)}", screen=False)
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/new":
            conversation_id, first, seen, handed_off = str(uuid.uuid4()), True, 0, False
            out.print("[dim](new conversation)[/]\n")
            continue

        start = time.monotonic()
        with out.screen.status("thinking...", spinner="dots"):
            state = send(graph, conversation_id, text, first=first)
        first = False
        show_turn(out, state, seen, args.debug, time.monotonic() - start, handed_off)
        handed_off = state.get("handed_off", False)
        seen = len(state["messages"])

    if args.record:
        out.save(args.record, title=f"{config.COMPANY_NAME} support agent ({config.GEMINI_MODEL})")
        out.screen.print(f"[dim]Saved {args.record}[/]")


if __name__ == "__main__":
    main()
