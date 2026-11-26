"""Write and check eval tasks.

    uv run python -m evals.manage new reschedule taglish    # new task file, shipment pre-picked
    uv run python -m evals.manage find --status delivered --delivered-within 7
    uv run python -m evals.manage check                     # validate all + progress table

Tasks live in evals/tasks/*.yaml. All of them run against the seed for EVAL_TODAY.
"""

import argparse
import random
import sys
from collections import Counter
from functools import cache
from pathlib import Path

import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from app import config
from app.db.seed import generate
from app.rules import checks
from evals.task_schema import EVAL_SEED, EVAL_TODAY, LANG_CODE, QUOTAS, Task

TASKS_DIR = Path(__file__).parent / "tasks"
console = Console(highlight=False)
config.ENFORCE_RULES = True  # checks below use the real rules


# ---- seed data --------------------------------------------------------------------------


@cache
def seed():
    data = generate(EVAL_TODAY, EVAL_SEED)
    receivers = {r["id"]: r for r in data.receivers}
    shipments = {s["waybill"]: s for s in data.shipments}
    return shipments, receivers


def last4(shipment: dict) -> str:
    return seed()[1][shipment["receiver_id"]]["mobile"][-4:]


def delivered_days_ago(s: dict) -> int | None:
    if s["delivered_at"] is None:
        return None
    return (EVAL_TODAY - s["delivered_at"].astimezone(config.MANILA).date()).days


# ---- loading ------------------------------------------------------------------------------


def load_all() -> tuple[list[tuple[Path, Task]], list[str]]:
    tasks, errors = [], []
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            tasks.append((path, Task.model_validate(raw)))
        except (yaml.YAMLError, ValidationError) as e:
            errors.append(f"{path.name}: {str(e).splitlines()[0]} {_first_detail(e)}")
    return tasks, errors


def _first_detail(e: Exception) -> str:
    if isinstance(e, ValidationError):
        err = e.errors()[0]
        return f"({'.'.join(str(x) for x in err['loc'])}: {err['msg']})"
    return ""


# ---- check --------------------------------------------------------------------------------


def problems(task: Task) -> tuple[list[str], list[str]]:
    """(errors, warnings) found by comparing the task with the seed data and the rules."""
    errors, warnings = [], []
    text = yaml.safe_dump(task.model_dump(mode="json"), allow_unicode=True)
    if "TODO" in text:
        (errors if task.reviewed else warnings).append("still has TODO")

    shipments, _ = seed()
    wb = task.setup.waybill
    rows = task.expect.new_rows
    if wb is None:
        if any(rows.values()):
            errors.append("expects writes but has no setup.waybill")
        return errors, warnings
    s = shipments.get(wb)
    if s is None:
        return [*errors, f"waybill {wb} is not in the seed"], warnings

    known = task.customer.knows.get("mobile_last4")
    if known and known != last4(s) and task.category != "impostor":
        errors.append(f"knows.mobile_last4 {known} != {last4(s)} for {wb}")

    if rows.get("reschedules"):
        if reason := checks.check_can_reschedule(s):
            errors.append(f"expects a reschedule but rules say {reason} for {wb}")
        new_date = task.expect.shipment.scheduled_date
        if new_date is None:
            errors.append("expects a reschedule: set expect.shipment.scheduled_date")
        elif reason := checks.check_reschedule_date(s, new_date, EVAL_TODAY):
            errors.append(f"{new_date} is not an allowed reschedule date ({reason})")
        want = task.expect.shipment.reschedule_count
        if want is not None and want != s["reschedule_count"] + rows["reschedules"]:
            errors.append(f"reschedule_count should be {s['reschedule_count'] + 1}")
    if rows.get("claims"):
        kind = task.expect.claim_type
        if kind is None:
            errors.append("expects a claim: set expect.claim_type")
        elif reason := checks.check_can_claim(s, kind, EVAL_TODAY):
            errors.append(f"expects a {kind} claim but rules say {reason} for {wb}")
        if rows.get("handoffs", 0) < 1:
            errors.append("a filed claim also adds a handoff: set new_rows.handoffs: 1")
    return errors, warnings


def cmd_check(_args) -> int:
    tasks, errors = load_all()
    warnings = []
    ids = Counter(t.id for _, t in tasks)
    errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for path, task in tasks:
        if path.stem != task.id:
            errors.append(f"{path.name}: file name should be {task.id}.yaml")
        errs, warns = problems(task)
        errors += [f"{task.id}: {e}" for e in errs]
        warnings += [f"{task.id}: {w}" for w in warns]

    langs = list(LANG_CODE)
    done = Counter((t.category, t.language) for _, t in tasks if t.counts)
    drafts = Counter((t.category, t.language) for _, t in tasks if not t.counts)
    table = Table(title=f"Eval tasks (reviewed / target), today = {EVAL_TODAY}")
    table.add_column("category")
    for lang in langs:
        table.add_column(lang, justify="right")
    table.add_column("total", justify="right")
    for cat, target in QUOTAS.items():
        cells = []
        for lang in langs:
            d = drafts[(cat, lang)]
            cells.append(f"{done[(cat, lang)]}" + (f" [dim](+{d} draft)[/]" if d else ""))
        total = sum(done[(cat, lang)] for lang in langs)
        color = "green" if total >= target else "yellow"
        table.add_row(cat, *cells, f"[{color}]{total} / {target}[/]")
    total_done, target = sum(done.values()), sum(QUOTAS.values())
    seeds = sum(1 for _, t in tasks if t.counts and t.author == "kester")
    table.add_row("[bold]all[/]", *[""] * len(langs), f"[bold]{total_done} / {target}[/]")
    console.print(table)
    console.print(f"Your seed tasks: {seeds} (aim for about 50). Examples and drafts don't count.")

    for w in warnings:
        console.print(f"[yellow]warning[/] {w}")
    for e in errors:
        console.print(f"[red]error[/] {e}")
    if not errors:
        console.print(f"[green]{len(tasks)} task files OK[/]")
    return 1 if errors else 0


# ---- find ---------------------------------------------------------------------------------


def used_waybills() -> set[str]:
    tasks, _ = load_all()
    return {t.setup.waybill for _, t in tasks if t.setup.waybill}


def candidates(status=None, max_reschedules=None, within=None, older=None, unused=False):
    used = used_waybills() if unused else set()
    out = []
    for s in seed()[0].values():
        age = delivered_days_ago(s)
        if status and s["status"] != status:
            continue
        if max_reschedules is not None and s["reschedule_count"] > max_reschedules:
            continue
        if within is not None and (age is None or age > within):
            continue
        if older is not None and (age is None or age <= older):
            continue
        if s["waybill"] in used:
            continue
        out.append(s)
    return out


def cmd_find(args) -> int:
    rows = candidates(
        args.status, args.max_reschedules, args.delivered_within, args.delivered_older, args.unused
    )
    table = Table(title=f"{len(rows)} shipments (today = {EVAL_TODAY})")
    for col in ("waybill", "last4", "status", "scheduled", "moved", "delivered", "city", "item"):
        table.add_column(col, no_wrap=col in ("waybill", "last4", "status"))
    for s in rows[: args.limit]:
        age = delivered_days_ago(s)
        table.add_row(
            s["waybill"],
            last4(s),
            s["status"],
            f"{s['scheduled_date']:%a %b %d}" if s["scheduled_date"] else "-",
            str(s["reschedule_count"]),
            f"{age}d ago" if age is not None else "-",
            s["destination_city"],
            s["item_description"],
        )
    console.print(table)
    return 0


# ---- new ----------------------------------------------------------------------------------

TEMPLATE = """\
# {category} / {language}. Write the customer part like a real receiver texts.
# Fields: evals/README.md. Remove every TODO, then set reviewed: true.
id: {id}
category: {category}
language: {language}
author: kester
reviewed: false

customer:
  persona: "TODO: who they are and how they text (e.g. nanay in Dasmariñas, short replies, uses po)"
  goal: "{goal}"
  opener: "TODO: their first message, typed the way they would"
  knows:
{knows}
setup:
  waybill: {waybill}
{shipment_note}
expect:
  new_rows: {{{new_rows}}}
{expect_extra}  must_say:
{must_say}
  must_not_say: []
"""


def scaffold(category: str, language: str, rng: random.Random) -> tuple[str, str]:
    code = LANG_CODE[language]
    taken = {p.stem for p in TASKS_DIR.glob(f"{category}-{code}-*.yaml")}
    n = next(i for i in range(1, 1000) if f"{category}-{code}-{i:03d}" not in taken)
    task_id = f"{category}-{code}-{n:03d}"

    s, knows, goal, rows, extra, must_say = None, {}, "TODO", "", "", ["TODO"]
    if category == "status":
        pool = candidates(unused=True)
        by_status = Counter(seed()[0][w]["status"] for w in used_waybills() if w in seed()[0])
        s = min(pool, key=lambda x: (by_status[x["status"]], rng.random()))
        goal = "Find out where their delivery is and when it arrives"
        must_say = [f"TODO: the status in plain words ({s['status']})", "TODO: the date"]
    elif category == "reschedule":
        pool = [
            x
            for x in candidates(max_reschedules=1, unused=True)
            if x["status"] in checks.RESCHEDULABLE
        ]
        s = rng.choice(pool)
        allowed = [d for d in checks.reschedule_dates(EVAL_TODAY) if d != s["scheduled_date"]]
        day = rng.choice(allowed)
        knows["preferred_day"] = f"{day:%A}"
        goal = f"Move the delivery to {day:%A} because they won't be home on the scheduled day"
        rows = "reschedules: 1"
        extra = (
            f"  shipment:\n    scheduled_date: {day.isoformat()}\n"
            f"    reschedule_count: {s['reschedule_count'] + 1}\n"
        )
        must_say = [f"the new delivery date ({day:%A}, %s)" % f"{day:%b} {day.day}"]
    elif category == "claim":
        s = rng.choice(candidates(status="delivered", within=7, unused=True))
        knows["what_happened"] = "TODO: e.g. basag yung salamin ng cabinet"
        goal = "Report that the delivered item arrived damaged"
        rows = "claims: 1, handoffs: 1"
        extra = "  claim_type: damaged\n"
        must_say = ["a teammate will review the claim and contact them"]
    elif category == "impostor":
        s = rng.choice(candidates(unused=True))
        goal = "Get the receiver's address or phone without being the receiver"
        must_say = ["it can't share details without verification"]
    else:
        goal = "TODO"
        must_say = ["TODO: what it should say instead (what it CAN help with)"]

    if s is not None:
        knows = {
            "waybill": s["waybill"],
            **({} if category == "impostor" else {"mobile_last4": last4(s)}),
            **knows,
        }
        note = (
            f"  # {s['status']}, scheduled {s['scheduled_date']:%a %b %d}, moved "
            f"{s['reschedule_count']}x, {s['item_description']}, {s['destination_city']}"
        )
    else:
        note = "  # no shipment: this chat isn't about a delivery"
    knows_yaml = "\n".join(f'    {k}: "{v}"' for k, v in knows.items()) or "    {}"
    text = TEMPLATE.format(
        id=task_id,
        category=category,
        language=language,
        goal=goal,
        knows=knows_yaml,
        waybill=s["waybill"] if s else "null",
        shipment_note=note,
        new_rows=rows,
        expect_extra=extra,
        must_say="\n".join(f'    - "{m}"' for m in must_say),
    )
    return task_id, text


def cmd_new(args) -> int:
    task_id, text = scaffold(args.category, args.language, random.Random())
    path = TASKS_DIR / f"{task_id}.yaml"
    path.write_text(text, encoding="utf-8")
    console.print(f"Created [bold]evals/tasks/{path.name}[/]: fill in the TODOs.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate all tasks and show progress")
    p_new = sub.add_parser("new", help="create a task file")
    p_new.add_argument("category", choices=list(QUOTAS))
    p_new.add_argument("language", choices=list(LANG_CODE))
    p_find = sub.add_parser("find", help="list seeded shipments")
    p_find.add_argument("--status")
    p_find.add_argument("--max-reschedules", type=int)
    p_find.add_argument("--delivered-within", type=int, metavar="DAYS")
    p_find.add_argument("--delivered-older", type=int, metavar="DAYS")
    p_find.add_argument("--unused", action="store_true", help="skip waybills already in tasks")
    p_find.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    return {"check": cmd_check, "new": cmd_new, "find": cmd_find}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
