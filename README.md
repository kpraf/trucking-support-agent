# Trucking Support Agent

A support agent for a fictional trucking company in Laguna and Cavite, Philippines. Receivers chat in English, Taglish or Tagalog to check a delivery, reschedule it, or report a problem.

The main focus is evaluation: a test suite of about 120 tasks, written by a native speaker, that measures whether the agent follows the company's rules in each language. Tasks are graded on the database state at the end of each conversation, not just on how the reply sounds.

> Work in progress. Results will be added here as each version is measured.

## What the agent can do

- Check delivery status (after verifying the receiver with waybill + last 4 digits of their mobile)
- Reschedule a delivery, within the company's rules
- Open a claim for a failed or damaged delivery and hand off to a human
- Refuse out-of-scope requests and prompt-injection attempts

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

Coming soon.
