"""Tests for the rule-based pedagogical fallback (Story 5.1 AC1)."""

from app.agents.fallbacks import ACTION_TYPES, URGENCIES, rule_based_strategy


def test_each_affect_maps_to_documented_action():
    assert rule_based_strategy("confused")["action_type"] == "show_hint"
    assert rule_based_strategy("confused")["urgency"] == "medium"
    assert rule_based_strategy("frustrated")["action_type"] == "simplify"
    assert rule_based_strategy("frustrated")["urgency"] == "high"
    assert rule_based_strategy("bored")["action_type"] == "skip_ahead"
    assert rule_based_strategy("bored")["urgency"] == "low"
    assert rule_based_strategy("engaged")["action_type"] == "no_action"
    assert rule_based_strategy("engaged")["urgency"] == "low"


def test_unknown_or_missing_affect_is_safe_no_action():
    assert rule_based_strategy(None)["action_type"] == "no_action"
    assert rule_based_strategy("garbage")["action_type"] == "no_action"
    assert rule_based_strategy("")["action_type"] == "no_action"


def test_result_always_in_vocabulary_and_well_formed():
    for affect in ("confused", "frustrated", "bored", "engaged", None, 123, "x"):
        strat = rule_based_strategy(affect)
        assert strat["action_type"] in ACTION_TYPES
        assert strat["urgency"] in URGENCIES
        assert isinstance(strat["reason"], str) and strat["reason"]


def test_profile_arg_is_optional_and_ignored_safely():
    # Signature parity with the LLM path — passing a profile must not change the baseline.
    assert rule_based_strategy("bored", profile={"skill_level": "advanced"})["action_type"] == "skip_ahead"
