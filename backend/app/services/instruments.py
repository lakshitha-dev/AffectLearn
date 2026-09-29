"""The questionnaires the pilot administers, and how an answer to each is validated.

Three instruments, each with a version stamped on every stored response:

  * `lesson_feedback` -- a short study-specific questionnaire after each lesson, for BOTH arms.
    It is not a validated scale; its items are reported individually, never summed into a score.
    The control arm answers "did you notice the lesson changing" too, which gives the rate at
    which learners report changes that did not happen -- the baseline the adaptive arm's rate has
    to be read against.
  * `sus` -- the System Usability Scale (Brooke, 1996), ten items, five-point agreement, used
    verbatim. Scored 0-100 with the standard rule (`sus_score`).
  * `ueq_s` -- the short User Experience Questionnaire (Schrepp, Hinderks & Thomaschewski, 2017),
    eight seven-point semantic-differential items stored as 1..7 (-3..+3 when analysed); items
    1-4 form the pragmatic scale and 5-8 the hedonic scale.

The item TEXT lives in the frontend (`components/study/instruments.ts`) because that is what the
participant reads; this module holds the contract: which item ids exist and which values each
accepts. A response with an unknown item, a missing required item or an out-of-range value is
refused rather than stored, because a questionnaire row that cannot be scored is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Item:
    id: str
    allowed: frozenset[str]
    required: bool = True


def _scale(lo: int, hi: int) -> frozenset[str]:
    return frozenset(str(v) for v in range(lo, hi + 1))


LIKERT_5 = _scale(1, 5)
SEVEN_POINT = _scale(1, 7)
YES_NO_UNSURE = frozenset({"yes", "no", "not_sure"})


@dataclass(frozen=True)
class Instrument:
    name: str
    version: str
    items: tuple[Item, ...]

    def validate(self, responses: dict[str, Any]) -> dict[str, str]:
        """The cleaned responses, or raises ValueError naming the first problem."""
        if not isinstance(responses, dict):
            raise ValueError("responses must be an object")
        known = {item.id for item in self.items}
        unknown = sorted(set(responses) - known)
        if unknown:
            raise ValueError(f"unknown item(s): {', '.join(unknown)}")
        cleaned: dict[str, str] = {}
        for item in self.items:
            value = responses.get(item.id)
            if value is None or value == "":
                if item.required:
                    raise ValueError(f"missing required item: {item.id}")
                continue
            value = str(value)
            if value not in item.allowed:
                raise ValueError(f"invalid value for {item.id}: {value}")
            cleaned[item.id] = value
        return cleaned


LESSON_FEEDBACK = Instrument("lesson_feedback", "1.0", (
    Item("difficulty", LIKERT_5),              # 1 very easy .. 5 very difficult
    Item("easy_to_understand", LIKERT_5),      # agreement
    Item("noticed_change", YES_NO_UNSURE),
    Item("change_helpful", LIKERT_5, required=False),       # only if a change was noticed
    Item("change_distracting", LIKERT_5, required=False),   # only if a change was noticed
    Item("responded_to_needs", LIKERT_5),      # agreement
))

SUS = Instrument("sus", "1.0", tuple(Item(f"q{i}", LIKERT_5) for i in range(1, 11)))

UEQ_S = Instrument("ueq_s", "1.0", tuple(Item(f"q{i}", SEVEN_POINT) for i in range(1, 9)))

INSTRUMENTS: dict[str, Instrument] = {i.name: i for i in (LESSON_FEEDBACK, SUS, UEQ_S)}


def sus_score(responses: dict[str, str]) -> float | None:
    """Standard SUS score (0-100): odd items contribute (x-1), even items (5-x), sum x 2.5."""
    try:
        values = [int(responses[f"q{i}"]) for i in range(1, 11)]
    except (KeyError, ValueError):
        return None
    total = sum((v - 1) if i % 2 == 1 else (5 - v) for i, v in enumerate(values, start=1))
    return total * 2.5


def ueq_s_scales(responses: dict[str, str]) -> dict[str, float] | None:
    """UEQ-S pragmatic (items 1-4), hedonic (5-8) and overall means on the -3..+3 scale."""
    try:
        values = [int(responses[f"q{i}"]) - 4 for i in range(1, 9)]
    except (KeyError, ValueError):
        return None
    return {
        "pragmatic": sum(values[:4]) / 4,
        "hedonic": sum(values[4:]) / 4,
        "overall": sum(values) / 8,
    }
