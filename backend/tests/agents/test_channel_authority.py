"""Intervention authority is granted by measured reliability, not momentary confidence.

The gate thresholds a model's SELF-REPORTED confidence. That is a different question from
whether the channel is any good, and here the two diverge sharply:

  behavioural confusion   AUC 0.7408-0.7473, bootstrap CI excludes chance, permutation p 0.0005
  facial confusion        AUC 0.5064 with p 0.108 on the only corpus where both channels are
                          recorded against one human label; in production, P(confused) inside a
                          0.127-wide band centred on 0.502

Because each modality arrives on its own WebSocket message, each runs the whole graph and gets
its own gate evaluation, so both channels were independently decisive. A fixed threshold against
a distribution centred on that threshold fires on roughly half of all cycles whatever signal is
carried — so the weaker channel triggered MORE interventions than the stronger one, and
`AFFECT_DETECTION_MODE=behavioral_only` did not prevent it (that flag only skips fusion pairing).

Two properties matter as much as the policy and are pinned below:

  1. It must FAIL LOUD, not silent. An unclassified channel is non-decisive — the safe direction
     for an interruption — but it warns every evaluation, because a channel that quietly never
     intervenes is indistinguishable, during a pilot, from a system that cannot.
  2. The authority check runs LAST, so `channel_advisory` appears only when the channel would
     OTHERWISE have intervened. That makes the count of those cycles a direct measurement of
     what the advisory channel would have done — evidence for or against promoting it.
"""

import pytest

from app.agents import edges
from app.agents.edges import (
    GATE_CHANNEL_ADVISORY,
    GATE_COOLDOWN,
    GATE_LOW_CONFIDENCE,
    GATE_NOT_SUSTAINED,
    GATE_OK,
    GATE_STATE_NOT_ACTIONABLE,
    is_decisive,
    passes_adaptation_gate,
)
from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_CATEGORY,
    AFFECT_SOURCE_ENGAGEMENT,
    AFFECT_SOURCE_FUSION,
)

SUSTAINED = ["confused", "confused"]


def _gate(source, state="confused", conf=0.80, history=None, cycle=10, last=None):
    return passes_adaptation_gate(state, conf, history or SUSTAINED, cycle, last, source)


class TestWhoMayIntervene:
    @pytest.mark.parametrize("source", [AFFECT_SOURCE_BEHAVIORAL, AFFECT_SOURCE_FUSION])
    def test_the_validated_channels_may(self, source):
        assert _gate(source) == (True, GATE_OK)

    @pytest.mark.parametrize("source", [AFFECT_SOURCE_CATEGORY, AFFECT_SOURCE_ENGAGEMENT])
    def test_the_facial_channels_may_not(self, source):
        assert _gate(source) == (False, GATE_CHANNEL_ADVISORY)

    def test_a_missing_source_fails_open(self):
        """The gate is called directly by tests and by callers predating provenance."""
        assert _gate(None) == (True, GATE_OK)

    def test_an_unclassified_source_is_advisory_and_warns(self, capsys):
        # structlog renders to stdout rather than through stdlib logging, so caplog is empty
        # here and capsys is what actually sees the line.
        allowed, reason = _gate("some_new_channel")
        assert (allowed, reason) == (False, GATE_CHANNEL_ADVISORY)
        out = capsys.readouterr().out
        assert "affect_source_unclassified" in out, "must never be silent"
        assert "some_new_channel" in out, "the line must name the channel"

    def test_the_policy_can_be_disabled_entirely(self, monkeypatch):
        """An empty allowlist restores the previous behaviour exactly."""
        monkeypatch.setattr(edges, "DECISIVE_AFFECT_SOURCES", ())
        assert _gate(AFFECT_SOURCE_CATEGORY) == (True, GATE_OK)

    def test_a_channel_can_be_promoted_without_a_code_change(self, monkeypatch):
        """If step 1 or 2 re-validates the facial channel, this is the whole change."""
        monkeypatch.setattr(
            edges, "DECISIVE_AFFECT_SOURCES",
            (AFFECT_SOURCE_BEHAVIORAL, AFFECT_SOURCE_FUSION, AFFECT_SOURCE_CATEGORY),
        )
        assert _gate(AFFECT_SOURCE_CATEGORY) == (True, GATE_OK)

    def test_is_decisive_is_usable_on_its_own(self):
        assert is_decisive(AFFECT_SOURCE_BEHAVIORAL) is True
        assert is_decisive(AFFECT_SOURCE_CATEGORY) is False


class TestTheReasonNamesTheBindingConstraint:
    """The check runs last, so an advisory cycle still reports what actually stopped it.

    Checking authority earlier would collapse every withheld advisory cycle to
    `channel_advisory`, destroying the ability to ask how often the facial channel was even
    close to firing.
    """

    @pytest.mark.parametrize(
        "state,conf,history,expected",
        [
            ("engaged", 0.99, ["engaged", "engaged"], GATE_STATE_NOT_ACTIONABLE),
            ("confused", 0.30, SUSTAINED, GATE_LOW_CONFIDENCE),
            ("confused", 0.80, ["confused"], GATE_NOT_SUSTAINED),
        ],
    )
    def test_an_advisory_channel_still_reports_the_real_reason(
        self, state, conf, history, expected
    ):
        _, reason = _gate(AFFECT_SOURCE_CATEGORY, state=state, conf=conf, history=history)
        assert reason == expected

    def test_cooldown_still_takes_precedence(self):
        _, reason = _gate(AFFECT_SOURCE_CATEGORY, cycle=11, last=10)
        assert reason == GATE_COOLDOWN

    def test_advisory_appears_only_when_the_channel_would_have_fired(self):
        """So counting these cycles measures what the advisory channel would have done."""
        _, advisory = _gate(AFFECT_SOURCE_CATEGORY)
        decisive_allowed, decisive_reason = _gate(AFFECT_SOURCE_BEHAVIORAL)
        assert advisory == GATE_CHANNEL_ADVISORY
        assert (decisive_allowed, decisive_reason) == (True, GATE_OK), (
            "identical inputs: the ONLY difference is which channel reported them"
        )


class TestNoOverSuppression:
    """A gate that withholds too readily produces a system that never intervenes — which in a
    pilot cannot be distinguished from one that cannot intervene at all."""

    def test_the_decisive_channel_is_unaffected_by_the_new_check(self):
        assert _gate(AFFECT_SOURCE_BEHAVIORAL) == (True, GATE_OK)

    def test_every_other_gate_condition_still_applies_to_the_decisive_channel(self):
        assert _gate(AFFECT_SOURCE_BEHAVIORAL, state="engaged")[1] == GATE_STATE_NOT_ACTIONABLE
        assert _gate(AFFECT_SOURCE_BEHAVIORAL, conf=0.10)[1] == GATE_LOW_CONFIDENCE
        assert _gate(AFFECT_SOURCE_BEHAVIORAL, history=["confused"])[1] == GATE_NOT_SUSTAINED

    def test_at_least_one_channel_is_decisive_by_default(self):
        """Guards the configuration itself: an allowlist excluding everything would ship a
        platform that can never adapt, and RQ4 would be unanswerable by construction."""
        assert edges.DECISIVE_AFFECT_SOURCES, "the default must not be empty-by-accident"
        assert AFFECT_SOURCE_BEHAVIORAL in edges.DECISIVE_AFFECT_SOURCES

    def test_the_default_authorises_the_best_measured_channel(self):
        """Behavioural outperforms facial on paired data — 0.7473 vs 0.5064 AUC."""
        assert is_decisive(AFFECT_SOURCE_BEHAVIORAL)
        assert not is_decisive(AFFECT_SOURCE_CATEGORY)
