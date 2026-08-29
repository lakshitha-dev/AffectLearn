"""Per-section confusion features derived from the existing research-event stream.

These features ship DARK — they are logged for future training and must never reach the live
model, whose input width is frozen by the deployed ONNX (`behavioral_inference.py:276`).
"""

from __future__ import annotations

import pytest

from app.services import section_features as sf

SEC = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def ev(kind: str, section_id: str = SEC, **payload):
    return {"event_type": kind, "payload": {"section_id": section_id, **payload}}


def test_empty_stream_yields_zeroed_row():
    f = sf.extract([], SEC)
    assert f["section_id"] == SEC
    assert f["time_on_section_s"] == 0.0
    assert f["quiz_attempt_count"] == 0
    assert f["show_answer_used"] == 0


def test_ignores_other_sections():
    """A learner's stream contains every section; features must be per-section."""
    f = sf.extract(
        [
            ev(sf.SHOW_ANSWER_REVEALED, section_id=OTHER),
            ev(sf.QUIZ_SUBMITTED, section_id=OTHER, is_correct=False),
        ],
        SEC,
    )
    assert f["show_answer_used"] == 0
    assert f["quiz_attempt_count"] == 0


def test_show_answer_is_a_flag_not_a_count():
    f = sf.extract([ev(sf.SHOW_ANSWER_REVEALED), ev(sf.SHOW_ANSWER_REVEALED)], SEC)
    assert f["show_answer_used"] == 1


def test_quiz_attempts_correctness_and_timing():
    f = sf.extract(
        [
            ev(sf.QUIZ_SUBMITTED, is_correct=False, response_time_ms=4000),
            ev(sf.QUIZ_SUBMITTED, is_correct=False, response_time_ms=6000),
            ev(sf.QUIZ_SUBMITTED, is_correct=True, response_time_ms=2000),
        ],
        SEC,
    )
    assert f["quiz_attempt_count"] == 3
    assert f["quiz_incorrect_count"] == 2
    assert f["quiz_response_time_ms_mean"] == 4000.0


def test_completion_time_takes_max_not_sum():
    """The completion route is idempotent and re-emits; summing would double-count a revisit."""
    f = sf.extract(
        [
            ev(sf.SECTION_COMPLETED, time_spent_seconds=120),
            ev(sf.SECTION_COMPLETED, time_spent_seconds=90),
        ],
        SEC,
    )
    assert f["time_on_section_s"] == 120.0


def test_views_and_back_navigation_counted():
    f = sf.extract(
        [ev(sf.SECTION_VIEWED, dwell_seconds=30), ev(sf.SECTION_VIEWED, dwell_seconds=45),
         ev(sf.SECTION_BACK_NAV), ev(sf.SECTION_BACK_NAV), ev(sf.SECTION_BACK_NAV)],
        SEC,
    )
    assert f["view_count"] == 2
    assert f["back_nav_count"] == 3
    assert f["time_on_section_s"] == 45.0


def test_adaptation_dismissal_tracked():
    f = sf.extract(
        [
            ev(sf.ADAPTATION_INTERACTION, interaction="dismissed"),
            ev(sf.ADAPTATION_INTERACTION, interaction="accepted"),
        ],
        SEC,
    )
    assert f["adaptation_delivered_count"] == 2
    assert f["adaptation_dismissed_count"] == 1


def test_time_normalised_by_measured_words():
    f = sf.extract(
        [ev(sf.SECTION_COMPLETED, time_spent_seconds=300)],
        SEC,
        section_shape={"n_words": 300},
    )
    assert f["time_per_100_words"] == 100.0


def test_no_word_count_passes_dwell_through_rather_than_dividing_by_zero():
    f = sf.extract([ev(sf.SECTION_COMPLETED, time_spent_seconds=300)], SEC, section_shape={})
    assert f["time_per_100_words"] == 300.0


@pytest.mark.parametrize("bad", [None, "abc", {}])
def test_malformed_time_never_raises(bad):
    f = sf.extract([ev(sf.SECTION_COMPLETED, time_spent_seconds=bad)], SEC)
    assert f["time_on_section_s"] == 0.0


def test_accepts_orm_style_objects_not_just_dicts():
    class Row:
        def __init__(self, t, p):
            self.event_type, self.payload = t, p

    f = sf.extract([Row(sf.SHOW_ANSWER_REVEALED, {"section_id": SEC})], SEC)
    assert f["show_answer_used"] == 1


def test_every_declared_feature_is_present_in_the_row():
    """FEATURE_NAMES is the contract an analyst reads; the row must not drift from it."""
    f = sf.extract([], SEC)
    for name in sf.FEATURE_NAMES:
        assert name in f, f"{name} declared in FEATURE_NAMES but missing from the row"


def test_section_shape_from_real_block_objects():
    from app.models.course import BlockType

    class B:
        def __init__(self, t, c, o=0):
            self.block_type, self.content, self.sort_order = t, c, o

    shape = sf.section_shape_from_blocks([
        B(BlockType.text, {"text": "one two three four five"}, 0),
        B(BlockType.code, {"language": "python", "code": "x = 1"}, 1),
        B(BlockType.exercise, {"prompt": "q", "answer": "a"}, 2),
    ])
    assert shape["n_blocks"] == 3
    assert shape["n_code_blocks"] == 1
    assert shape["has_exercise"] is True
    assert shape["has_quiz"] is False
    assert shape["n_words"] > 0


def test_shape_word_count_excludes_assessment_text():
    """Shares `_render_body`, which excludes assessments — so n_words stays consistent with the
    text a learner actually reads, and with what the LLM prompt sees."""
    from app.models.course import BlockType

    class B:
        def __init__(self, t, c, o=0):
            self.block_type, self.content, self.sort_order = t, c, o

    shape = sf.section_shape_from_blocks([
        B(BlockType.exercise, {"prompt": "a very long question " * 20, "answer": "secret"}, 0),
    ])
    assert shape["n_words"] < 20


# ── signals path (LIVE) ───────────────────────────────────────────────────────
#
# `extract` reads landed events (offline analysis). `from_signals` uses counters the client sent
# (live emit), because research events go to a Redis stream drained asynchronously into Postgres
# and are therefore NOT queryable when a section is completed. Two code paths, one row shape —
# these tests exist so they cannot drift apart.


def test_signal_and_event_paths_agree():
    """The same interaction, expressed either way, must yield an identical row."""
    shape = {"n_words": 200, "n_blocks": 4, "n_code_blocks": 1,
             "has_exercise": True, "has_quiz": True}

    from_events = sf.extract(
        [
            ev(sf.SECTION_COMPLETED, time_spent_seconds=240),
            ev(sf.SECTION_VIEWED, dwell_seconds=100),
            ev(sf.SECTION_VIEWED, dwell_seconds=140),
            ev(sf.SECTION_BACK_NAV),
            ev(sf.SHOW_ANSWER_REVEALED),
            ev(sf.QUIZ_SUBMITTED, is_correct=False, response_time_ms=5000),
            ev(sf.QUIZ_SUBMITTED, is_correct=True, response_time_ms=3000),
            ev(sf.ADAPTATION_INTERACTION, interaction="dismissed"),
        ],
        SEC,
        section_shape=shape,
    )

    from_signals = sf.from_signals(
        {
            "time_on_section_s": 240,
            "view_count": 2,
            "back_nav_count": 1,
            "show_answer_used": True,
            "quiz_attempt_count": 2,
            "quiz_incorrect_count": 1,
            "quiz_response_time_ms_mean": 4000.0,
            "adaptation_delivered_count": 1,
            "adaptation_dismissed_count": 1,
        },
        SEC,
        section_shape=shape,
    )

    assert from_events == from_signals


def test_signals_absent_yields_valid_zeroed_row():
    """An old client that sends nothing must still produce a well-formed row, not a crash."""
    row = sf.from_signals(None, SEC)
    for name in sf.FEATURE_NAMES:
        assert name in row
    assert row["time_on_section_s"] == 0.0
    assert row["show_answer_used"] == 0


@pytest.mark.parametrize("junk", [{"time_on_section_s": "abc"}, {"view_count": None},
                                  {"back_nav_count": [1, 2]}, {"show_answer_used": "yes"}])
def test_malformed_signals_never_raise(junk):
    row = sf.from_signals(junk, SEC)
    assert isinstance(row["time_on_section_s"], float)


def test_signals_normalise_by_words_like_the_event_path():
    row = sf.from_signals({"time_on_section_s": 300}, SEC, section_shape={"n_words": 300})
    assert row["time_per_100_words"] == 100.0


def test_negative_time_is_clamped_not_propagated():
    row = sf.from_signals({"time_on_section_s": -50}, SEC)
    assert row["time_on_section_s"] == 0.0


def test_live_model_feature_schema_is_untouched():
    """The dark-ship invariant.

    Section features must never widen the LIVE behavioural model's input. The deployed ONNX
    expects 16 features x 5 aggregates = 80, and `behavioral_inference.py` raises on any
    mismatch — so appending here would break inference in production, not fail loudly in CI.
    Names must not collide either, or an analyst joining the two datasets silently merges
    unrelated columns.
    """
    from app.services.feature_engineering import FEATURE_NAMES as LIVE, N_FEATURES

    assert N_FEATURES == 16, "live feature width changed — deployed ONNX expects 16"
    assert not (set(LIVE) & set(sf.FEATURE_NAMES)), "section features collide with live names"
