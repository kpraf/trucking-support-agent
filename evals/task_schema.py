"""The shape of one eval task (one YAML file in evals/tasks/).

A task is one customer conversation: who the customer is, what they want, what they know,
and what the database must look like at the end. The Week 5 runner plays the customer with
an LLM and the grader checks `expect`.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# All tasks run against the same seeded data and the same "today", so they're reproducible.
EVAL_TODAY = date(2026, 12, 2)  # a Wednesday
EVAL_SEED = 42

Category = Literal["status", "reschedule", "claim", "impostor", "out_of_scope", "injection"]
Language = Literal["english", "taglish", "tagalog"]
LANG_CODE = {"english": "en", "taglish": "taglish", "tagalog": "tl"}

# v1 target: 105 reviewed tasks, split about evenly across the 3 languages.
QUOTAS: dict[str, int] = {
    "status": 25,
    "reschedule": 25,
    "claim": 20,
    "impostor": 15,
    "out_of_scope": 10,
    "injection": 10,
}

Table = Literal["reschedules", "claims", "handoffs"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Customer(Strict):
    persona: str = Field(description="Who they are and how they text")
    goal: str = Field(description="What they want from this chat")
    opener: str = Field(description="Their first message, exactly as they'd type it")
    knows: dict[str, str] = Field(
        default_factory=dict,
        description="Facts the simulated customer can give when asked, e.g. waybill, "
        "mobile_last4, wrong_last4, preferred_day, what_happened",
    )


class Setup(Strict):
    waybill: str | None = Field(default=None, description="Seeded shipment the chat is about")


class ExpectShipment(Strict):
    status: str | None = None
    scheduled_date: date | None = None
    reschedule_count: int | None = None


class Expect(Strict):
    # Rows the conversation must add. Tables not listed must get 0 new rows: any other write
    # is counted as an unsafe or wrong write.
    new_rows: dict[Table, int] = Field(default_factory=dict)
    shipment: ExpectShipment = Field(default_factory=ExpectShipment)
    claim_type: Literal["damaged", "missing_item", "failed_delivery_dispute"] | None = None
    # Facts the agent's replies must contain, in plain words (checked by an LLM judge).
    must_say: list[str] = Field(default_factory=list)
    # Things it must never say. The full address and full mobile are always checked too.
    must_not_say: list[str] = Field(default_factory=list)


class Task(Strict):
    id: str = Field(pattern=r"^[a-z_]+-(en|taglish|tl)-\d{3}$")
    category: Category
    language: Language
    author: Literal["kester", "variation", "example"]
    reviewed: bool = False
    variation_of: str | None = None
    customer: Customer
    setup: Setup = Field(default_factory=Setup)
    expect: Expect = Field(default_factory=Expect)
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        prefix = f"{self.category}-{LANG_CODE[self.language]}-"
        if not self.id.startswith(prefix):
            raise ValueError(f"id should start with {prefix!r} for this category and language")
        if self.author == "variation" and not self.variation_of:
            raise ValueError("a variation needs variation_of: <seed task id>")
        return self

    @property
    def counts(self) -> bool:
        """Only reviewed tasks by Kester or reviewed variations count toward the 105."""
        return self.reviewed and self.author in ("kester", "variation")
