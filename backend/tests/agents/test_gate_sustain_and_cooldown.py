"""Two faults that together prevented the adaptation gate from EVER passing in production.

Observed in the live Pipeline Monitor: the facial channel reported `confused` for several
consecutive cycles while the gate withheld, alternating between `not_sustained` and `cooldown`,
and the Deliver node had never run.

1. `affect_history` interleaves modalities. The graph runs once per channel per cycle, so both
   the behavioural and the facial pass append under the same `cycle_number`. The last two
   entries are then usually the two channels disagreeing inside ONE cycle, not one state
   holding across two -- which is what the consecutive-cycle condition exists to test.

2. The cooldown marker outlived its session. `last_adaptation_cycle` is compared against
   `cycle_number`, which restarts at 1 per session, but the profile is keyed by learner. A
   marker left by an earlier, longer session exceeds the current cycle, the subtraction goes
   negative, and the gate withholds `cooldown` permanently. Fixing the profile-persistence
   migration made this WORSE: while the profile was Redis-only it was lost on restart, which
   accidentally cleared the stale marker.

Together these are the likely cause of the recorded "0 of 1,473 cycles reached the threshold",
which had been attributed to the confidence threshold being too high.
"""

import pytest

from app.agents.edges import (
    GATE_COOLDOWN,
    GATE_NOT_SUSTAINED,
    GATE_OK,
    passes_adaptation_gate,
)
from app.services.profile_service import apply_affect, sustain_history

BEH = "behavioral"
FAC = "category_model"


def _two_cycles_of_disagreement() -> dict:
    """Behaviour says engaged, face says confused, for two cycles running."""
    p: dict = {}
    for cycle in (1, 2):
        p = apply_affect(p, "engaged", cycle, 0, source=BEH)
        p = apply_affect(p, "confused", cycle, 0, source=FAC)
    return p


class TestPerSourceSustain:
    def test_interleaved_history_hides_a_sustained_state(self):
        """The bug, pinned. Face was confused twice running; the shared history cannot show it."""
        p = _two_cycles_of_disagreement()
        assert p["affect_history"] == ["engaged", "confused", "engaged", "confused"]
        allowed, reason = passes_adaptation_gate(
            "confused", 0.80, p["affect_history"], 3, None
        )
        assert (allowed, reason) == (False, GATE_NOT_SUSTAINED)

    def test_per_source_history_reveals_it(self):
        p = _two_cycles_of_disagreement()
        assert sustain_history(p, FAC) == ["confused", "confused"]
        allowed, reason = passes_adaptation_gate("confused", 0.80, sustain_history(p, FAC), 3, None)
        assert (allowed, reason) == (True, GATE_OK)

    def test_channels_do_not_contaminate_each_other(self):
        p = _two_cycles_of_disagreement()
        assert sustain_history(p, BEH) == ["engaged", "engaged"]
        assert sustain_history(p, FAC) == ["confused", "confused"]

    def test_a_single_cycle_is_still_not_sustained(self):
        """Guards against the fix over-firing: one confused reading must not qualify."""
        p = apply_affect({}, "confused", 1, 0, source=FAC)
        allowed, reason = passes_adaptation_gate("confused", 0.80, sustain_history(p, FAC), 1, None)
        assert (allowed, reason) == (False, GATE_NOT_SUSTAINED)

    def test_a_state_that_flips_within_one_channel_is_not_sustained(self):
        p = apply_affect({}, "confused", 1, 0, source=FAC)
        p = apply_affect(p, "engaged", 2, 0, source=FAC)
        p = apply_affect(p, "confused", 3, 0, source=FAC)
        allowed, reason = passes_adaptation_gate("confused", 0.80, sustain_history(p, FAC), 3, None)
        assert (allowed, reason) == (False, GATE_NOT_SUSTAINED)

    def test_research_record_is_unchanged(self):
        """`affect_history` is persisted and analysed; the fix must not alter its shape."""
        p = _two_cycles_of_disagreement()
        assert p["affect_history"] == ["engaged", "confused", "engaged", "confused"]
        assert isinstance(p["affect_history_by_source"], dict)

    def test_falls_back_when_the_source_is_unknown(self):
        """A profile persisted before per-source tracking must behave as it did."""
        legacy = {"affect_history": ["confused", "confused"]}
        assert sustain_history(legacy, None) == ["confused", "confused"]
        assert sustain_history(legacy, "a_source_never_seen") == ["confused", "confused"]

    def test_an_empty_affect_does_not_append(self):
        p = apply_affect({}, None, 1, 0, source=FAC)
        assert sustain_history(p, FAC) == []


class TestCooldownScoping:
    def test_a_marker_from_a_longer_earlier_session_blocks_forever(self):
        """The bug, pinned: cycle 24 against a marker of 40 is -16, permanently under the window."""
        allowed, reason = passes_adaptation_gate(
            "confused", 0.80, ["confused", "confused"], 24, 40
        )
        assert (allowed, reason) == (False, GATE_COOLDOWN)

    def test_ignoring_a_foreign_marker_lets_the_gate_pass(self):
        allowed, reason = passes_adaptation_gate(
            "confused", 0.80, ["confused", "confused"], 24, None
        )
        assert (allowed, reason) == (True, GATE_OK)

    @pytest.mark.parametrize(
        "cycle,last_adapt,expected",
        [
            (10, 9, GATE_COOLDOWN),   # 1 cycle ago -- inside the 3-cycle window
            (11, 9, GATE_COOLDOWN),   # 2 cycles ago
            (12, 9, GATE_OK),         # 3 cycles ago -- window elapsed
            (20, 9, GATE_OK),         # well clear
        ],
    )
    def test_a_marker_from_this_session_still_enforces_the_window(
        self, cycle, last_adapt, expected
    ):
        """The scoping fix must not disable the cooldown for markers that are legitimate."""
        _, reason = passes_adaptation_gate(
            "confused", 0.80, ["confused", "confused"], cycle, last_adapt
        )
        assert reason == expected
