"""Analytics aggregation service (Story 7.1) — the read-only data engine for Epic 7.

Mirrors the read-only discipline of `research_export_service.py`: filtered async `select`s,
plain-dict returns, thin functions taking `db`. NO writes, NO migration, NO new tables, NO
Redis, NO agent loop — pure live aggregation over existing tables. The three designer/admin
endpoints (overview / affect-heatmap / section-detail) all delegate here so confidence and
insufficient-data semantics live in ONE place (AC4).

Data-sourcing reality (drives the whole design):

* Per-section affect is sourced ONLY from `section_progress.affect_states` — a JSON list of
  affect labels observed in-section, client-supplied on completion (Story 4.6). It is the
  only affect signal reliably keyed to a `section_id`. This is the basis for the heatmap and
  the per-section affect-distribution bars.
* `research_events` affect/adaptation rows are keyed by `session_id` + `cycle_number`, NOT by
  `section_id`. They feed course-level rollups, the section temporal distribution, and the
  adaptation key-insights ONLY on a best-effort basis (no first-class section linkage). The
  section temporal/insight aggregations are therefore documented as best-effort and degrade
  gracefully (empty/flat) when no cycle-level data exists.
* Affect vocabulary is fixed: engaged | confused | bored | frustrated (see
  `app.agents.affect_mapping.AFFECT_CLASS_ORDER`). The current facial stand-in can only emit
  engaged/bored, so confused/frustrated shares may be sparse — every aggregation handles all
  four labels and never assumes all four are present.

Affect-distribution basis (AC2): per-section percentages are the share of LEARNERS who
showed each affect state (a learner counts toward a state if it appears at least once in
their in-section `affect_states`), NOT per-observation shares — one chatty learner cannot
skew a section. `sample_count` is the number of distinct learners observed for the section.

Engagement-score formula: `average_engagement_score` is the SHARE of observed LEARNERS
(course-wide) who showed `engaged` at least once, scaled to 0-100 — the same per-learner
basis as the heatmap. Chosen for transparency so the 7.2 "Avg Engagement" stat card label is
literally true. Documented here as the single source of the definition.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress

# ── Single-source-of-truth constants (AC4) ──────────────────────────────────────
# Minimum number of in-section affect observations required before an aggregate is
# considered reliable. Below this a payload is flagged `insufficient_data` and excluded
# from hotspot classification. Set to 5 for the pilot's small sample sizes — a single
# documented module constant, trivially tunable as N grows (see story Open Question 1).
INSUFFICIENT_DATA_THRESHOLD = 5

# A section is a "confusion hotspot" when its confused share is at/above this percentage
# AND it has sufficient samples. A 1-learner confused section must never count.
CONFUSION_HOTSPOT_THRESHOLD = 30.0

# Confidence band boundaries (observation counts). `low` below the insufficient threshold.
_MEDIUM_CONFIDENCE_THRESHOLD = 15

# Affect labels, ordered as the designer dashboard renders them (engaged first).
AFFECT_STATES: tuple[str, ...] = ("engaged", "confused", "bored", "frustrated")

# Number of temporal bins for the section confusion-over-time distribution (best-effort).
TEMPORAL_BIN_COUNT = 5

# research_event types we read (best-effort) for course rollups and section insights.
_AFFECT_EVENT_TYPES = (
    "facial_affect_detected",
    "behavioral_affect_detected",
    "multimodal_affect_detected",
)
_ADAPTATION_EVENT_TYPES = ("adaptation_triggered", "adaptation_delivered")


def _confidence(sample_count: int) -> dict[str, Any]:
    """Map an observation count to a {confidence, insufficient_data} indicator.

    ONE place defines the bands so all three endpoints (and 7.2/7.3/7.4) agree:
      * sample_count < INSUFFICIENT_DATA_THRESHOLD     -> low,    insufficient_data=True
      * < _MEDIUM_CONFIDENCE_THRESHOLD                 -> medium, insufficient_data=False
      * otherwise                                      -> high,   insufficient_data=False
    """
    insufficient = sample_count < INSUFFICIENT_DATA_THRESHOLD
    if insufficient:
        band = "low"
    elif sample_count < _MEDIUM_CONFIDENCE_THRESHOLD:
        band = "medium"
    else:
        band = "high"
    return {"confidence": band, "insufficient_data": insufficient}


def _empty_percentages() -> dict[str, float]:
    return {state: 0.0 for state in AFFECT_STATES}


def _percentages_from_counts(counts: dict[str, int], total: int) -> dict[str, float]:
    """Convert per-affect counts to 0-100 percentages over `total` observations."""
    if total <= 0:
        return _empty_percentages()
    return {
        state: round((counts.get(state, 0) * 100.0) / total, 2) for state in AFFECT_STATES
    }


async def affect_distribution_for_sections(
    db: AsyncSession, section_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Per-section affect distribution from `section_progress.affect_states`, per LEARNER.

    AC2 basis: percentages are the share of LEARNERS who showed each affect state, NOT the
    share of raw observations — so one chatty learner who logged a label many times cannot
    skew a section. A learner counts toward an affect state if that state appears at least
    once in their in-section `affect_states` list. Percentages = learners-with-state /
    learners-observed (so they can sum to >100 when learners show multiple states).
    `sample_count` is the number of DISTINCT learners observed for the section.

    Tolerates `affect_states` being None/[] (a learner with no labels is not "observed").
    Shared core used by both the heatmap and section detail.

    Returns {section_id: {counts, percentages, sample_count}} for every requested id
    (sections with no progress still get a zeroed entry). `counts` is per-affect learner
    counts; `sample_count` is the distinct-learner-observed count.
    """
    result: dict[uuid.UUID, dict[str, Any]] = {
        sid: {"counts": Counter(), "percentages": _empty_percentages(), "sample_count": 0}
        for sid in section_ids
    }
    if not section_ids:
        return result

    stmt = select(
        SectionProgress.section_id,
        SectionProgress.user_id,
        SectionProgress.affect_states,
    ).where(SectionProgress.section_id.in_(section_ids))
    rows = (await db.execute(stmt)).all()

    # Per section: learner counts per affect state + set of observed learners.
    counters: dict[uuid.UUID, Counter] = defaultdict(Counter)
    observed_learners: dict[uuid.UUID, set] = defaultdict(set)
    for section_id, user_id, affect_states in rows:
        states = {label for label in (affect_states or []) if label in AFFECT_STATES}
        if not states:
            continue
        observed_learners[section_id].add(user_id)
        for label in states:
            counters[section_id][label] += 1

    for section_id in section_ids:
        learner_count = len(observed_learners[section_id])
        counts = counters[section_id]
        result[section_id] = {
            "counts": counts,
            "percentages": _percentages_from_counts(counts, learner_count),
            "sample_count": learner_count,
        }
    return result


async def _ordered_sections(db: AsyncSession, course_id: uuid.UUID) -> list[Section]:
    """Sections of a course ordered by (module, lesson, section) sort_order."""
    stmt = (
        select(Section)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.course_id == course_id)
        .order_by(Module.sort_order, Lesson.sort_order, Section.sort_order)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _require_course(db: AsyncSession, course_id: uuid.UUID) -> Course:
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Course not found"}},
        )
    return course


async def _require_section(db: AsyncSession, section_id: uuid.UUID) -> Section:
    section = (
        await db.execute(select(Section).where(Section.id == section_id))
    ).scalar_one_or_none()
    if section is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Section not found"}},
        )
    return section


async def course_overview(db: AsyncSession, course_id: uuid.UUID) -> dict[str, Any]:
    """Aggregate course-level overview stats (AC1).

    * total_learners: distinct enrolled learners in the course.
    * completion_rate: percentage of enrolled learners who completed ALL sections (0-100).
      A course with zero sections has completion_rate 0.
    * average_engagement_score: share of observed LEARNERS (course-wide) who showed `engaged`
      at least once, 0-100 — the same per-learner basis as the heatmap (see module docstring).
    * confusion_hotspot_count: sections whose confused share >= CONFUSION_HOTSPOT_THRESHOLD
      AND whose sample_count >= INSUFFICIENT_DATA_THRESHOLD (thin sections never count).
    * sample_count / confidence / insufficient_data: distinct learners observed course-wide
      + the shared band.

    Raises 404 if the course does not exist. Tolerant of empty courses/enrollments.
    """
    await _require_course(db, course_id)

    sections = await _ordered_sections(db, course_id)
    section_ids = [s.id for s in sections]
    total_sections = len(section_ids)

    # Enrolled learners.
    total_learners = (
        await db.execute(
            select(func.count(func.distinct(Enrollment.user_id))).where(
                Enrollment.course_id == course_id
            )
        )
    ).scalar_one() or 0

    # Completion: learners who completed all sections / enrolled learners.
    completion_rate = 0.0
    if total_sections > 0 and total_learners > 0:
        completed_counts_stmt = (
            select(SectionProgress.user_id, func.count(SectionProgress.section_id))
            .where(SectionProgress.section_id.in_(section_ids))
            .group_by(SectionProgress.user_id)
        )
        completed_rows = (await db.execute(completed_counts_stmt)).all()
        fully_completed = sum(
            1 for _user_id, n in completed_rows if n >= total_sections
        )
        completion_rate = round((fully_completed * 100.0) / total_learners, 2)

    # Per-section hotspot classification (per-learner basis, thin sections excluded).
    distributions = await affect_distribution_for_sections(db, section_ids)
    confusion_hotspot_count = 0
    for dist in distributions.values():
        sample_count = dist["sample_count"]
        confused_pct = dist["percentages"].get("confused", 0.0)
        if (
            sample_count >= INSUFFICIENT_DATA_THRESHOLD
            and confused_pct >= CONFUSION_HOTSPOT_THRESHOLD
        ):
            confusion_hotspot_count += 1

    # Course-wide engagement on a per-distinct-learner basis: a learner counts as "engaged"
    # if any of their in-section affect_states (across the course) contains `engaged`.
    # sample_count is the number of distinct learners observed (with any affect label).
    learners_observed: set = set()
    learners_engaged: set = set()
    if section_ids:
        affect_rows_stmt = select(
            SectionProgress.user_id, SectionProgress.affect_states
        ).where(SectionProgress.section_id.in_(section_ids))
        for user_id, affect_states in (await db.execute(affect_rows_stmt)).all():
            states = {label for label in (affect_states or []) if label in AFFECT_STATES}
            if not states:
                continue
            learners_observed.add(user_id)
            if "engaged" in states:
                learners_engaged.add(user_id)

    observed_count = len(learners_observed)
    average_engagement_score = (
        round((len(learners_engaged) * 100.0) / observed_count, 2)
        if observed_count > 0
        else 0.0
    )

    indicator = _confidence(observed_count)
    return {
        "course_id": str(course_id),
        "total_learners": int(total_learners),
        "completion_rate": completion_rate,
        "average_engagement_score": average_engagement_score,
        "confusion_hotspot_count": confusion_hotspot_count,
        "sample_count": observed_count,
        **indicator,
    }


async def affect_heatmap(db: AsyncSession, course_id: uuid.UUID) -> dict[str, Any]:
    """Per-section affect distribution rows in course order (AC2).

    Each row carries the four percentages (summing to ~100 with >=1 observation, zeros
    otherwise), sample_count, confidence, and insufficient_data. Empty course → empty list.
    Raises 404 if the course does not exist.
    """
    await _require_course(db, course_id)

    sections = await _ordered_sections(db, course_id)
    section_ids = [s.id for s in sections]
    distributions = await affect_distribution_for_sections(db, section_ids)

    rows: list[dict[str, Any]] = []
    for section in sections:
        dist = distributions[section.id]
        pct = dist["percentages"]
        sample_count = dist["sample_count"]
        indicator = _confidence(sample_count)
        rows.append(
            {
                "section_id": str(section.id),
                "section_title": section.title,
                "engaged_pct": pct["engaged"],
                "confused_pct": pct["confused"],
                "bored_pct": pct["bored"],
                "frustrated_pct": pct["frustrated"],
                "sample_count": sample_count,
                **indicator,
            }
        )

    return {"course_id": str(course_id), "sections": rows}


def _temporal_distribution(affect_rows: list[tuple[int, Any]]) -> list[dict[str, Any]]:
    """Best-effort confusion-over-time bins from cycle-ordered affect events.

    `affect_rows` is (cycle_number, payload) for affect events of the section's learners,
    ordered by (session_id, cycle_number, timestamp). We split them into TEMPORAL_BIN_COUNT
    equal bins and report the `confused` share per bin. Because session/cycle→section linkage
    is approximate (affect events are NOT section-keyed — see module docstring), this is
    documented as best-effort and degrades to an all-zero distribution when no cycle-level
    data exists. NOTE: rows from different sessions are concatenated in session_id order, so
    the "time" axis is session-grouped cycle order, not a single global chronological timeline.
    """
    bins = [{"bin_index": i, "confused_pct": 0.0} for i in range(TEMPORAL_BIN_COUNT)]
    if not affect_rows:
        return bins

    n = len(affect_rows)
    for idx, (_cycle, payload) in enumerate(affect_rows):
        bin_index = min(TEMPORAL_BIN_COUNT - 1, (idx * TEMPORAL_BIN_COUNT) // n)
        bins[bin_index].setdefault("_total", 0)
        bins[bin_index].setdefault("_confused", 0)
        bins[bin_index]["_total"] += 1
        if isinstance(payload, dict) and payload.get("affect_state") == "confused":
            bins[bin_index]["_confused"] += 1

    for b in bins:
        total = b.pop("_total", 0)
        confused = b.pop("_confused", 0)
        b["confused_pct"] = round((confused * 100.0) / total, 2) if total else 0.0
    return bins


async def _section_learner_ids(db: AsyncSession, section_id: uuid.UUID) -> list[str]:
    """Learner ids (as str) who have a `section_progress` row for this section.

    Used to SCOPE `research_events` (which are learner/session/cycle-keyed, NOT section-keyed)
    to the learners who actually touched the section, so the temporal distribution and key
    insights never bleed events from other sections/courses. `ResearchEvent.learner_id` is a
    String(64), so the UUIDs are cast to str for the `IN` comparison.
    """
    stmt = (
        select(SectionProgress.user_id)
        .where(SectionProgress.section_id == section_id)
        .distinct()
    )
    return [str(uid) for uid in (await db.execute(stmt)).scalars().all()]


async def section_detail(db: AsyncSession, section_id: uuid.UUID) -> dict[str, Any]:
    """Full section detail aggregation (AC3).

    Returns affect distribution (from section_progress, same per-learner basis as the heatmap
    row), a best-effort temporal confusion distribution, best-effort key insights, and the
    section content with paragraph-level annotation. All `research_events`-derived parts are
    best-effort because those events are session/cycle-keyed, not section-keyed (see module
    docstring) — they are SCOPED to the learners who have section_progress for this section so
    they never bleed activity from other sections/courses. Raises 404 if the section does not
    exist.

    keyInsights heuristics (documented):
      * most_triggered_adaptation_type: mode of `action`/`strategy`/`adaptation_type` in the
        adaptation event payloads of this section's learners (best-effort; null if none).
      * average_confusion_duration_seconds: mean of section_progress.time_spent_seconds
        weighted by each row's confused share — a heuristic estimate of time-in-confusion.
    """
    section = await _require_section(db, section_id)

    distributions = await affect_distribution_for_sections(db, [section_id])
    dist = distributions[section_id]
    pct = dist["percentages"]
    sample_count = dist["sample_count"]
    indicator = _confidence(sample_count)

    affect_distribution = {
        "engaged_pct": pct["engaged"],
        "confused_pct": pct["confused"],
        "bored_pct": pct["bored"],
        "frustrated_pct": pct["frustrated"],
    }

    # Scope research_events to this section's learners AND to this section. Events carry the
    # section they happened in (migration 021); scoping by learner alone counted each learner's
    # readings from every OTHER section they visited too, so one section's chart described the
    # learners' whole course. Events recorded before the column existed have no section and keep
    # the learner-only scoping, which is the best that can be said about them.
    learner_ids = await _section_learner_ids(db, section_id)

    # Best-effort temporal distribution from this section's learners' affect events. If no
    # learner touched the section, degrade gracefully to a flat (all-zero) distribution.
    if learner_ids:
        affect_stmt = (
            select(ResearchEvent.cycle_number, ResearchEvent.payload)
            .where(
                ResearchEvent.event_type.in_(_AFFECT_EVENT_TYPES),
                ResearchEvent.learner_id.in_(learner_ids),
                _in_section(section_id),
            )
            .order_by(
                ResearchEvent.session_id.asc(),
                ResearchEvent.cycle_number.asc(),
                ResearchEvent.timestamp.asc(),
            )
        )
        affect_rows = [(c, p) for c, p in (await db.execute(affect_stmt)).all()]
    else:
        affect_rows = []
    temporal_distribution = _temporal_distribution(affect_rows)

    key_insights = await _section_insights(db, section_id, learner_ids)

    content = await _content_annotations(db, section_id, affect_distribution, sample_count)

    return {
        "section_id": str(section_id),
        "section_title": section.title,
        "affect_distribution": affect_distribution,
        "temporal_distribution": temporal_distribution,
        "key_insights": key_insights,
        "content": content,
        "sample_count": sample_count,
        **indicator,
    }


def _in_section(section_id: Any):
    """Events that happened in this section, or that predate section tagging (no section)."""
    return or_(
        ResearchEvent.section_id == str(section_id),
        ResearchEvent.section_id.is_(None),
    )


async def _section_insights(
    db: AsyncSession, section_id: uuid.UUID, learner_ids: list[str]
) -> dict[str, Any]:
    """Best-effort key insights (see `section_detail` docstring for heuristics).

    Scoped to `learner_ids` (the section's learners) so adaptation activity from other
    sections/courses never leaks in. With no learners, most_triggered_adaptation_type is null.
    """
    # Most-triggered adaptation type — only the section's learners' adaptation events.
    most_triggered_adaptation_type = None
    if learner_ids:
        adapt_stmt = select(ResearchEvent.payload).where(
            ResearchEvent.event_type.in_(_ADAPTATION_EVENT_TYPES),
            ResearchEvent.learner_id.in_(learner_ids),
            _in_section(section_id),
        )
        adapt_payloads = (await db.execute(adapt_stmt)).scalars().all()
        adaptation_counter: Counter = Counter()
        for payload in adapt_payloads:
            if not isinstance(payload, dict):
                continue
            action = (
                payload.get("action")
                or payload.get("action_type")
                or payload.get("strategy")
                or payload.get("adaptation_type")
            )
            if action:
                adaptation_counter[action] += 1
        most_triggered = adaptation_counter.most_common(1)
        most_triggered_adaptation_type = most_triggered[0][0] if most_triggered else None

    # Per-section progress rows for the confusion-duration heuristic.
    prog_stmt = select(
        SectionProgress.time_spent_seconds, SectionProgress.affect_states
    ).where(SectionProgress.section_id == section_id)
    prog_rows = (await db.execute(prog_stmt)).all()

    weighted_total = 0.0
    weight_sum = 0.0
    for time_spent, affect_states in prog_rows:
        labels = [s for s in (affect_states or []) if s in AFFECT_STATES]
        if labels and time_spent:
            confused_share = labels.count("confused") / len(labels)
            weighted_total += time_spent * confused_share
            weight_sum += confused_share

    average_confusion_duration_seconds = (
        round(weighted_total / weight_sum, 2) if weight_sum > 0 else None
    )

    return {
        "most_triggered_adaptation_type": most_triggered_adaptation_type,
        "average_confusion_duration_seconds": average_confusion_duration_seconds,
    }


def _block_text(content: Any) -> str | None:
    """Extract display text from a content block's JSON, if present."""
    if isinstance(content, dict):
        for key in ("text", "body", "markdown", "content", "caption"):
            value = content.get(key)
            if isinstance(value, str):
                return value
    if isinstance(content, str):
        return content
    return None


async def _content_annotations(
    db: AsyncSession,
    section_id: uuid.UUID,
    affect_distribution: dict[str, float],
    sample_count: int,
) -> list[dict[str, Any]]:
    """Section content blocks (ordered) with section-level affect annotation (AC3 / Task 3).

    Paragraph-precise affect is NOT logged today (affect is session/cycle-keyed, the facial
    stand-in only emits engaged/bored). We therefore attach the SECTION-level distribution as
    each block's annotation where it is derivable (sample_count > 0), else null — we never
    fabricate per-paragraph numbers. The 7.4 hotspot highlighting degrades gracefully to
    section level; paragraph-precise affect is a documented future enhancement.
    """
    stmt = (
        select(ContentBlock)
        .where(ContentBlock.section_id == section_id)
        .order_by(ContentBlock.sort_order)
    )
    blocks = list((await db.execute(stmt)).scalars().all())

    annotation = affect_distribution if sample_count > 0 else None
    return [
        {
            "block_id": str(block.id),
            "paragraph_index": idx,
            "block_type": block.block_type.value
            if hasattr(block.block_type, "value")
            else str(block.block_type),
            "text": _block_text(block.content),
            "affect_distribution": annotation,
        }
        for idx, block in enumerate(blocks)
    ]
