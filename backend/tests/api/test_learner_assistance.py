"""Tests for the learner's own help history.

`assistance_service.for_learner` carries the docstring "The read behind a learner-facing hint
history" and had no route — `app/api/routes/learners.py` was an empty router mounted at
`/api/v1/learners`. Every hint the platform showed was recorded and none of it was visible to the
person it was shown to.

The privacy property is the one worth pinning hardest: `architecture.md` lists "showing detected
affect state to learners" as an anti-pattern, so the response must carry the help itself and not
the inference that produced it.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.assistance_event import AssistanceEvent

pytestmark = pytest.mark.asyncio

URL = "/api/v1/learners/me/assistance"


async def _record(db, *, learner_id, course_id=None, section_id=None, **kw):
    event = AssistanceEvent(
        adaptation_id=str(uuid.uuid4()),
        learner_id=learner_id,
        course_id=course_id,
        section_id=section_id,
        action_type=kw.get("action_type", "show_hint"),
        hint_text=kw.get("hint_text", "Try connecting it to something you know."),
        affect_state=kw.get("affect_state", "confused"),
        affect_confidence=kw.get("affect_confidence", 0.91),
        interaction=kw.get("interaction"),
        outcome_is_correct=kw.get("outcome_is_correct"),
    )
    # Explicit when the caller cares about order: `created_at` defaults to now() and two rows
    # written in the same test land in the same tick, which makes a desc sort a coin toss. The
    # real loop writes these tens of seconds apart.
    if kw.get("created_at") is not None:
        event.created_at = kw["created_at"]
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def test_returns_the_learners_own_help(client, auth_headers, db, test_user):
    await _record(db, learner_id=test_user.id, hint_text="Here is another way in.")

    resp = await client.get(URL, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["hintText"] == "Here is another way in."
    assert body[0]["actionType"] == "show_hint"


async def test_never_reveals_the_affect_inference(client, auth_headers, db, test_user):
    """The architecture's stated anti-pattern.

    Telling a learner the system decided they looked confused changes the behaviour the system
    exists to measure, and that data belongs on the designer dashboard.
    """
    await _record(db, learner_id=test_user.id, affect_state="confused", affect_confidence=0.93)

    body = (await client.get(URL, headers=auth_headers)).json()

    assert "affectState" not in body[0]
    assert "affectConfidence" not in body[0]
    assert "gateReason" not in body[0]
    assert "0.93" not in str(body[0])


async def test_only_ever_returns_your_own(client, auth_headers, db, test_user, test_designer):
    """There is no path parameter to point at anyone else, and the filter is on the caller."""
    await _record(db, learner_id=test_designer.id, hint_text="Someone else's hint.")
    await _record(db, learner_id=test_user.id, hint_text="Mine.")

    body = (await client.get(URL, headers=auth_headers)).json()

    assert [item["hintText"] for item in body] == ["Mine."]


async def test_newest_first(client, auth_headers, db, test_user):
    now = datetime.now(timezone.utc)
    await _record(
        db, learner_id=test_user.id, hint_text="First", created_at=now - timedelta(minutes=5)
    )
    await _record(db, learner_id=test_user.id, hint_text="Second", created_at=now)

    body = (await client.get(URL, headers=auth_headers)).json()

    assert [item["hintText"] for item in body] == ["Second", "First"]


async def test_distinguishes_no_next_attempt_from_a_wrong_one(
    client, auth_headers, db, test_user
):
    """None and False are different facts and collapsing them would invent evidence."""
    await _record(db, learner_id=test_user.id, hint_text="Unanswered", outcome_is_correct=None)
    await _record(db, learner_id=test_user.id, hint_text="Got it wrong", outcome_is_correct=False)

    body = (await client.get(URL, headers=auth_headers)).json()
    by_text = {item["hintText"]: item["outcomeIsCorrect"] for item in body}

    assert by_text["Unanswered"] is None
    assert by_text["Got it wrong"] is False


async def test_can_be_scoped_to_one_course(client, auth_headers, db, test_user, test_course):
    await _record(db, learner_id=test_user.id, course_id=test_course.id, hint_text="In course")
    await _record(db, learner_id=test_user.id, hint_text="Elsewhere")

    body = (
        await client.get(f"{URL}?course_id={test_course.id}", headers=auth_headers)
    ).json()

    assert [item["hintText"] for item in body] == ["In course"]


async def test_designers_have_no_help_history_here(client, designer_headers):
    resp = await client.get(URL, headers=designer_headers)
    assert resp.status_code == 403


async def test_requires_authentication(client):
    resp = await client.get(URL)
    assert resp.status_code == 401
