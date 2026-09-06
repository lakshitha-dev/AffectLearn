"""Replaying recorded cycles through the gate at other settings.

The single most important test here is `test_replay_matches_the_real_gate`. The replay is a
parameterised RESTATEMENT of `passes_adaptation_gate` -- it has to be, because the real gate
reads module-level constants and a read-only analysis endpoint must not mutate those for every
concurrent request in the process.

The cost of restating it is drift. A replay that had silently diverged from the gate would be
worse than no replay at all, because its output would still look like evidence and would still
end up in a chapter. So the two are compared across the decision space at the deployed
configuration, and the comparison fails if either moves without the other.
"""

import itertools

import pytest

from app.agents import edges
from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_PERFORMANCE,
)
from app.services import gate_replay_service as replay

pytestmark = pytest.mark.asyncio

# The real provenance markers, imported rather than retyped: `behavioral_model`, not
# `behavioral`. A wrong literal here would make every decisive-channel test silently
# exercise the advisory path instead.
BEHAVIORAL = AFFECT_SOURCE_BEHAVIORAL
PERFORMANCE = AFFECT_SOURCE_PERFORMANCE


def _replay_defaults(**over):
    """Replay parameters matching the deployed configuration."""
    params = {
        "min_confidence": edges.ADAPT_MIN_CONFIDENCE,
        "min_consecutive": edges.ADAPT_MIN_CONSECUTIVE,
        "cooldown_cycles": edges.ADAPT_COOLDOWN_CYCLES,
        "decisive_sources": list(edges.DECISIVE_AFFECT_SOURCES),
        "adapt_states": list(edges.ADAPT_STATES),
    }
    params.update(over)
    return params


def test_replay_matches_the_real_gate():
    """Across the decision space, at the deployed settings, the twin agrees with the original.

    Covers every axis the gate branches on: no state, an unactionable state, confidence either
    side of the floor, sustained and unsustained history, inside and outside the cooldown, and a
    decisive versus an advisory channel.
    """
    states = [None, "engaged", "confused"]
    confidences = [0.0, 0.49, 0.51, 0.69, 0.71, 0.95]
    histories = [[], ["confused"], ["confused", "confused"], ["bored", "confused"]]
    cycles = [None, 5]
    last_adaptations = [None, 3, 1]
    sources = [None, BEHAVIORAL, PERFORMANCE, "category_model"]

    checked = 0
    for state, confidence, history, cycle, last, source in itertools.product(
        states, confidences, histories, cycles, last_adaptations, sources
    ):
        real = edges.passes_adaptation_gate(state, confidence, history, cycle, last, source)
        twin = replay.replay_gate(
            affect_state=state,
            affect_confidence=confidence,
            affect_history=history,
            cycle_number=cycle,
            last_adaptation_cycle=last,
            affect_source=source,
            min_confidence=edges.min_confidence_for(source),
            **{k: v for k, v in _replay_defaults().items() if k != "min_confidence"},
        )
        assert real == twin, (
            f"replay diverged from the gate: state={state} conf={confidence} "
            f"history={history} cycle={cycle} last={last} source={source} "
            f"gate={real} replay={twin}"
        )
        checked += 1

    # Guards against the comparison silently covering nothing if a list above is emptied.
    assert checked > 500


class TestWalkingASession:

    def _reading(self, cycle, state="confused", confidence=0.9, source=BEHAVIORAL):
        return {
            "cycle_number": cycle,
            "affect_state": state,
            "affect_confidence": confidence,
            "affect_source": source,
        }

    def test_sustain_counts_the_current_cycle(self):
        """The profiler folds the current affect in BEFORE the gate runs, so a requirement of 2
        means "this cycle and the previous one agree" — not the two before this one."""
        readings = [self._reading(1), self._reading(2)]
        result = replay.replay_session(readings, **_replay_defaults(min_consecutive=2))

        assert len(result["interventions"]) == 1
        assert result["interventions"][0]["cycle_number"] == 2

    def test_cooldown_suppresses_the_cycles_after_an_intervention(self):
        readings = [self._reading(c) for c in range(1, 8)]
        result = replay.replay_session(
            readings, **_replay_defaults(min_consecutive=2, cooldown_cycles=3)
        )

        fired = [i["cycle_number"] for i in result["interventions"]]
        assert fired == [2, 5]

    def test_a_broken_run_resets_the_sustain(self):
        readings = [
            self._reading(1),
            self._reading(2, state="engaged"),
            self._reading(3),
        ]
        result = replay.replay_session(readings, **_replay_defaults(min_consecutive=2))

        assert result["interventions"] == []

    def test_raising_the_floor_removes_interventions(self):
        readings = [self._reading(c, confidence=0.65) for c in range(1, 6)]

        low = replay.replay_session(readings, **_replay_defaults(min_confidence=0.5))
        high = replay.replay_session(readings, **_replay_defaults(min_confidence=0.7))

        assert len(low["interventions"]) > 0
        assert high["interventions"] == []

    def test_every_withheld_cycle_records_a_reason(self):
        """The reason distribution is the whole point: a run that is mostly `low_confidence` is a
        threshold set too high, one that is mostly `cooldown` is a suppression window too long."""
        readings = [self._reading(c, confidence=0.2) for c in range(1, 4)]
        result = replay.replay_session(readings, **_replay_defaults())

        assert result["reasons"][edges.GATE_LOW_CONFIDENCE] == 3
        assert sum(result["reasons"].values()) == len(readings)

    def test_promoting_an_advisory_channel_is_answerable_before_promoting_it(self):
        """The live question this exists for. The performance channel ships advisory; this is how
        you find out what promoting it would cost before doing it."""
        readings = [self._reading(c, source=PERFORMANCE) for c in range(1, 6)]

        advisory = replay.replay_session(
            readings, **_replay_defaults(decisive_sources=[BEHAVIORAL])
        )
        promoted = replay.replay_session(
            readings, **_replay_defaults(decisive_sources=[BEHAVIORAL, PERFORMANCE])
        )

        assert advisory["interventions"] == []
        assert advisory["reasons"][edges.GATE_CHANNEL_ADVISORY] > 0
        assert len(promoted["interventions"]) > 0


class TestPrecision:

    def _intervention(self, cycle):
        return {"cycle_number": cycle}

    def test_is_withheld_on_a_thin_sample(self):
        """The deployed 0.500 rests on nine warranted offers in eighteen, with an interval
        spanning [0.273, 0.737]. A ratio over three would be worse than reporting nothing."""
        result = replay._precision(
            [self._intervention(1)], [{"cycle_number": 1, "affect": "confused"}]
        )
        assert result["precision"] is None
        assert "fewer than" in result["note"]

    def test_counts_only_interventions_with_a_report_nearby(self):
        """No report means no evidence either way. Counting silence as "the learner was fine"
        would systematically understate precision."""
        interventions = [self._intervention(c) for c in range(1, 21)]
        # Reports stop at cycle 12. Interventions at 13 and 14 still match it, because the window
        # is +/- 2 cycles -- self-reports arrive at section boundaries, not on the cycle clock,
        # so an exact match would find almost nothing.
        reports = [{"cycle_number": c, "affect": "confused"} for c in range(1, 13)]

        result = replay._precision(interventions, reports)

        assert result["matched_interventions"] == 14
        assert result["precision"] == 1.0
        # The six interventions with no report nearby are excluded, not counted as unwarranted.
        assert len(interventions) - result["matched_interventions"] == 6

    def test_an_engaged_self_report_makes_an_intervention_unwarranted(self):
        interventions = [self._intervention(c) for c in range(1, 21)]
        reports = [
            {"cycle_number": c, "affect": "confused" if c % 2 else "engaged"}
            for c in range(1, 21)
        ]

        result = replay._precision(interventions, reports)

        assert result["precision"] == 0.5

    def test_the_nearest_report_decides_not_any_report_in_the_window(self):
        """"Any negative report nearby" is systematically generous: it would count an
        intervention as warranted whenever a negative report sits anywhere in range, even when
        the report closest to the moment said the learner was fine — inflating precision by
        exactly the amount the window is widened.
        """
        interventions = [self._intervention(10 + i) for i in range(12)]
        reports = [
            # Immediately alongside each intervention: the learner was fine.
            *[{"cycle_number": 10 + i, "affect": "engaged"} for i in range(12)],
            # Two cycles out, at the edge of the window: they were confused.
            *[{"cycle_number": 12 + i, "affect": "confused"} for i in range(12)],
        ]

        result = replay._precision(interventions, reports)

        assert result["matched_interventions"] >= replay.MIN_PRECISION_SAMPLE
        assert result["precision"] == 0.0

    def test_reports_outside_the_window_do_not_match(self):
        interventions = [self._intervention(1)]
        far = [{"cycle_number": 50, "affect": "confused"}]

        assert replay._precision(interventions, far)["matched_interventions"] == 0


class TestSweep:

    async def test_reports_the_caveat_with_the_numbers(self, db):
        """A sweep table is the kind of output that gets pasted into a chapter, so the caveat has
        to travel with it rather than living only in a docstring."""
        result = await replay.sweep(db, confidence_floors=[0.5, 0.7])

        assert "Replays recorded readings only" in result["caveat"]
        assert len(result["rows"]) == 2

    async def test_reports_what_was_held_fixed(self, db):
        """A sweep varies one thing; the reader needs to know what the others were."""
        result = await replay.sweep(db, confidence_floors=[0.7])

        held = result["held_fixed"]
        assert held["min_consecutive"] == edges.ADAPT_MIN_CONSECUTIVE
        assert held["cooldown_cycles"] == edges.ADAPT_COOLDOWN_CYCLES

    async def test_an_empty_record_returns_zeroes_not_an_error(self, db):
        result = await replay.sweep(db, confidence_floors=[0.7])

        assert result["sessions"] == 0
        assert result["rows"][0]["interventions"] == 0
        assert result["rows"][0]["precision"] is None
