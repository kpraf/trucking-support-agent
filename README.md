# Trucking Support Agent

A support agent for a fictional trucking company in Laguna and Cavite, Philippines. Receivers chat in English, Taglish or Tagalog to check a delivery, reschedule it, or report a problem.

The main focus is evaluation: a test suite of about 120 tasks, written by a native speaker, that measures whether the agent follows the company's rules in each language. Tasks are graded on the database state at the end of each conversation, not just on how the reply sounds.

> Work in progress. Results will be added here as each version is measured.

## What the agent can do

- Check delivery status (after verifying the receiver with waybill + last 4 digits of their mobile)
- Reschedule a delivery, within the company's rules
- Open a claim for a failed or damaged delivery and hand off to a human
- Refuse out-of-scope requests and prompt-injection attempts

## Demo

Real runs of the CLI on Gemini (`gemini-3.5-flash-lite`), tool calls shown. Data is fake.

**Status check in Tagalog.** A wrong mobile number is refused, then details are shown only after verification, with a partial address.

![Agent verifies the receiver before showing the delivery status](assets/demo-status.svg)

**Refusals.** An impostor asking for the address, a prompt injection, and an out-of-scope rate question.

![Agent refuses an impostor, a prompt injection, and a rates question](assets/demo-refusals.svg)

## Stack

- **Agent:** LangGraph, Gemini Flash
- **Backend:** FastAPI, PostgreSQL
- **Frontend:** React, Tailwind
- **Evals:** LLM-simulated customers, scripted attacks, database end-state grading

## Architecture

![Architecture: every write passes Python rule checks before it reaches the database](assets/architecture.webp)

## Results

| Version | Success: English | Success: Taglish | Success: Tagalog | pass^3 | Unsafe writes |
| --- | --- | --- | --- | --- | --- |
| Baseline | | | | | |

## Running locally

Needs [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env
docker compose up -d                       # Postgres 16 on localhost:5433
uv sync                                    # Python 3.12 + dependencies
uv run python -m app.db.seed               # reset and seed ~200 fake shipments
uv run uvicorn app.api.main:app --reload
```

Then open http://localhost:8000/dev/shipments/TRK-10001 (or `/docs` for all routes).

The seed is deterministic: the same `--today` and `--seed` always give the same data, e.g.
`uv run python -m app.db.seed --today 2026-12-02 --seed 42`. Set `APP_TODAY` in `.env` to pin
the business date for eval runs.

`/dev/*` routes skip identity checks and show full details. They are for debugging only and are
turned off when `APP_ENV=prod`.

### Chat with the agent

Put a Gemini API key in `.env` (`GEMINI_API_KEY`, free at https://aistudio.google.com/apikey), then:

```bash
uv run python -m app.agent.cli --debug     # --debug shows each tool call and result
uv run python -m app.agent.cli --debug --record assets/demo.svg   # save the chat as an image on /quit
```

Rule checks run in Python before tools touch data (`app/rules`). `ENFORCE_RULES=false` turns
them off. That's only for measuring the v0 baseline.

Tests: `uv run pytest`. The API tests use a separate `trucking_test` database and are skipped
when Postgres isn't running.
