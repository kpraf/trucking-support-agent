"""Is the customer's reply a clear yes? English, Tagalog and Taglish.

Deliberately strict: anything with a "no" word, a condition ("pero", "but") or a question
counts as not a clear yes, so the agent asks again instead of writing.
"""

import re
from enum import Enum


class Answer(Enum):
    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


YES_WORDS = {
    "yes", "yep", "yup", "yeah", "ye", "y", "sure", "ok", "okay", "okey", "oki", "k",
    "confirm", "confirmed", "go", "goods", "game", "correct", "right",
    "oo", "opo", "oho", "o", "sige", "tama", "ayos", "g", "push", "yes po", "oks",
}  # fmt: skip
NO_WORDS = {
    "no", "nope", "nah", "not", "dont", "don't", "cancel", "stop", "wait", "wrong",
    "hindi", "di", "huwag", "wag", "ayaw", "ayoko", "teka", "mali", "hwag", "hnd", "hinde",
}  # fmt: skip
HEDGE_WORDS = {"pero", "but", "kaso", "except", "instead", "na lang", "nalang", "ba", "maybe"}


def classify_answer(text: str) -> Answer:
    cleaned = text.lower().replace("’", "'")
    words = re.findall(r"[a-z']+", cleaned)
    if not words:
        return Answer.UNCLEAR
    if any(w in NO_WORDS for w in words):
        return Answer.NO
    if "?" in cleaned or any(w in HEDGE_WORDS for w in words) or "na lang" in cleaned:
        return Answer.UNCLEAR
    if any(w in YES_WORDS for w in words):
        return Answer.YES
    return Answer.UNCLEAR
