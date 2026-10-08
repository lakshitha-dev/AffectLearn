"""Demo course: Python Basics: Repeating Code with Loops (published).

The course for the live viva demonstration (`app/db/seed_viva.py`). It is short enough to read in
front of examiners, and each of its three sections is built for one part of the demonstration:

  * "Why Programs Repeat Things" is deliberately easy. It has no authored `harder` variant, so when
    the learner looks away and the face channel reads sustained disengagement, the challenge card
    is written by the model from this section's own text.
  * "For Loops and range()" carries the classic off-by-one difficulty, two quizzes and an exercise
    with "Show answer", for the "I'm stuck" ladder. Its authored `simpler` variant is what the
    breakdown rung shows, next to generated hint and alternative text.
  * "While Loops and Stopping Safely" shows the richer block types: a Mermaid flowchart, a table,
    a quiz and a reflection. Finishing it leads to the post-check and the study survey.

Section titles are what the video sub-agent searches on when it has no brief, so they name the
concept a learner would type into YouTube.
"""

from __future__ import annotations

from app.db.assessment_content_helpers import assessment, option, question
from app.db.course_content_helpers import (
    callout,
    code,
    course,
    exercise,
    lesson,
    mermaid,
    module,
    quiz,
    reflection,
    section,
    table,
    text,
)
from app.db.demo_content import with_variants

TITLE = "Python Basics: Repeating Code with Loops"

WHY = "Why Programs Repeat Things"
FOR_RANGE = "For Loops and range()"
WHILE = "While Loops and Stopping Safely"


def build():
    return course(
        TITLE,
        "A short, friendly introduction to loops in Python. Learn why programs repeat things, "
        "how a for loop works with range(), and how to write a while loop that stops when it "
        "should.",
        "Explain why loops are useful; predict the numbers range() produces; count how many "
        "times a for loop runs; and write a while loop that stops safely.",
        20,
        module(
            "Loops",
            "Repeat code without writing it again and again.",
            lesson(
                "Repeating Code with Loops",
                "Why loops exist, for loops with range(), and while loops.",
                section(
                    WHY, 4,
                    text(
                        "Imagine you want to print the word Hello five times. You could write "
                        "print(\"Hello\") five times, one line under the other. That works, but "
                        "it is slow to write and easy to get wrong. If you later need it 100 "
                        "times, you would need 100 lines.\n\n"
                        "A loop solves this. A loop tells Python: run these lines again and "
                        "again. You write the instruction once, and Python repeats it for you.\n\n"
                        "Each time the loop runs its lines is called an iteration. A loop that "
                        "prints Hello five times makes five iterations."
                    ),
                    code(
                        "# Without a loop: five lines that do the same thing\n"
                        "print(\"Hello\")\n"
                        "print(\"Hello\")\n"
                        "print(\"Hello\")\n"
                        "print(\"Hello\")\n"
                        "print(\"Hello\")\n"
                        "\n"
                        "# With a loop: two lines, the same result\n"
                        "for i in range(5):\n"
                        "    print(\"Hello\")"
                    ),
                    callout(
                        "The lines that belong to a loop are indented: moved four spaces to the "
                        "right. Python uses the indentation to know which lines to repeat.",
                        "tip",
                    ),
                    quiz(
                        "What is the main reason to use a loop?",
                        [("To repeat instructions without writing them again and again", True),
                         ("To make a program run only once", False),
                         ("To store a list of names", False),
                         ("To stop a program when there is an error", False)],
                        "A loop repeats the same instructions, so you only write them once.",
                    ),
                ),
                with_variants(
                    section(
                        FOR_RANGE, 6,
                        text(
                            "A for loop repeats its lines once for every value it is given. The "
                            "most common way to give it values is range().\n\n"
                            "range(5) produces the numbers 0, 1, 2, 3 and 4. It starts at 0 and "
                            "stops BEFORE 5. So the loop runs five times, but the last number "
                            "is 4, not 5.\n\n"
                            "You can also give range() a start. range(2, 6) produces 2, 3, 4 and "
                            "5. The rule is the same: the start is included, the stop is not. A "
                            "third number is the step, so range(0, 10, 2) counts up in twos.\n\n"
                            "To count how many times a loop with range(start, stop) runs, "
                            "subtract: stop minus start. range(2, 6) runs 6 - 2 = 4 times."
                        ),
                        code(
                            "for number in range(2, 6):\n"
                            "    print(number)\n"
                            "\n"
                            "# Output:\n"
                            "# 2\n"
                            "# 3\n"
                            "# 4\n"
                            "# 5"
                        ),
                        table(
                            ["You write", "Numbers produced", "Times the loop runs"],
                            [
                                ["range(5)", "0, 1, 2, 3, 4", "5"],
                                ["range(1, 5)", "1, 2, 3, 4", "4"],
                                ["range(2, 6)", "2, 3, 4, 5", "4"],
                                ["range(0, 10, 2)", "0, 2, 4, 6, 8", "5"],
                            ],
                        ),
                        quiz(
                            "What is the LAST number printed by:  for i in range(1, 5): print(i)",
                            [("5", False), ("4", True), ("1", False), ("0", False)],
                            "range() stops before the stop value, so the last number is 4.",
                        ),
                        quiz(
                            "How many times does this loop run?  for i in range(3, 8): print(i)",
                            [("8", False), ("5", True), ("6", False), ("3", False)],
                            "Stop minus start: 8 - 3 = 5 times (3, 4, 5, 6 and 7).",
                        ),
                        exercise(
                            "How many times does print run in this code?  "
                            "for n in range(2, 6): print(n)   Type a number.",
                            "4",
                            "range(2, 6) produces 2, 3, 4 and 5. That is four numbers, so print "
                            "runs four times.",
                        ),
                    ),
                    0,
                    simpler=(
                        "Let's take it one step at a time.\n\n"
                        "Step 1. range(stop) counts from 0 up to the stop number, but never "
                        "reaches it. range(3) gives 0, 1, 2.\n\n"
                        "Step 2. range(start, stop) begins at the start number instead of 0. "
                        "range(2, 6) gives 2, 3, 4, 5.\n\n"
                        "Step 3. Think of the stop number as a fence: you walk up to it, but you "
                        "never step on it. That is why 6 is not printed.\n\n"
                        "Step 4. To count the loops, subtract: stop minus start. 6 - 2 = 4 loops."
                    ),
                ),
                section(
                    WHILE, 5,
                    text(
                        "A for loop is best when you know how many times to repeat. A while "
                        "loop is for when you do not know in advance. It keeps repeating while a "
                        "condition is true, and stops as soon as the condition becomes false.\n\n"
                        "For example, a login page might keep asking for a password while the "
                        "answer is wrong. Python checks the condition before every iteration.\n\n"
                        "Be careful: if the condition never becomes false, the loop never stops. "
                        "This is called an infinite loop. To avoid it, make sure something inside "
                        "the loop changes the value that the condition checks."
                    ),
                    mermaid(
                        "flowchart TD\n"
                        "    A[Start] --> B{Is the condition true?}\n"
                        "    B -- Yes --> C[Run the indented lines]\n"
                        "    C --> D[Change the value being checked]\n"
                        "    D --> B\n"
                        "    B -- No --> E[Carry on after the loop]"
                    ),
                    code(
                        "count = 3\n"
                        "while count > 0:\n"
                        "    print(count)\n"
                        "    count = count - 1   # without this line, the loop never ends\n"
                        "print(\"Lift off!\")\n"
                        "\n"
                        "# Output: 3, 2, 1, Lift off!"
                    ),
                    table(
                        ["", "for loop", "while loop"],
                        [
                            ["Use it when", "You know how many times to repeat",
                             "You repeat until something changes"],
                            ["It stops when", "It runs out of values",
                             "Its condition becomes false"],
                            ["Common mistake", "Off-by-one with range()",
                             "Forgetting to change the value, so it never stops"],
                        ],
                    ),
                    quiz(
                        "What happens if you remove the line  count = count - 1  from the example?",
                        [("The loop runs three times", False), ("The loop never stops", True),
                         ("Python prints Lift off! straight away", False),
                         ("The loop runs once", False)],
                        "count stays 3, so count > 0 is always true: an infinite loop.",
                    ),
                    reflection(
                        "Think of something in everyday life that repeats until a condition "
                        "changes, such as stirring tea until the sugar dissolves. Would you "
                        "describe it with a for loop or a while loop, and why?"
                    ),
                ),
            ),
        ),
    )


def build_pre():
    """Quick check before the lesson: sets the learner's starting skill level."""
    return assessment(
        "Loops: Quick Check (before)",
        "pre",
        question(
            "What is the best way to print \"Hi\" 50 times?",
            [option("Write print(\"Hi\") 50 times"), option("Use a loop", True),
             option("Use an if statement"), option("Use a comment")],
            pair_key="loop_purpose", section_title=WHY,
            explanation="A loop repeats the instruction, so you write it once.",
        ),
        question(
            "Which numbers does range(1, 4) produce?",
            [option("1, 2, 3", True), option("1, 2, 3, 4"), option("0, 1, 2, 3"),
             option("Only 4")],
            pair_key="range_stop", section_title=FOR_RANGE,
            explanation="The start is included and the stop is not.",
        ),
        question(
            "When does a while loop stop?",
            [option("When its condition becomes false", True),
             option("After exactly 10 iterations"), option("Never"),
             option("When it reaches the end of the file")],
            pair_key="while_stop", section_title=WHILE,
            explanation="A while loop repeats only while its condition is true.",
        ),
    )


def build_post():
    """Quick check after the lesson: the same three ideas, with different details."""
    return assessment(
        "Loops: Quick Check (after)",
        "post",
        question(
            "You need to send the same reminder to 30 students. What should your program use?",
            [option("A loop", True), option("30 separate lines of code"),
             option("An if statement"), option("A comment")],
            pair_key="loop_purpose", section_title=WHY,
            explanation="The same action repeated 30 times is exactly what a loop is for.",
        ),
        question(
            "Which numbers does range(3, 6) produce?",
            [option("3, 4, 5", True), option("3, 4, 5, 6"), option("4, 5, 6"),
             option("0, 1, 2, 3, 4, 5")],
            pair_key="range_stop", section_title=FOR_RANGE,
            explanation="It starts at 3 and stops before 6.",
        ),
        question(
            "x = 5, then  while x > 0: x = x - 1.  When does this loop stop?",
            [option("When x reaches 0", True), option("When x reaches 5"),
             option("It never stops"), option("After one iteration")],
            pair_key="while_stop", section_title=WHILE,
            explanation="x goes down by one each time, and the condition x > 0 is false at 0.",
        ),
    )
