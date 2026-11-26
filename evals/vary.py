"""Draft variations of a reviewed seed task with Gemini. You review every draft.

    uv run python -m evals.vary reschedule-taglish-001                  # 1 draft, same language
    uv run python -m evals.vary reschedule-taglish-001 --to tagalog -n 2

A variation keeps the seed's shipment, facts and expected end state, and only rewrites who
the customer is and how they talk. Drafts are saved with reviewed: false. Open each one:
fix anything you wouldn't say yourself, then set reviewed: true, or delete the file.
"""

import argparse
import json
import sys

import yaml
from google import genai
from google.genai import types

from app import config
from evals.manage import TASKS_DIR, console
from evals.task_schema import LANG_CODE, Task

STYLE = {
    "english": "plain Filipino English, the way a Filipino types English in a chat",
    "taglish": "natural Taglish code-switching, the way people in Laguna and Cavite text "
    "(mix of English and Tagalog in the same sentence, 'po', 'yung', 'naman', 'kasi')",
    "tagalog": "everyday conversational Tagalog as texted in Southern Tagalog, not formal or "
    "textbook Filipino (English loanwords like delivery and schedule are fine)",
}

PROMPT = """\
You help write test cases for a customer support chatbot of a trucking company in Laguna \
and Cavite, Philippines. Below is one test case written by a native speaker.

Write {n} variation(s). Each keeps the SAME goal and facts, but changes WHO the customer is \
and HOW they type: different age, job, mood (rushed, worried, annoyed, chill), message \
length, typos and texting habits. Language: {style}.

Do not translate word for word. Write it the way a real person would actually text. Do not \
add facts that aren't in the original (no new dates, numbers, or problems). Keep the same \
town or city as the original persona. Stay in the requested language: for Tagalog, most of \
the message must be Tagalog.

Original persona: {persona}
Original goal: {goal}
Original first message: {opener}
Facts the customer knows: {knows}

Return JSON: a list of {n} objects with keys "persona" (one sentence, in English) and \
"opener" (their first message).
"""


def draft(seed: Task, language: str, n: int) -> list[dict]:
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = PROMPT.format(
        n=n,
        style=STYLE[language],
        persona=seed.customer.persona,
        goal=seed.customer.goal,
        opener=seed.customer.opener,
        knows=json.dumps(seed.customer.knows, ensure_ascii=False),
    )
    reply = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(reply.text)[:n]


def next_id(category: str, language: str) -> str:
    code = LANG_CODE[language]
    taken = {p.stem for p in TASKS_DIR.glob(f"{category}-{code}-*.yaml")}
    return next(
        f"{category}-{code}-{i:03d}"
        for i in range(1, 1000)
        if f"{category}-{code}-{i:03d}" not in taken
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("seed_id", help="id of a reviewed task you wrote")
    parser.add_argument("--to", choices=list(LANG_CODE), help="language (default: same)")
    parser.add_argument("-n", type=int, default=1, help="how many drafts")
    args = parser.parse_args()

    path = TASKS_DIR / f"{args.seed_id}.yaml"
    if not path.exists():
        console.print(f"[red]No task {args.seed_id}[/]")
        return 1
    seed = Task.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if not (seed.reviewed and seed.author == "kester"):
        console.print("[red]Only vary tasks you wrote and reviewed (author: kester).[/]")
        return 1
    if not config.GEMINI_API_KEY:
        console.print("[red]GEMINI_API_KEY is not set in .env[/]")
        return 1

    language = args.to or seed.language
    for variant in draft(seed, language, args.n):
        task = seed.model_copy(deep=True)
        task.id = next_id(seed.category, language)
        task.language = language
        task.author = "variation"
        task.reviewed = False
        task.variation_of = seed.id
        task.customer.persona = variant["persona"]
        task.customer.opener = variant["opener"]
        out = TASKS_DIR / f"{task.id}.yaml"
        header = (
            f"# DRAFT variation of {seed.id}. Fix anything you wouldn't say yourself,\n"
            f"# then set reviewed: true. Or delete this file.\n"
        )
        body = yaml.safe_dump(
            Task.model_validate(task.model_dump()).model_dump(mode="json", exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        out.write_text(header + body, encoding="utf-8")
        console.print(f"[green]Drafted[/] evals/tasks/{out.name}: {variant['opener']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
