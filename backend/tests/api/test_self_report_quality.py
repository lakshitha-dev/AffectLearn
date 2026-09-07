"""Tests for self-report label quality (Story 8.6 / FR48).

The self-report widget is the pilot's ground-truth label source, every prompt and response has
been recorded since Story 6.2, and nothing read them back. A participant who answers "engaged" to
every prompt produces a dataset that looks clean and measures nothing; the distribution is the
only place that shows.
"""

import pytest

from app.models.research_event import ResearchEvent

pytestmark = pytest.mark.asyncio

URL = "/api/v1/admin/research/self-report-quality"


async def _report(db, *, session_id, affect=None, skipped=False, seq=1, ts=1_000):
    db.add(
        ResearchEvent(
            event_type="self_report",
            learner_id="u1",
            session_id=session_id,
            cycle_number=0,
            timestamp=ts,
            sequence_number=seq,
            phase="phase_a",
            group="control",
            payload={"affect": affect, "skipped": skipped, "prompt_index": seq},
        )
    )
    await db.commit()


async def _varied_session(db, session_id, affects, start_seq=1):
    for i, affect in enumerate(affects):
        await _report(db, session_id=session_id, affect=affect, seq=start_seq + i, ts=1_000 + i)


async def test_reports_the_overall_distribution(client, admin_headers, db):
    await _varied_session(db, "s1", ["engaged", "confused", "engaged", "bored"])

    body = (await client.get(URL, headers=admin_headers)).json()

    assert body["distribution"] == {"engaged": 2, "confused": 1, "bored": 1}
    assert body["answered"] == 4
    assert body["totalPrompts"] == 4


async def test_counts_skips_against_the_answer_rate(client, admin_headers, db):
    await _report(db, session_id="s1", affect="engaged", seq=1)
    await _report(db, session_id="s1", skipped=True, seq=2)

    body = (await client.get(URL, headers=admin_headers)).json()

    assert body["skipped"] == 1
    assert body["skipRate"] == 0.5
    # A skipped prompt contributes no label.
    assert body["distribution"] == {"engaged": 1}


async def test_flags_a_session_whose_labels_never_vary(client, admin_headers, db):
    """The failure mode this exists to catch: clicking the first button every time."""
    await _varied_session(db, "s1", ["engaged"] * 6)

    body = (await client.get(URL, headers=admin_headers)).json()
    session = next(s for s in body["sessions"] if s["sessionId"] == "s1")

    assert session["lowVariance"] is True
    assert session["dominantAffect"] == "engaged"
    assert session["dominantShare"] == 1.0
    assert body["flaggedSessions"] == 1


async def test_does_not_flag_a_session_with_a_real_spread(client, admin_headers, db):
    await _varied_session(
        db, "s1", ["engaged", "confused", "engaged", "bored", "confused", "engaged"]
    )

    body = (await client.get(URL, headers=admin_headers)).json()
    session = next(s for s in body["sessions"] if s["sessionId"] == "s1")

    assert session["lowVariance"] is False
    assert session["distinctLabels"] == 3


async def test_does_not_flag_a_short_session(client, admin_headers, db):
    """Three identical answers out of three is a short session, not evidence of fatigue.

    Flagging it would put honest participants in front of a researcher deciding what to exclude.
    """
    await _varied_session(db, "s1", ["engaged"] * 3)

    body = (await client.get(URL, headers=admin_headers)).json()
    session = next(s for s in body["sessions"] if s["sessionId"] == "s1")

    assert session["lowVariance"] is False


async def test_publishes_the_criteria_behind_the_flag(client, admin_headers, db):
    """A flag whose threshold is invisible cannot be argued with."""
    body = (await client.get(URL, headers=admin_headers)).json()

    assert body["fatigueCriteria"]["minAnswers"] == 5
    assert body["fatigueCriteria"]["dominantShare"] == 0.9


async def test_flagged_sessions_sort_first(client, admin_headers, db):
    await _varied_session(db, "clean", ["engaged", "confused", "bored", "engaged", "confused"])
    await _varied_session(db, "suspect", ["engaged"] * 6, start_seq=10)

    body = (await client.get(URL, headers=admin_headers)).json()

    # Worst first: the sessions a researcher needs to look at.
    assert body["sessions"][0]["sessionId"] == "suspect"


async def test_empty_dataset_does_not_divide_by_zero(client, admin_headers):
    body = (await client.get(URL, headers=admin_headers)).json()

    assert body["totalPrompts"] == 0
    assert body["skipRate"] is None
    assert body["sessions"] == []


async def test_requires_admin(client, designer_headers):
    resp = await client.get(URL, headers=designer_headers)
    assert resp.status_code == 403
