"""Request/response schemas for the post-study satisfaction survey (Story 6.4).

The instrument is a small set of 5-point Likert items across the four AC dimensions
(perceived adaptation quality, learning experience, willingness to continue, overall
satisfaction). The submit request carries a `responses` dict keyed by `Q1`..`Qn`, each value a
1-5 Likert string from `LIKERT_5`. The shape is validated at the schema boundary: unknown keys
are rejected and all known keys must be present, so a malformed payload yields a 422 before any
DB write (mirrors `app/schemas/questionnaire.py`'s `field_validator` pattern).

The >= 4.0/5 success target is a research metric only — it is NOT enforced here; any valid
1-5 answer set (including low scores) passes validation and reaches the Thank You page.
Response models use `CamelModel` for the camelCase REST wire convention.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import field_validator

from app.schemas.base import CamelModel

# --- Known value set + question keys (mirror satisfaction-questions.ts) ----------------

LIKERT_5 = {"1", "2", "3", "4", "5"}

# Q1 perceived adaptation quality ("The platform helped me when I needed it" — UX anchor)
# Q2 learning experience  | Q3 willingness to continue  | Q4 overall satisfaction
SURVEY_KEYS = ("Q1", "Q2", "Q3", "Q4")
REQUIRED_KEYS = set(SURVEY_KEYS)
ALL_KEYS = REQUIRED_KEYS


class SurveySubmitRequest(CamelModel):
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

        for key in SURVEY_KEYS:
            v = value[key]
            if not isinstance(v, str) or v not in LIKERT_5:
                raise ValueError(f"{key} must be one of {sorted(LIKERT_5)}")

        return value


class SurveyResponseSchema(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    responses: dict[str, Any]
    submitted_at: datetime
