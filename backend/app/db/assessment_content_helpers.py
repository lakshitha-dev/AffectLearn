"""Authoring API for pre/post assessments — mirrors `course_content_helpers.py`.

WHY THIS EXISTS

`assessments` was empty in production and `assessment_attempts` was 0. There was no way to create
an assessment except through the designer REST API, one request at a time, so the study's only
learning-outcome measure had never been authored. Without a pre/post score there is no dependent
variable, and a perfectly executed pilot would still produce no publishable result.

MATCHED PAIRS

The pre and post tests must measure the SAME construct with DIFFERENT surface details. If an item
is reused verbatim, a gain score measures recall of that item rather than learning, and the study's
central comparison collapses. `pair_key` links the two halves of a pair so item-level analysis can
check the pairing held, and `section_title` maps each item to the section that teaches it so gains
can be attributed to specific content.

Both live in `AssessmentQuestion.explanation` as a machine-readable prefix, because the schema has
no spare columns and adding one would need a migration for what is fundamentally analysis metadata.
The prefix is stripped before the explanation is ever shown to a learner.
"""

from __future__ import annotations

from app.models.assessment import Assessment, AssessmentOption, AssessmentQuestion

# Separator between the analysis metadata and the learner-facing explanation text.
_META_SEP = " || "


def option(text: str, correct: bool = False) -> tuple[str, bool]:
    return (text, correct)


def question(
    text: str,
    options: list[tuple[str, bool]],
    *,
    pair_key: str,
    section_title: str,
    explanation: str = "",
) -> AssessmentQuestion:
    """One multiple-choice item.

    `pair_key` must match between the pre and post versions of the same construct.
    `section_title` must name a real section, so gains can be attributed to content.

    Exactly one option must be correct — a silently multi-correct item would be scored as if only
    one answer counted, and the resulting score would be wrong in a way nobody would notice.
    """
    n_correct = sum(1 for _, c in options if c)
    if n_correct != 1:
        raise ValueError(
            f"question {text[:40]!r} has {n_correct} correct options; exactly 1 is required"
        )

    return AssessmentQuestion(
        text=text,
        sort_order=0,  # set by `assessment()` in argument order
        explanation=f"pair:{pair_key}|section:{section_title}{_META_SEP}{explanation}",
        options=[
            AssessmentOption(text=t, is_correct=c, sort_order=i)
            for i, (t, c) in enumerate(options)
        ],
    )


def assessment(title: str, assessment_type: str, *questions: AssessmentQuestion) -> Assessment:
    """Build a pre or post assessment. `module_id` is attached by the seeder."""
    if assessment_type not in ("pre", "post"):
        raise ValueError(f"assessment_type must be 'pre' or 'post', got {assessment_type!r}")
    for i, q in enumerate(questions):
        q.sort_order = i
    return Assessment(
        title=title,
        assessment_type=assessment_type,
        questions=list(questions),
    )


def parse_question_meta(explanation: str | None) -> dict[str, str]:
    """Recover `{pair, section, text}` from a stored explanation. Never raises.

    Used by analysis (and by the tests that verify pre/post pairing) to read the metadata back out
    of the field it is packed into.
    """
    raw = explanation or ""
    meta_part, sep, learner_text = raw.partition(_META_SEP)
    if not sep:
        # No metadata prefix (e.g. an item authored through the designer API) — the whole field is
        # learner-facing text, and there is nothing to parse.
        return {"text": raw}
    out: dict[str, str] = {"text": learner_text}
    for chunk in meta_part.split("|"):
        key, sep, value = chunk.partition(":")
        if sep and key in ("pair", "section"):
            out[key] = value
    return out
