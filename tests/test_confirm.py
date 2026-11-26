import pytest

from app.rules.confirm import Answer, classify_answer


@pytest.mark.parametrize(
    "text",
    ["oo", "Oo sige po", "opo", "sige", "yes", "Yes po!", "ok lang", "go", "tama po yan", "G"],
)
def test_yes(text):
    assert classify_answer(text) is Answer.YES


@pytest.mark.parametrize(
    "text",
    ["hindi", "wag na po", "huwag", "no", "ayoko", "teka lang", "mali yung date", "di pwede"],
)
def test_no(text):
    assert classify_answer(text) is Answer.NO


@pytest.mark.parametrize(
    "text",
    [
        "sige pero sa Friday na lang",  # yes, but a different change
        "ok ba yung Saturday?",  # a question, not an answer
        "Saturday na lang",
        "salamat",
        "",
        "...",
    ],
)
def test_unclear(text):
    assert classify_answer(text) is Answer.UNCLEAR
