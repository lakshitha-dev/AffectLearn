"""Tests for the rule-based agent fallbacks (Story 5.1 AC1, Story 5.2 AC1)."""

from app.agents.fallbacks import (
    ACTION_TYPES,
    GENERATIVE_ACTIONS,
    SELECTIVE_ACTIONS,
    URGENCIES,
    rule_based_content,
    rule_based_strategy,
)


def test_each_affect_opens_at_the_first_rung_of_its_ladder():
    """The default rung is 0, so an unescalated call is the ladder's FIRST action.

    Two of these changed when the single-action map became a ladder (Sep 2026), and both changes
    are deliberate:
      * `bored` opens at `increase_difficulty`, not `skip_ahead`. Flow theory places boredom at
        challenge BELOW skill, so raising challenge comes before conceding the material.
      * `frustrated` opens at `show_encouragement`, not `simplify`. Re-explaining is a heavier
        intervention than a word of encouragement and should not be the opening move.
    """
    assert rule_based_strategy("confused")["action_type"] == "show_hint"
    assert rule_based_strategy("confused")["urgency"] == "medium"
    assert rule_based_strategy("frustrated")["action_type"] == "show_encouragement"
    assert rule_based_strategy("frustrated")["urgency"] == "medium"
    assert rule_based_strategy("bored")["action_type"] == "increase_difficulty"
    assert rule_based_strategy("bored")["urgency"] == "low"
    assert rule_based_strategy("engaged")["action_type"] == "no_action"
    assert rule_based_strategy("engaged")["urgency"] == "low"


def test_a_repeat_escalates_instead_of_repeating():
    """The behaviour the single-action map could not produce: a learner confused three times in
    one section used to receive the identical hint three times."""
    assert rule_based_strategy("confused", rung=1)["action_type"] == "show_breakdown"
    assert rule_based_strategy("bored", rung=1)["action_type"] == "skip_ahead"
    assert rule_based_strategy("frustrated", rung=2)["action_type"] == "suggest_break"


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
    assert (
        rule_based_strategy("bored", profile={"skill_level": "advanced"})["action_type"]
        == "increase_difficulty"
    )


# ── Story 5.2: rule_based_content (Content Adapter fallback) ────────────────────


def test_action_partition_covers_vocabulary_exactly():
    # Every action is generative XOR selective XOR no_action — single source of truth.
    assert set(GENERATIVE_ACTIONS) | set(SELECTIVE_ACTIONS) | {"no_action"} == set(ACTION_TYPES)
    assert not (set(GENERATIVE_ACTIONS) & set(SELECTIVE_ACTIONS))
    assert "no_action" not in GENERATIVE_ACTIONS
    assert "no_action" not in SELECTIVE_ACTIONS


def test_generative_actions_return_warm_text_and_matching_variant():
    for action in GENERATIVE_ACTIONS:
        content = rule_based_content(action)
        assert content["variant"] == action
        assert isinstance(content["text"], str) and content["text"].strip()
        assert content["metadata"]["action_type"] == action
        # Warm/conversational copy must NOT leak the clinical mechanism wording.
        assert "difficulty reduced" not in content["text"].lower()


def test_selective_actions_return_selection_descriptor():
    expected_select = {"skip_ahead": "next_section", "increase_difficulty": "challenge_exercise"}
    for action in SELECTIVE_ACTIONS:
        content = rule_based_content(action)
        assert content["variant"] == action
        assert content["metadata"]["select"] == expected_select[action]
        assert content["metadata"]["action_type"] == action


def test_no_action_and_unknown_are_safe_empty():
    for junk in ("no_action", "teleport_learner", "", None, 123, ["x"]):
        content = rule_based_content(junk)
        assert content["variant"] == "no_action"
        assert content["text"] == ""
        assert content["metadata"]["action_type"] == "no_action"


def test_content_always_well_formed_and_never_raises():
    for action in (*ACTION_TYPES, "garbage", None, 42):
        content = rule_based_content(action)
        assert set(content) == {"text", "variant", "metadata"}
        assert isinstance(content["text"], str)
        assert isinstance(content["variant"], str)
        assert isinstance(content["metadata"], dict)


def test_context_arg_is_optional_and_ignored_safely():
    # Signature parity with the LLM path — passing context must not change the baseline copy.
    base = rule_based_content("show_hint")
    with_ctx = rule_based_content("show_hint", context={"topic": "subnetting", "difficulty": "hard"})
    assert base == with_ctx
