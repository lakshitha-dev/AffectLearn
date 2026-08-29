"""Authoring helpers for the pilot course content (courses → modules → lessons →
sections → content blocks).

Course files under `app/db/course_content/` compose rich sections with these helpers
instead of hand-building ContentBlock rows. Block content shapes match what the
frontend renderers expect:
  - text:     {"text": "...\n\npara2"}                (ContentBlockRenderer -> paragraphs)
  - code:     {"language": "python", "code": "..."}   (language "mermaid" -> diagram/chart)
  - callout:  {"variant": "info|tip|warning", "text": "..."}
  - quiz:     {"question","type":"single|multiple","options":[{id,text,isCorrect}],"explanation"}
  - exercise: {"prompt","answer","type":"text","explanation"}   (also used for reflections)

Sort order within a section is auto-assigned from argument order.
"""

from __future__ import annotations

import uuid

from app.models.course import (
    BlockType,
    ContentBlock,
    Course,
    Lesson,
    Module,
    Section,
)

__all__ = [
    "Course", "Module", "Lesson",
    "text", "code", "mermaid", "callout", "quiz", "exercise", "reflection",
    "section", "lesson", "module", "course",
]

# --- block builders: each returns a (BlockType, content_dict) tuple ------------

def text(body: str):
    return (BlockType.text, {"text": body})


def code(source: str, language: str = "python"):
    return (BlockType.code, {"language": language, "code": source})


def mermaid(source: str):
    """A Mermaid diagram/chart — rendered by the frontend MermaidDiagram component."""
    return (BlockType.code, {"language": "mermaid", "code": source})


def table(headers: list[str], rows: list[list[str]]):
    """A comparison table — rendered as a real `<table>` by `TableBlock.tsx`.

    Text blocks are emitted as plain `<p>` paragraphs with no markdown parsing, so a markdown
    table would render as literal `|` characters. This is the supported way to show tabular
    material (`int` vs `double`, `==` vs `.equals`, and so on).

    Rows are NOT padded or validated against the header count — a ragged row renders with empty
    trailing cells rather than raising, so a content typo can never break a lesson at request time.
    """
    return (BlockType.table, {
        "headers": [str(h) for h in headers],
        "rows": [[str(c) for c in row] for row in rows],
    })


def callout(body: str, variant: str = "info"):
    """variant: info | tip | warning."""
    return (BlockType.callout, {"variant": variant, "text": body})


def quiz(question: str, options: list[tuple[str, bool]], explanation: str = "",
         multiple: bool = False):
    """options: list of (text, is_correct). Auto-ids a, b, c, ..."""
    opts = [
        {"id": chr(ord("a") + i), "text": t, "isCorrect": bool(correct)}
        for i, (t, correct) in enumerate(options)
    ]
    return (BlockType.quiz, {
        "question": question,
        "type": "multiple" if multiple else "single",
        "options": opts,
        "explanation": explanation,
    })


def exercise(prompt: str, answer: str, explanation: str = ""):
    return (BlockType.exercise, {
        "prompt": prompt, "answer": answer, "type": "text", "explanation": explanation,
    })


def reflection(prompt: str, guidance: str = "There is no single right answer — jot down your own thinking."):
    """An open reflection prompt (an exercise with no graded answer)."""
    return (BlockType.exercise, {
        "prompt": prompt, "answer": "", "type": "text", "explanation": guidance,
    })


# --- structure builders -------------------------------------------------------

def section(title: str, duration_min: int, *blocks) -> Section:
    """Build a Section from (BlockType, content) tuples in argument order."""
    content_blocks = [
        ContentBlock(
            block_type=btype,
            content=content,
            sort_order=i,
            variant_key="original",
            variant_group=uuid.uuid4(),
        )
        for i, (btype, content) in enumerate(blocks)
    ]
    return Section(title=title, sort_order=0, estimated_duration_minutes=duration_min,
                   content_blocks=content_blocks)


def lesson(title: str, description: str, *sections: Section) -> Lesson:
    for i, s in enumerate(sections):
        s.sort_order = i
    return Lesson(title=title, description=description, sort_order=0, sections=list(sections))


def module(title: str, description: str, *lessons: Lesson) -> Module:
    for i, ls in enumerate(lessons):
        ls.sort_order = i
    return Module(title=title, description=description, sort_order=0, lessons=list(lessons))


def course(title: str, description: str, objectives: str, duration_min: int,
           *modules: Module) -> Course:
    for i, m in enumerate(modules):
        m.sort_order = i
    return Course(
        title=title,
        description=description,
        learning_objectives=objectives,
        estimated_duration_minutes=duration_min,
        is_published=True,
        modules=list(modules),
    )
