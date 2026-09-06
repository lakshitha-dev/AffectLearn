"""The behaviour-driven struggle channel.

It exists because both trained channels are weak on THIS interface, and the code says so:
`section_features` records the behavioural model as "structurally blind on this UI" (two scroll
events per thirty-second window, P(confused) = 0.008 while the author was deliberately trying to
appear confused), and Chapter 4 records the facial channel's live scores compressing into a
0.127-wide band around its own threshold.

A gate that almost never opens makes the adaptive arm of a study indistinguishable, from the
learner's side, from the control condition.

These tests pin the two properties that make the channel defensible: no single indicator can
trigger an intervention alone, and no indicator can run away with the score.
"""

import pytest

from app.services import performance_signals as ps


def _score(**counts) -> float:
    return ps.struggle_score(counts)["score"]


class TestSaturation:
    """Without saturation, a learner rattling through a ten-question section would outscore one
    genuinely stuck on a two-question one. Saturation matters more than the weights."""

    def test_wrong_answers_stop_adding_past_the_cap(self):
        at_cap = _score(quiz_incorrect_count=3)
        far_past = _score(quiz_incorrect_count=30)
        assert at_cap == far_past

    def test_back_navigation_stops_adding_past_the_cap(self):
        assert _score(back_nav_count=3) == _score(back_nav_count=25)

    def test_no_single_indicator_reaches_the_actionable_floor(self):
        """The floor sits where at least two independent indicators must be present, so one
        badly-worded question cannot interrupt a learner on its own."""
        for counts in (
            {"quiz_incorrect_count": 99},
            {"back_nav_count": 99},
            {"show_answer_used": True},
        ):
            assert _score(**counts) < ps.MIN_ACTIONABLE_SCORE, counts

    def test_the_score_is_bounded(self):
        result = ps.struggle_score(
            {
                "quiz_incorrect_count": 99,
                "back_nav_count": 99,
                "show_answer_used": True,
                "time_on_section_s": 99_999,
            },
            section_words=100,
        )
        assert result["score"] <= 1.0


class TestCombining:

    def test_two_indicators_together_can_clear_the_floor(self):
        score = _score(quiz_incorrect_count=3, show_answer_used=True)
        assert score >= ps.MIN_ACTIONABLE_SCORE

    def test_more_struggle_scores_higher(self):
        mild = _score(quiz_incorrect_count=1)
        severe = _score(quiz_incorrect_count=3, back_nav_count=3, show_answer_used=True)
        assert severe > mild

    def test_a_learner_doing_fine_scores_zero(self):
        assert _score(quiz_incorrect_count=0, back_nav_count=0, show_answer_used=False) == 0.0


class TestPace:

    def test_pace_needs_a_word_count_to_mean_anything(self):
        """Without a denominator there is no pace, and inventing one would make a long section
        look like a struggling learner."""
        without = ps.struggle_score({"time_on_section_s": 5000})
        assert without["contributions"]["slow_pace"] == 0.0
        assert without["counts"]["pace_s_per_100_words"] is None

    def test_a_comfortable_pace_contributes_nothing(self):
        # 400 words in 120 seconds — 30s per 100 words, a normal reading speed.
        result = ps.struggle_score({"time_on_section_s": 120}, section_words=400)
        assert result["contributions"]["slow_pace"] == 0.0

    def test_a_laboured_pace_contributes(self):
        # 400 words in 800 seconds — 200s per 100 words.
        result = ps.struggle_score({"time_on_section_s": 800}, section_words=400)
        assert result["contributions"]["slow_pace"] > 0

    def test_pace_alone_cannot_trigger(self):
        """A learner who leaves the tab open to make tea looks identical to one labouring over a
        paragraph, which is why dwelling is the weakest indicator here."""
        result = ps.struggle_score({"time_on_section_s": 99_999}, section_words=100)
        assert result["score"] < ps.MIN_ACTIONABLE_SCORE


class TestTheReading:

    def test_returns_nothing_below_the_actionable_floor(self):
        """A stream of near-zero readings would reach the research record and the learner
        profile's affect history, where it would dilute the sustain check the OTHER channels
        depend on."""
        assert ps.detect({"quiz_incorrect_count": 1}) is None

    def test_reports_confusion_and_only_confusion(self):
        """Wrong answers and re-reading are evidence of not understanding. They say nothing about
        boredom — a bored learner clicks onward and produces no struggle indicators at all — and
        claiming otherwise would repeat the mistake of listing states no detector can see."""
        reading = ps.detect({"quiz_incorrect_count": 3, "show_answer_used": True})
        assert reading["affect_state"] == "confused"

    def test_is_labelled_as_a_heuristic(self):
        """Its confidence is a weighted count of observed behaviours, not a calibrated
        probability, and must not be compared against a model's as though they meant the same."""
        reading = ps.detect({"quiz_incorrect_count": 3, "show_answer_used": True})
        assert reading["heuristic"] is True
        assert reading["affect_source"] == "performance"

    def test_carries_the_breakdown_that_produced_it(self):
        """A bare number invites exactly the treatment this channel avoids. The breakdown is also
        what lets an analyst recompute the score under different weights from the stored record,
        rather than re-running the study."""
        reading = ps.detect({"quiz_incorrect_count": 3, "show_answer_used": True})
        assert reading["performance_breakdown"]["incorrect_answers"] > 0
        assert reading["performance_counts"]["quiz_incorrect_count"] == 3


class TestRobustness:
    """The counters come from a browser, so every field is untrusted."""

    @pytest.mark.parametrize(
        "signals",
        [None, {}, "not a dict", 42, {"quiz_incorrect_count": "many"},
         {"back_nav_count": -5}, {"time_on_section_s": None}],
    )
    def test_never_raises_on_junk(self, signals):
        result = ps.struggle_score(signals)
        assert 0.0 <= result["score"] <= 1.0

    def test_negative_counts_are_floored_not_subtracted(self):
        """A negative count from a buggy client must not REDUCE the score below zero, which
        would let a broken build silently suppress every intervention."""
        assert _score(quiz_incorrect_count=-10, back_nav_count=-10) == 0.0
