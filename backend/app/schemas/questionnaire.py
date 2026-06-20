"""Request/response schemas for the pre-study questionnaire (Story 6.3).

The instrument (Sections A–E, Q1–Q14) is heterogeneous, so the submit request carries a
`responses` dict keyed by `Q1`..`Q14`. The shape is validated at the schema boundary:

- Single-select / Likert items (Q1-Q7, Q10, Q11) must be a string drawn from that question's
  known value set.
- The Likert matrix (Q8) must be an object with the 4 affect rows, each a 1-5 Likert value.
- The multi-select (Q9) must be a list (possibly empty — the spec implies it is optional) of
  values drawn from its known set.
- The self-efficacy block (Q12-Q14) are 1-5 Likert values.

Unknown keys are rejected and required keys must be present (Q9 may be empty but must be
present as a list) so a malformed payload yields a 422 before any DB write. Consent
(Section F / Q15) is intentionally absent — Epic 3 already collects it. Response models use
`CamelModel` for the camelCase REST wire convention.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import field_validator

from app.schemas.base import CamelModel

# --- Known value sets (mirror pre-study-questionnaire.md, Q1–Q14) ---------------------

LIKERT_5 = {"1", "2", "3", "4", "5"}

SINGLE_SELECT_OPTIONS: dict[str, set[str]] = {
    "Q1": {"18-20", "21-23", "24-26", "27+"},
    "Q2": {"male", "female", "nonbinary", "prefer_not_to_say"},
    "Q3": {"daily", "several_per_week", "weekly", "few_per_month", "rarely_never"},
    "Q4": {"0", "1-2", "3-5", "6-10", "10+"},
    "Q5": {"0", "1-2", "3-5", "6-10", "10+"},
    "Q6": LIKERT_5,
    "Q7": {"video", "text", "interactive", "visual"},
    "Q10": {"yes_multiple", "yes_once_twice", "no_considered", "no_never"},
    "Q11": LIKERT_5,
    "Q12": LIKERT_5,
    "Q13": LIKERT_5,
    "Q14": LIKERT_5,
}

# Q8 — Likert matrix: one 1-5 value per affect row.
MATRIX_ROWS = {"boredom", "confusion", "frustration", "engagement"}

# Q9 — multi-select "select all that apply" (may be empty).
MULTI_SELECT_OPTIONS = {
    "push_through",
    "take_break",
    "skip_ahead",
    "search_alternatives",
    "stop_session",
    "ask_help",
}

REQUIRED_KEYS = (
    set(SINGLE_SELECT_OPTIONS) | {"Q8", "Q9"}
)
ALL_KEYS = REQUIRED_KEYS


class QuestionnaireSubmitRequest(CamelModel):
    responses: dict[str, Any]

    @field_validator("responses")
    @classmethod
    def _validate_responses(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("responses must be an object")

        keys = set(value)
        unknown = keys - ALL_KEYS
        if unknown:
            raise ValueError(f"unknown question keys: {sorted(unknown)}")
        missing = REQUIRED_KEYS - keys
        if missing:
            raise ValueError(f"missing required question keys: {sorted(missing)}")

        # Single-select / Likert single-value items
        for key, options in SINGLE_SELECT_OPTIONS.items():
            v = value[key]
            if not isinstance(v, str) or v not in options:
                raise ValueError(f"{key} must be one of {sorted(options)}")

        # Q8 — Likert matrix
        matrix = value["Q8"]
        if not isinstance(matrix, dict) or set(matrix) != MATRIX_ROWS:
            raise ValueError(f"Q8 must be an object with rows {sorted(MATRIX_ROWS)}")
        for row, rating in matrix.items():
            if not isinstance(rating, str) or rating not in LIKERT_5:
                raise ValueError(f"Q8.{row} must be one of {sorted(LIKERT_5)}")

        # Q9 — multi-select (may be empty list)
        multi = value["Q9"]
        if not isinstance(multi, list):
            raise ValueError("Q9 must be a list")
        invalid = [m for m in multi if not isinstance(m, str) or m not in MULTI_SELECT_OPTIONS]
        if invalid:
            raise ValueError(f"Q9 contains invalid options: {invalid}")
        if len(set(multi)) != len(multi):
            raise ValueError("Q9 must not contain duplicate options")

        return value


class QuestionnaireResponseSchema(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    responses: dict[str, Any]
    submitted_at: datetime
