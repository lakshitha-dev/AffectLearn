"""Seed demo course content (courses → modules → lessons → sections → blocks).

Idempotent: a course is skipped if one with the same title already exists.
Run with:  python -m app.db.seed_demo_courses
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.course import (
    BlockType,
    ContentBlock,
    Course,
    Lesson,
    Module,
    Section,
)


def _blocks(*specs) -> list[ContentBlock]:
    """Build ContentBlock rows from (block_type, content) tuples."""
    out = []
    for i, (btype, content) in enumerate(specs):
        out.append(
            ContentBlock(
                block_type=btype,
                content=content,
                sort_order=i,
                variant_key="original",
                variant_group=uuid.uuid4(),
            )
        )
    return out


def _section(title, order, duration, *block_specs) -> Section:
    return Section(
        title=title,
        sort_order=order,
        estimated_duration_minutes=duration,
        content_blocks=_blocks(*block_specs),
    )


def _build_courses() -> list[Course]:
    T = BlockType.text
    C = BlockType.code
    K = BlockType.callout
    Q = BlockType.quiz
    E = BlockType.exercise

    # ------------------------------------------------------------------
    # Course 1 — Introduction to Python Programming
    # ------------------------------------------------------------------
    python_course = Course(
        title="Introduction to Python Programming",
        description=(
            "A beginner-friendly journey into Python — from your first line of "
            "code to working with data structures. No prior experience needed."
        ),
        estimated_duration_minutes=90,
        is_published=True,
        learning_objectives=(
            "Write and run basic Python programs; understand variables, types, "
            "and control flow; work with lists and dictionaries."
        ),
        modules=[
            Module(
                title="Getting Started",
                description="Set up your mindset and write your first programs.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="Your First Program",
                        description="Run code and print output to the screen.",
                        sort_order=0,
                        sections=[
                            _section(
                                "Hello, World", 0, 5,
                                (T, {"text": (
                                    "Every programming journey starts with a single line "
                                    "of output. In Python, displaying text on screen takes "
                                    "just one function call.\n\n"
                                    "The print() function sends whatever you give it to the "
                                    "console. It is the simplest way to see what your program "
                                    "is doing."
                                )}),
                                (C, {"language": "python", "code": 'print("Hello, World!")'}),
                                (K, {"variant": "tip", "text": (
                                    "Tip: Strings in Python can use single or double quotes — "
                                    "'hello' and \"hello\" are equivalent."
                                )}),
                            ),
                            _section(
                                "Variables and Types", 1, 8,
                                (T, {"text": (
                                    "A variable is a name that points to a value. Python "
                                    "figures out the type for you — no need to declare it."
                                )}),
                                (C, {"language": "python", "code": (
                                    "name = \"Ada\"      # a string\n"
                                    "age = 36          # an integer\n"
                                    "height = 1.70     # a float\n"
                                    "is_engineer = True  # a boolean\n\n"
                                    "print(name, age, height, is_engineer)"
                                )}),
                                (Q, {
                                    "question": "Which value is a boolean?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": '"Ada"', "isCorrect": False},
                                        {"id": "b", "text": "36", "isCorrect": False},
                                        {"id": "c", "text": "True", "isCorrect": True},
                                        {"id": "d", "text": "1.70", "isCorrect": False},
                                    ],
                                    "explanation": "True (and False) are Python's two boolean values.",
                                }),
                            ),
                        ],
                    ),
                    Lesson(
                        title="Control Flow",
                        description="Make decisions with conditionals.",
                        sort_order=1,
                        sections=[
                            _section(
                                "Conditionals", 0, 7,
                                (T, {"text": (
                                    "Programs make decisions using if / elif / else. The "
                                    "indented block runs only when its condition is True."
                                )}),
                                (C, {"language": "python", "code": (
                                    "score = 82\n\n"
                                    "if score >= 90:\n"
                                    "    grade = \"A\"\n"
                                    "elif score >= 80:\n"
                                    "    grade = \"B\"\n"
                                    "else:\n"
                                    "    grade = \"C\"\n\n"
                                    "print(grade)"
                                )}),
                                (E, {
                                    "prompt": "What grade does the program above print for score = 82?",
                                    "answer": "B",
                                    "type": "text",
                                    "explanation": "82 is below 90 but at least 80, so the elif branch sets grade to B.",
                                }),
                            ),
                        ],
                    ),
                ],
            ),
            Module(
                title="Working with Data",
                description="Store and organize collections of values.",
                sort_order=1,
                lessons=[
                    Lesson(
                        title="Lists and Dictionaries",
                        description="Python's two workhorse data structures.",
                        sort_order=0,
                        sections=[
                            _section(
                                "Working with Lists", 0, 8,
                                (T, {"text": (
                                    "A list holds an ordered collection of items. You can add "
                                    "to it, index into it, and loop over it."
                                )}),
                                (C, {"language": "python", "code": (
                                    "fruits = [\"apple\", \"banana\", \"cherry\"]\n"
                                    "fruits.append(\"date\")\n\n"
                                    "print(fruits[0])      # apple\n"
                                    "print(len(fruits))    # 4"
                                )}),
                                (K, {"variant": "warning", "text": (
                                    "Watch out: list indexing starts at 0, so the first item "
                                    "is fruits[0], not fruits[1]."
                                )}),
                                (Q, {
                                    "question": "What does fruits[0] return after the code above?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": '"apple"', "isCorrect": True},
                                        {"id": "b", "text": '"banana"', "isCorrect": False},
                                        {"id": "c", "text": '"date"', "isCorrect": False},
                                    ],
                                    "explanation": "Indexing starts at 0, so fruits[0] is the first item, 'apple'.",
                                }),
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    # ------------------------------------------------------------------
    # Course 2 — Foundations of Machine Learning
    # ------------------------------------------------------------------
    ml_course = Course(
        title="Foundations of Machine Learning",
        description=(
            "Understand the core ideas behind machine learning — what it is, the "
            "main families of algorithms, and how models learn from data."
        ),
        estimated_duration_minutes=60,
        is_published=True,
        learning_objectives=(
            "Distinguish supervised from unsupervised learning; explain training "
            "vs inference; describe overfitting and how to spot it."
        ),
        modules=[
            Module(
                title="Core Concepts",
                description="The vocabulary and intuition of ML.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="What is Machine Learning?",
                        description="Learning patterns from data instead of hard-coding rules.",
                        sort_order=0,
                        sections=[
                            _section(
                                "Supervised vs Unsupervised", 0, 10,
                                (T, {"text": (
                                    "Machine learning lets a program improve at a task by "
                                    "learning from examples, rather than following rules a "
                                    "human wrote by hand.\n\n"
                                    "In supervised learning the data is labelled — each "
                                    "example comes with the correct answer. In unsupervised "
                                    "learning there are no labels; the model finds structure "
                                    "on its own."
                                )}),
                                (K, {"variant": "info", "text": (
                                    "Spam detection is supervised (emails labelled spam / not "
                                    "spam). Customer segmentation is unsupervised (group "
                                    "similar customers with no predefined labels)."
                                )}),
                                (Q, {
                                    "question": "Which task is an example of supervised learning?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Grouping news articles by topic with no labels", "isCorrect": False},
                                        {"id": "b", "text": "Predicting house price from labelled sales data", "isCorrect": True},
                                        {"id": "c", "text": "Compressing an image", "isCorrect": False},
                                    ],
                                    "explanation": "Predicting price from labelled examples (price known) is supervised learning.",
                                }),
                            ),
                            _section(
                                "Overfitting", 1, 9,
                                (T, {"text": (
                                    "A model overfits when it memorises the training data "
                                    "instead of learning the general pattern. It scores well "
                                    "on data it has seen but poorly on new data.\n\n"
                                    "We detect this by holding out a separate test set the "
                                    "model never trains on."
                                )}),
                                (E, {
                                    "prompt": (
                                        "Fill in the blank: a model that performs great on "
                                        "training data but badly on unseen data is said to be "
                                        "______."
                                    ),
                                    "answer": "overfitting",
                                    "type": "text",
                                    "explanation": "This gap between training and test performance is the signature of overfitting.",
                                }),
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    # ------------------------------------------------------------------
    # Course 3 — Building APIs with FastAPI (draft / unpublished)
    # ------------------------------------------------------------------
    api_course = Course(
        title="Building APIs with FastAPI",
        description=(
            "Design and ship modern Python web APIs with FastAPI — routing, "
            "request validation, and automatic docs. (Draft course.)"
        ),
        estimated_duration_minutes=75,
        is_published=False,
        learning_objectives=(
            "Create endpoints, validate input with Pydantic, and read the "
            "auto-generated OpenAPI docs."
        ),
        modules=[
            Module(
                title="First Endpoint",
                description="Your first route in minutes.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="Hello FastAPI",
                        description="A minimal app that returns JSON.",
                        sort_order=0,
                        sections=[
                            _section(
                                "Defining a Route", 0, 6,
                                (T, {"text": (
                                    "FastAPI turns a plain Python function into a web endpoint "
                                    "with a decorator. The return value is serialised to JSON "
                                    "automatically."
                                )}),
                                (C, {"language": "python", "code": (
                                    "from fastapi import FastAPI\n\n"
                                    "app = FastAPI()\n\n"
                                    "@app.get(\"/ping\")\n"
                                    "def ping():\n"
                                    "    return {\"status\": \"ok\"}"
                                )}),
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    return [python_course, ml_course, api_course]


async def seed_demo_courses(db: AsyncSession) -> list[str]:
    """Insert demo courses that don't already exist (matched by title)."""
    created: list[str] = []
    for course in _build_courses():
        existing = await db.execute(
            select(Course).where(Course.title == course.title)
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(course)
        created.append(course.title)
    await db.commit()
    return created


async def run() -> None:
    async with async_session() as db:
        created = await seed_demo_courses(db)
    if created:
        print(f"Seeded {len(created)} course(s): " + "; ".join(created))
    else:
        print("Demo courses already present — no changes.")


if __name__ == "__main__":
    asyncio.run(run())
