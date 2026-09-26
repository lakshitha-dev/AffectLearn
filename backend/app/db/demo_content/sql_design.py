"""Demo course: Database Design with SQL (DRAFT — never published).

Shows the designer's work in progress: a course with real sections that learners cannot see yet,
so the editor has something to open that is not already live.
"""

from __future__ import annotations

from app.db.course_content_helpers import (
    callout,
    code,
    course,
    lesson,
    module,
    quiz,
    section,
    table,
    text,
)

TITLE = "Database Design with SQL"


def build():
    c = course(
        TITLE,
        "Design a relational database from scratch and query it with SQL. Model a small "
        "university's courses and enrolments, normalise the design, and write the queries that "
        "answer real questions about it.",
        "Model entities as tables with primary and foreign keys; normalise a design to third "
        "normal form; filter and sort with SELECT; and combine tables with JOIN.",
        60,
        module(
            "Designing a Relational Database",
            "From a messy spreadsheet to a clean set of related tables.",
            lesson(
                "Tables and Keys",
                "Every relational design starts here.",
                section(
                    "Tables, Rows and Columns", 7,
                    text(
                        "A relational database stores data in tables. Each table describes one "
                        "kind of thing — students, courses, enrolments — with one row per item "
                        "and one column per fact about it.\n\n"
                        "Every column has a type (INTEGER, TEXT, DATE), and the database "
                        "refuses values that do not fit. That strictness is the point: a "
                        "spreadsheet will happily accept 'twenty' in an age column; a database "
                        "will not."
                    ),
                    code(
                        "CREATE TABLE students (\n"
                        "  student_id  INTEGER PRIMARY KEY,\n"
                        "  full_name   TEXT NOT NULL,\n"
                        "  enrolled_on DATE\n"
                        ");",
                        language="sql",
                    ),
                ),
                section(
                    "Primary and Foreign Keys", 8,
                    text(
                        "A primary key uniquely identifies each row — no two students share a "
                        "student_id. A foreign key is a column that points at another table's "
                        "primary key, and it is how tables are related.\n\n"
                        "An enrolments table with student_id and course_id columns links "
                        "students to courses. The database checks every foreign key, so an "
                        "enrolment can never point at a student who does not exist."
                    ),
                    code(
                        "CREATE TABLE enrolments (\n"
                        "  student_id INTEGER REFERENCES students(student_id),\n"
                        "  course_id  INTEGER REFERENCES courses(course_id),\n"
                        "  PRIMARY KEY (student_id, course_id)\n"
                        ");",
                        language="sql",
                    ),
                    quiz(
                        "What does a foreign key guarantee?",
                        [("That the column is never empty", False),
                         ("That each value matches an existing row in another table", True),
                         ("That the column is sorted", False),
                         ("That the table has no duplicates", False)],
                        "A foreign key must reference an existing primary key value.",
                    ),
                ),
            ),
            lesson(
                "Normalisation",
                "Remove duplication before it turns into inconsistency.",
                section(
                    "Why Normalise?", 9,
                    text(
                        "When the same fact is stored in several rows, it will eventually be "
                        "updated in some and not others. If a lecturer's email appears on every "
                        "course they teach, changing it means finding every copy — and missing "
                        "one leaves the data contradicting itself.\n\n"
                        "Normalisation splits tables so each fact is stored exactly once. The "
                        "first three normal forms cover almost every practical case."
                    ),
                    table(
                        ["Normal form", "Rule of thumb"],
                        [
                            ["1NF", "One value per cell; no repeating groups"],
                            ["2NF", "Every column depends on the WHOLE key"],
                            ["3NF", "Non-key columns depend only on the key"],
                        ],
                    ),
                    callout(
                        "Draft note: add a worked example that normalises the lecturer "
                        "spreadsheet step by step.",
                        variant="info",
                    ),
                ),
            ),
        ),
        module(
            "Querying with SQL",
            "Ask the database questions.",
            lesson(
                "SELECT and JOIN",
                "Filtering, sorting and combining tables.",
                section(
                    "Filtering with WHERE", 7,
                    text(
                        "SELECT chooses the columns you want, FROM names the table, and WHERE "
                        "keeps only the rows that match a condition. ORDER BY sorts the result."
                    ),
                    code(
                        "SELECT full_name, enrolled_on\n"
                        "FROM students\n"
                        "WHERE enrolled_on >= '2026-01-01'\n"
                        "ORDER BY full_name;",
                        language="sql",
                    ),
                ),
                section(
                    "Joining Tables", 10,
                    text(
                        "A JOIN combines rows from two tables where a condition holds — "
                        "usually a foreign key equal to a primary key. An INNER JOIN keeps "
                        "only matching rows; a LEFT JOIN keeps every row from the left table "
                        "and fills the gaps with NULL."
                    ),
                    code(
                        "SELECT s.full_name, c.title\n"
                        "FROM enrolments e\n"
                        "JOIN students s ON s.student_id = e.student_id\n"
                        "JOIN courses  c ON c.course_id  = e.course_id;",
                        language="sql",
                    ),
                ),
            ),
        ),
    )
    c.is_published = False
    return c
