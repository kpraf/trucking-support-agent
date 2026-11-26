"""Eval task schema, checks and scaffolding. Pure Python, no database or LLM."""

import random
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from evals.manage import problems, scaffold
from evals.task_schema import QUOTAS, Task

EXAMPLES = sorted((Path(__file__).parents[1] / "evals" / "tasks" / "examples").glob("*.yaml"))


def load(path: Path) -> Task:
    return Task.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def example(prefix: str) -> dict:
    path = next(p for p in EXAMPLES if p.stem.startswith(prefix))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_are_valid_and_consistent(path):
    task = load(path)
    assert problems(task) == ([], [])
    assert not task.counts  # examples never count toward the 105


def test_id_must_match_category_and_language():
    raw = example("reschedule") | {"id": "claim-taglish-001"}
    with pytest.raises(ValidationError, match="id should start with"):
        Task.model_validate(raw)


def test_variation_needs_its_seed():
    with pytest.raises(ValidationError, match="variation_of"):
        Task.model_validate(example("reschedule") | {"author": "variation"})


def test_unknown_fields_are_rejected():
    raw = example("reschedule")
    raw["expect"]["new_row"] = {"claims": 1}  # typo
    with pytest.raises(ValidationError):
        Task.model_validate(raw)


def test_counts_only_reviewed_real_tasks():
    raw = example("reschedule") | {"author": "kester", "reviewed": True}
    assert Task.model_validate(raw).counts
    assert not Task.model_validate(raw | {"reviewed": False}).counts


def errors_for(raw: dict) -> list[str]:
    return problems(Task.model_validate(raw))[0]


def test_check_catches_wrong_last4():
    raw = example("reschedule")
    raw["customer"]["knows"]["mobile_last4"] = "0000"
    assert any("mobile_last4" in e for e in errors_for(raw))


def test_check_catches_a_date_the_rules_forbid():
    raw = example("reschedule")
    raw["expect"]["shipment"]["scheduled_date"] = "2026-12-06"  # a Sunday
    assert any("not an allowed reschedule date" in e for e in errors_for(raw))


def test_check_catches_claim_outside_window_and_missing_handoff():
    raw = example("claim")
    raw["expect"]["new_rows"] = {"claims": 1}
    assert any("handoffs" in e for e in errors_for(raw))
    raw["expect"]["claim_type"] = "failed_delivery_dispute"
    assert any("CLAIM_TYPE_NOT_ALLOWED" in e for e in errors_for(raw))


def test_reviewed_task_with_todo_is_an_error():
    raw = example("injection") | {"author": "kester", "reviewed": True}
    raw["customer"]["persona"] = "TODO"
    assert "still has TODO" in errors_for(raw)


@pytest.mark.parametrize("category", list(QUOTAS))
@pytest.mark.parametrize("language", ["english", "taglish", "tagalog"])
def test_new_scaffolds_a_valid_task(category, language):
    task_id, text = scaffold(category, language, random.Random(7))
    task = Task.model_validate(yaml.safe_load(text))
    assert task.id == task_id and task.author == "kester" and not task.reviewed
    errors, warnings = problems(task)
    assert errors == [] and warnings == ["still has TODO"]
