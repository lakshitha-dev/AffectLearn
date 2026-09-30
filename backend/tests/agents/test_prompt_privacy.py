"""Nothing that identifies the learner is sent to the language model.

The consent text tells participants that the adaptive version sends the section text and a
description of their estimated state and recent activity to an external model provider, and that
their name, email and account id are never sent. These tests hold the prompts to that sentence.
"""

from app.agents.nodes import content_adapter, pedagogical

LEARNER_ID = "9f0c3b52-1111-4a2b-9c3d-5e6f7a8b9c0d"
IDENTITY = ("Test", "Learner", "learner@test.com", LEARNER_ID)


def _profile():
    # A profile as the profiler stores it, plus identity fields a future change might add.
    return {
        "learner_id": LEARNER_ID, "first_name": "Test", "last_name": "Learner",
        "email_address": "learner@test.com", "skill_level": "beginner",
        "affect_history": ["bored", "bored"], "format_preferences": {"text": 1},
    }


def _context():
    return {"topic": "Agents", "lesson": "Tools", "difficulty": "easy",
            "body": "An agent calls tools.", "section_id": "sec-1"}


def test_strategist_prompt_carries_no_identity():
    prompt = pedagogical._build_human_prompt("bored", 0.9, _profile(), _context())
    assert not [value for value in IDENTITY if value in prompt]


def test_content_prompt_carries_no_identity():
    prompt = content_adapter._build_human_prompt("show_hint", _profile(), _context())
    assert not [value for value in IDENTITY if value in prompt]
