"""`n_words`: the performance channel's pace denominator, and the designer view's.

The live context never carried a word count, so the performance channel's slow-pace term was zero
on every live window. The count must also cover the WHOLE section: the prompt body stops at
`_BODY_CHAR_BUDGET`, and counting that would make every long section look like slow reading.
"""

import pytest

from app.models.course import BlockType, ContentBlock, Course, Lesson, Module, Section
from app.services import content_context_service, section_features


@pytest.fixture(autouse=True)
def _reset_cache():
    content_context_service._reset_cache()
    yield
    content_context_service._reset_cache()


async def _seed_section(db, text: str):
    course = Course(title="Word Count Course", is_published=True)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    section = Section(title="S", sort_order=0, lesson_id=lesson.id)
    db.add(section)
    await db.flush()
    db.add(ContentBlock(block_type="text", content={"text": text}, sort_order=0,
                        section_id=section.id))
    await db.flush()
    return section


async def test_the_context_carries_a_word_count(db):
    section = await _seed_section(db, "one two three four five")

    context = await content_context_service.build(section.id, db)

    assert context["n_words"] == 5


async def test_a_long_section_is_counted_in_full(db):
    """1,000 words is ~6,000 characters, three times the prompt budget."""
    section = await _seed_section(db, "word " * 1000)

    context = await content_context_service.build(section.id, db)

    assert context["n_words"] == 1000
    assert len(context["body"].split()) < 1000   # the prompt body is still truncated


class _Block:
    def __init__(self, block_type, content, sort_order=0):
        self.block_type, self.content, self.sort_order = block_type, content, sort_order


def test_the_designer_view_uses_the_same_count():
    blocks = [
        _Block(BlockType.text, {"text": "word " * 1000}, 0),
        _Block(BlockType.code, {"language": "python", "code": "x = 1"}, 1),
    ]

    shape = section_features.section_shape_from_blocks(blocks)

    assert shape["n_words"] == content_context_service.word_count(blocks)
    assert shape["n_words"] > 1000
