"""Content coordinates resolved by `content_context_service.build` (migration 021).

`build` existed to ground the strategist/adapter prompts in the section the learner is on. It
now also returns the ids of that section's place in the course, because the research-event
envelope stamps them and this is the one lookup per section that already pays for the join —
resolving the course anywhere else would mean a second query on the 30s hot path.

The prompt-shaping keys (`topic`, `lesson`, `body`, `difficulty`) are covered elsewhere; these
tests cover only the coordinates and the degradation contract.
"""

import uuid

import pytest

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.services import content_context_service

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_cache():
    # The context cache is process-wide and never invalidated (see the module docstring), so a
    # test that seeded a section id must not leak its context into the next one.
    content_context_service._reset_cache()
    yield
    content_context_service._reset_cache()


async def _seed_section(db):
    course = Course(title="Coordinates Course", is_published=True)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="Type Systems", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    section = Section(title="Generics", sort_order=0, lesson_id=lesson.id)
    db.add(section)
    await db.flush()
    db.add(ContentBlock(
        block_type="text", content={"text": "A generic type is..."},
        sort_order=0, section_id=section.id,
    ))
    await db.flush()
    return course, module, lesson, section


async def test_build_returns_the_full_coordinate_chain(db):
    course, module, lesson, section = await _seed_section(db)

    context = await content_context_service.build(section.id, db)

    assert context["section_id"] == str(section.id)
    assert context["lesson_id"] == str(lesson.id)
    assert context["module_id"] == str(module.id)
    assert context["course_id"] == str(course.id)


async def test_build_still_grounds_the_prompt(db):
    """The coordinates are additive: adding them must not disturb what the prompt reads."""
    _, _, _, section = await _seed_section(db)

    context = await content_context_service.build(section.id, db)

    assert context["topic"] == "Generics"
    assert context["lesson"] == "Type Systems"
    assert "generic type" in context["body"]


async def test_unknown_section_yields_no_coordinates(db):
    """An unknown section returns {} rather than a coordinate-shaped dict of Nones, so the
    caller stamps nothing and the event is honestly uncoordinated."""
    assert await content_context_service.build(uuid.uuid4(), db) == {}


async def test_missing_section_id_yields_no_coordinates(db):
    """The browser omits `section_id` on cycles outside a lesson. That must not raise, and must
    not invent a location."""
    assert await content_context_service.build(None, db) == {}


async def test_coordinates_survive_the_cache(db):
    """The second call is served from the process cache; it must carry the coordinates too,
    or events would be located only on the first cycle of each section."""
    course, _, _, section = await _seed_section(db)

    first = await content_context_service.build(section.id, db)
    second = await content_context_service.build(section.id, db)

    assert first == second
    assert second["course_id"] == str(course.id)


async def test_build_accepts_a_string_section_id(db):
    """The id arrives as a STRING everywhere it matters, and never did in a test.

    `ws.py` passes `data.get("section_id")` straight off the WebSocket wire, and the dev harness
    passes it out of a JSON body. `Section.id` is `postgresql.UUID(as_uuid=True)`, which accepts a
    string on Postgres and raises `'str' object has no attribute 'hex'` on any dialect storing it
    as CHAR(32) -- including the test database. `build` catches everything and returns `{}`, so the
    whole grounding path degraded to "unknown topic" with no coordinates, silently, and every
    existing test passed a UUID object and never saw it.
    """
    course, module, lesson, section = await _seed_section(db)

    context = await content_context_service.build(str(section.id), db)

    assert context["topic"] == "Generics"
    assert context["lesson"] == "Type Systems"
    assert context["course_id"] == str(course.id)
    assert "A generic type is..." in context["body"]


async def test_build_degrades_on_a_malformed_section_id(db):
    assert await content_context_service.build("not-a-uuid", db) == {}
