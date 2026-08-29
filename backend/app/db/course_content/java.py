"""Introductory Java course — a short, self-contained end-to-end study flow.

Purpose (two-fold):

1. A SIMPLE course. The other four seeded courses are all Agentic AI and fairly dense. This one is
   deliberately gentle and complete on its own: variables -> control flow -> objects, finishing
   with a small program that uses all three.

2. A SECOND SUBJECT DOMAIN. Every existing section is one topic area, which is a real limitation
   when the platform's whole premise is adapting to any course. A learner-facing hint about Java
   exercises the same grounding path on material the system has never seen.

Authoring conventions (match the other course modules):
- `# affect:` above every `section()` — AFFECT_SECTION_CODEBOOK.md depends on it.
- Section lengths VARY on purpose (~100-300 words). The existing 49 sections cluster at 4-5
  minutes regardless of content, which is exactly why `estimated_duration_minutes` turned out to
  be useless as a confusion feature. Do not reproduce that.
- TWO sections carry an `exercise`, so the "Show answer" affordance is reachable here. Only 5
  sections platform-wide had one before this course, which is why `show_answer_used` had never
  been observed in production.
"""

from __future__ import annotations

from app.db.course_content_helpers import (
    callout,
    code,
    course,
    exercise,
    lesson,
    mermaid,
    module,
    quiz,
    section,
    table,
    text,
)

JAVA_TITLE = "Java Essentials: From First Program to Objects"


def build():
    return course(
        JAVA_TITLE,
        "A short, hands-on introduction to Java — variables, control flow, methods and objects — "
        "ending with a small program that puts them together.",
        "Write and read basic Java: declare variables, use conditions and loops, write methods, "
        "and model data with a class.",
        30,
        module(
            "Java Essentials",
            "Everything you need to read and write simple Java programs.",
            _lesson_basics(),
            _lesson_flow(),
            _lesson_objects(),
        ),
    )


def _lesson_basics():
    return lesson(
        "Values and Variables",
        "How Java stores data, and why its types matter.",
        # affect: engaged
        section(
            "Your First Java Program", 3,
            text(
                "Every Java program starts inside a class, and every runnable class needs a "
                "`main` method. That is the entry point the Java runtime looks for when you run "
                "your program.\n\n"
                "Here is the whole thing — the smallest complete Java program you can write."
            ),
            code(
                'public class Hello {\n'
                '    public static void main(String[] args) {\n'
                '        System.out.println("Hello, Java!");\n'
                '    }\n'
                '}',
                "java",
            ),
            text(
                "Reading it piece by piece: `public class Hello` declares a class named Hello. "
                "`public static void main(String[] args)` is the method Java calls to start. "
                "`System.out.println(...)` prints a line to the console.\n\n"
                "The file must be named `Hello.java` — matching the public class name. Java is "
                "strict about that, and it is one of the first things beginners trip over."
            ),
            callout(
                "Java is case-sensitive. `System` works; `system` does not.",
                variant="tip",
            ),
        ),
        # affect: engaged
        section(
            "Primitive Types", 4,
            text(
                "Java asks you to say what kind of value a variable holds, and it holds you to "
                "it. That is what people mean when they call Java statically typed: the type is "
                "fixed when you write the code, not when you run it.\n\n"
                "There are eight primitive types. In practice you will use four of them most of "
                "the time."
            ),
            table(
                ["Type", "Holds", "Example", "Typical use"],
                [
                    ["int", "Whole numbers", "42", "Counting, indexes"],
                    ["double", "Decimal numbers", "3.14", "Measurements, money*"],
                    ["boolean", "true or false", "true", "Conditions, flags"],
                    ["char", "A single character", "'A'", "Individual letters"],
                ],
            ),
            code(
                'int score = 42;\n'
                'double price = 19.99;\n'
                'boolean isReady = true;\n'
                'char grade = \'A\';',
                "java",
            ),
            text(
                "Try to assign the wrong kind of value and the program will not compile at all — "
                "`int score = \"forty\";` is an error before it ever runs. That is the trade Java "
                "makes: more typing up front, fewer surprises later."
            ),
            callout(
                "*Not actually money. `double` is approximate, so 0.1 + 0.2 is not exactly 0.3. "
                "Real currency code uses BigDecimal.",
                variant="warning",
            ),
            quiz(
                "Which type would you use to store whether a user is logged in?",
                [("int", False), ("boolean", True), ("char", False), ("double", False)],
                explanation="A logged-in state is either true or false, which is exactly what "
                            "boolean represents.",
            ),
        ),
        # affect: confused
        section(
            "Primitives vs Objects", 5,
            text(
                "Here is the first thing about Java that genuinely surprises people. Some values "
                "are primitives, and some are objects — and they behave differently when you "
                "compare them.\n\n"
                "A primitive variable holds the value itself. An object variable holds a "
                "reference: a pointer to where the value lives. `String` is an object, not a "
                "primitive, and that has consequences."
            ),
            mermaid(
                "flowchart LR\n"
                "  A[\"int x = 5\"] --> B[\"memory: 5\"]\n"
                "  C[\"String s\"] --> D[\"reference\"] --> E[\"memory: 'hello'\"]"
            ),
            text(
                "Now the consequence. `==` compares what the variable holds. For a primitive "
                "that is the value, so it does what you expect. For an object it compares the "
                "REFERENCE — whether both variables point at the same place in memory, not "
                "whether the contents match."
            ),
            table(
                ["Comparison", "What it checks", "Use for"],
                [
                    ["==", "Same value (primitives) or same object (references)", "int, double, boolean, char"],
                    [".equals()", "Same contents", "String and other objects"],
                ],
            ),
            code(
                'String a = new String("hi");\n'
                'String b = new String("hi");\n'
                '\n'
                'a == b        // false — two different objects\n'
                'a.equals(b)   // true  — same contents',
                "java",
            ),
            callout(
                "Comparing Strings with == is one of the most common Java bugs. It sometimes "
                "appears to work, which makes it worse: identical literals can share one object, "
                "so == may return true by accident and then fail on other input.",
                variant="warning",
            ),
            exercise(
                "You have two String variables holding user input. Which comparison should you "
                "use to check whether the user typed the same word twice, and why?",
                ".equals()",
                explanation="Strings are objects, so == would ask whether the two variables point "
                            "at the same object in memory. Two separately-entered words are "
                            "different objects even when the text matches, so you need .equals(), "
                            "which compares contents.",
            ),
        ),
    )


def _lesson_flow():
    return lesson(
        "Control Flow and Methods",
        "Making decisions, repeating work, and packaging it up.",
        # affect: engaged
        section(
            "Conditions and Loops", 4,
            text(
                "Two building blocks cover most of what programs do: choosing between paths, and "
                "repeating work.\n\n"
                "An `if` statement picks a branch based on a boolean. A `for` loop repeats a "
                "block a set number of times."
            ),
            code(
                'int score = 72;\n'
                '\n'
                'if (score >= 70) {\n'
                '    System.out.println("Pass");\n'
                '} else {\n'
                '    System.out.println("Try again");\n'
                '}\n'
                '\n'
                'for (int i = 1; i <= 3; i++) {\n'
                '    System.out.println("Attempt " + i);\n'
                '}',
                "java",
            ),
            text(
                "The `for` loop header has three parts separated by semicolons: start at `i = 1`, "
                "keep going while `i <= 3`, and add one each time round. Read it as \"start here, "
                "continue while this is true, do this between passes\"."
            ),
            mermaid(
                "flowchart TD\n"
                "  S([Start]) --> C{score >= 70?}\n"
                "  C -->|yes| P[Print 'Pass']\n"
                "  C -->|no| F[Print 'Try again']\n"
                "  P --> E([End])\n"
                "  F --> E"
            ),
        ),
        # affect: engaged
        section(
            "Methods", 4,
            text(
                "A method is a named piece of work you can run whenever you need it. Instead of "
                "repeating the same lines, you give them a name and call it.\n\n"
                "A method declares what it gives back and what it needs. This one returns a "
                "`String` and needs an `int`."
            ),
            code(
                'public static String gradeFor(int score) {\n'
                '    if (score >= 70) {\n'
                '        return "Pass";\n'
                '    }\n'
                '    return "Try again";\n'
                '}\n'
                '\n'
                '// calling it\n'
                'String result = gradeFor(72);   // "Pass"',
                "java",
            ),
            table(
                ["Part", "In the example", "Means"],
                [
                    ["Return type", "String", "What it hands back"],
                    ["Name", "gradeFor", "How you call it"],
                    ["Parameter", "int score", "What it needs"],
                    ["Body", "the if / return", "What it does"],
                ],
            ),
            text(
                "A method that returns nothing uses `void` — that is what `main` does. Once the "
                "logic has a name, the calling code reads as intent rather than mechanics."
            ),
        ),
    )


def _lesson_objects():
    return lesson(
        "Objects and a Small Program",
        "Modelling data with a class, and putting it all together.",
        # affect: confused
        section(
            "Classes and Objects", 5,
            text(
                "So far the values have been loose — an int here, a String there. A class lets "
                "you group related data and give it a name.\n\n"
                "Think of a class as the blueprint and an object as one thing built from it. One "
                "`Student` class; many student objects."
            ),
            code(
                'public class Student {\n'
                '    String name;\n'
                '    int score;\n'
                '\n'
                '    Student(String name, int score) {\n'
                '        this.name = name;\n'
                '        this.score = score;\n'
                '    }\n'
                '\n'
                '    String grade() {\n'
                '        return score >= 70 ? "Pass" : "Try again";\n'
                '    }\n'
                '}',
                "java",
            ),
            text(
                "Three parts. The fields (`name`, `score`) hold each student's data. The "
                "constructor — the method with the same name as the class — builds one. The "
                "method `grade()` answers a question about that particular student.\n\n"
                "`this.name = name` looks odd at first. The parameter and the field share a name, "
                "so `this.` says \"the field belonging to this object\", not the parameter."
            ),
            mermaid(
                "flowchart LR\n"
                "  C[\"class Student<br/>(blueprint)\"] --> A[\"ada<br/>name='Ada' score=91\"]\n"
                "  C --> B[\"raj<br/>name='Raj' score=64\"]"
            ),
            callout(
                "`score >= 70 ? \"Pass\" : \"Try again\"` is a ternary — a compact if/else that "
                "produces a value. Read it as: condition ? value-if-true : value-if-false.",
                variant="info",
            ),
        ),
        # affect: frustrated
        section(
            "Putting It Together", 5,
            text(
                "This program uses everything from the course: a class with fields and a method, "
                "an array of objects, a loop, and a condition.\n\n"
                "Read it once through before worrying about the details."
            ),
            code(
                'public class Report {\n'
                '    public static void main(String[] args) {\n'
                '        Student[] students = {\n'
                '            new Student("Ada", 91),\n'
                '            new Student("Raj", 64),\n'
                '            new Student("Mei", 78)\n'
                '        };\n'
                '\n'
                '        int passes = 0;\n'
                '\n'
                '        for (Student s : students) {\n'
                '            System.out.println(s.name + ": " + s.grade());\n'
                '            if (s.grade().equals("Pass")) {\n'
                '                passes++;\n'
                '            }\n'
                '        }\n'
                '\n'
                '        System.out.println(passes + " of " + students.length + " passed");\n'
                '    }\n'
                '}',
                "java",
            ),
            text(
                "Output:\n\n"
                "Ada: Pass\n"
                "Raj: Try again\n"
                "Mei: Pass\n"
                "2 of 3 passed\n\n"
                "`for (Student s : students)` is an enhanced for loop — \"for each Student s in "
                "students\". Use it when you want every element and do not need the index.\n\n"
                "Note `s.grade().equals(\"Pass\")` rather than `==`. `grade()` returns a String, "
                "and String is an object."
            ),
            exercise(
                "The program counts passes with `s.grade().equals(\"Pass\")`. What would go wrong "
                "if you wrote `s.grade() == \"Pass\"` instead, and why?",
                "It compares references, not text",
                explanation="== asks whether the two sides are the same object in memory. "
                            "grade() returns a String built at runtime, which is a different "
                            "object from the literal \"Pass\" even though the text matches — so "
                            "the count would be wrong. This is the primitives-vs-objects "
                            "distinction from lesson one, showing up in real code.",
            ),
            quiz(
                "Why does the loop use .equals() instead of == to compare the grade?",
                [
                    ("Because == does not work on Strings at all", False),
                    ("Because String is an object, so == compares references not contents", True),
                    ("Because .equals() is faster", False),
                    ("Because == only works on numbers", False),
                ],
                explanation="String is an object. == compares whether both sides reference the "
                            "same object; .equals() compares the actual text.",
            ),
        ),
    )
