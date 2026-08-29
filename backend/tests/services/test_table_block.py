"""The `table` content block: authoring helper, and its rendering into the LLM prompt context.

Text blocks are emitted as plain `<p>` paragraphs with no markdown parsing, so a markdown table in
lesson copy would render as literal `|` characters. `table()` is the supported way to author
tabular material.

The prompt-context half matters as much as the rendering half: if `_block_text` ignored tables, the
model would be grounding hints on a section it can only partly see — a silent quality regression
rather than a visible failure.
"""

from __future__ import annotations

from app.db.course_content_helpers import table
from app.models.course import BlockType
from app.services import content_context_service as ccs


class _Block:
    def __init__(self, block_type, content, sort_order=0):
        self.block_type = block_type
        self.content = content
        self.sort_order = sort_order


def _as_block(built, sort_order=0):
    kind, content = built
    return _Block(kind, content, sort_order)


def test_helper_returns_table_block_type_and_shape():
    kind, content = table(["A", "B"], [["1", "2"]])
    assert kind is BlockType.table
    assert content == {"headers": ["A", "B"], "rows": [["1", "2"]]}


def test_helper_stringifies_non_string_cells():
    """Authors write ints and bools inline; the stored content must stay JSON-safe strings."""
    _, content = table(["N"], [[1], [True]])
    assert content["rows"] == [["1"], ["True"]]


def test_table_reaches_the_prompt_context():
    """Without this the model silently loses part of the section it is asked to ground on."""
    rendered = ccs._render_body([
        _as_block(table(["Type", "Size"], [["int", "32-bit"], ["double", "64-bit"]]))
    ])
    assert "Type | Size" in rendered
    assert "int | 32-bit" in rendered
    assert "double | 64-bit" in rendered


def test_table_words_count_toward_section_length():
    """`n_words` feeds `time_per_100_words`; a table-heavy section must not read as near-empty."""
    from app.services import section_features as sf

    shape = sf.section_shape_from_blocks([
        _as_block(table(["Comparison", "Checks"], [["==", "same object"], [".equals()", "contents"]]))
    ])
    assert shape["n_words"] > 0


def test_empty_table_renders_nothing_rather_than_stray_pipes():
    assert ccs._render_body([_as_block(table([], []))]).strip() == ""


def test_ragged_rows_do_not_raise():
    """The helper deliberately does not pad rows; a content typo must never break a request."""
    rendered = ccs._render_body([_as_block(table(["A", "B", "C"], [["1"], ["1", "2", "3"]]))])
    assert "A | B | C" in rendered


def test_assessment_exclusion_still_holds_alongside_tables():
    """Regression guard for PR #73 — adding a block type must not reopen the answer leak."""
    from app.db.course_content_helpers import exercise

    rendered = ccs._render_body([
        _as_block(table(["K", "V"], [["a", "b"]]), 0),
        _as_block(exercise("Why does == fail here?", "SECRET_ANSWER"), 1),
    ])
    assert "K | V" in rendered
    assert "SECRET_ANSWER" not in rendered
    assert "Why does == fail" not in rendered


def test_java_course_builds_and_has_reachable_exercises():
    """The Java course exists partly to make `show_answer_used` observable in production.

    Only 5 sections platform-wide carried an exercise before it, which is why that signal was
    still unverified after Phase 1 shipped.
    """
    from app.db.course_content.java import build

    course = build()
    sections = [s for m in course.modules for l in m.lessons for s in l.sections]
    assert len(sections) >= 6

    def kinds(sec):
        return {getattr(b.block_type, "value", b.block_type) for b in (sec.content_blocks or [])}

    assert sum(1 for s in sections if "exercise" in kinds(s)) >= 2
    assert any("table" in kinds(s) for s in sections)
    # Mermaid is authored as a code block with language "mermaid" — reused, not reinvented.
    assert any(
        (b.content or {}).get("language") == "mermaid"
        for s in sections for b in (s.content_blocks or [])
    )


def test_java_sections_vary_in_length():
    """The existing 49 sections cluster at 4-5 minutes regardless of content, which is exactly
    why `estimated_duration_minutes` was useless as a confusion feature. Do not reproduce it."""
    from app.db.course_content.java import build
    from app.services import section_features as sf

    course = build()
    words = [
        sf.section_shape_from_blocks(s.content_blocks or [])["n_words"]
        for m in course.modules for l in m.lessons for s in l.sections
    ]
    assert max(words) >= min(words) * 1.4, f"sections too uniform: {sorted(words)}"
