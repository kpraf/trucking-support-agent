"""Settings read from the environment (.env is loaded if present)."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

MANILA = ZoneInfo("Asia/Manila")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/trucking")
APP_ENV = os.getenv("APP_ENV", "dev")

COMPANY_NAME = "Timog Freight"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Python rule checks (app/rules). Turn off only to measure the v0 baseline, where the
# prompt alone has to keep the agent in line.
ENFORCE_RULES = os.getenv("ENFORCE_RULES", "true").lower() not in ("0", "false", "no", "off")


def today() -> date:
    """The business date in Manila.

    Set APP_TODAY=YYYY-MM-DD to pin the clock, so seeded data and eval runs
    give the same results on any day.
    """
    pinned = os.getenv("APP_TODAY")
    if pinned:
        return date.fromisoformat(pinned)
    return datetime.now(MANILA).date()
