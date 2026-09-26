"""Demo course: Web Development Fundamentals (published).

The course the demo learner has finished. Its opening section is gentle enough that learners who
already know HTML drift (the seeded class shows it as the course's boredom spot), and its
Flexbox section is the one where most of them get stuck — each with authored variants.
"""

from __future__ import annotations

from app.db.course_content_helpers import (
    callout,
    code,
    course,
    exercise,
    lesson,
    module,
    quiz,
    section,
    table,
    text,
)
from app.db.demo_content import with_variants

TITLE = "Web Development Fundamentals"


def build():
    return course(
        TITLE,
        "Build and style your first web pages. Learn how HTML gives a page its structure, how "
        "CSS controls layout, and how JavaScript makes it respond to the user.",
        "Structure a page with semantic HTML; explain the CSS box model; lay out a page with "
        "Flexbox; select and change elements with JavaScript; and respond to user events.",
        70,
        module(
            "Structuring Pages with HTML",
            "What a web page is made of.",
            lesson(
                "HTML Essentials",
                "Elements, tags and the structure every page shares.",
                with_variants(
                    section(
                        "How a Web Page Is Built", 6,
                        text(
                            "Every web page is a text file written in HTML — HyperText Markup "
                            "Language. The browser downloads the file, reads it from top to "
                            "bottom, and draws what it describes.\n\n"
                            "HTML is made of elements. Most elements have an opening tag, some "
                            "content and a closing tag: <p>Hello</p> is a paragraph. Elements "
                            "sit inside each other, so a page is really a tree: <html> contains "
                            "<head> and <body>, and <body> contains everything you see.\n\n"
                            "Attributes add extra information to an element, such as the "
                            "address a link points to: <a href=\"https://example.com\">."
                        ),
                        code(
                            "<!DOCTYPE html>\n"
                            "<html>\n"
                            "  <head>\n"
                            "    <title>My first page</title>\n"
                            "  </head>\n"
                            "  <body>\n"
                            "    <h1>Hello!</h1>\n"
                            "    <p>This is my first web page.</p>\n"
                            "  </body>\n"
                            "</html>",
                            language="html",
                        ),
                        quiz(
                            "Where does content the visitor SEES go?",
                            [("Inside <head>", False), ("Inside <body>", True),
                             ("Inside <title>", False), ("After </html>", False)],
                            "<head> holds information ABOUT the page; <body> holds what is shown.",
                        ),
                    ),
                    0,
                    harder=(
                        "You already know the basics, so look at what the browser does with "
                        "them. The HTML is parsed into the DOM — a live tree of objects — and "
                        "the parser is forgiving: an unclosed <p> is closed for you, and a "
                        "stray element in <head> is moved into <body>.\n\n"
                        "Open your browser's developer tools on any site and compare 'View "
                        "Source' with the Elements panel. Where they differ, the parser has "
                        "repaired the markup. Can you find a page where it had to?"
                    ),
                ),
                section(
                    "Semantic HTML Tags", 7,
                    text(
                        "Semantic tags say what content IS, not just how it looks. <header>, "
                        "<nav>, <main>, <article> and <footer> describe the parts of a page, "
                        "where a plain <div> says nothing at all.\n\n"
                        "This matters for three reasons. Screen readers use these tags to let "
                        "people jump straight to the navigation or the main content. Search "
                        "engines use them to understand the page. And the next developer can "
                        "read your structure at a glance."
                    ),
                    table(
                        ["Tag", "Use it for"],
                        [
                            ["<header>", "The introduction or banner of a page or section"],
                            ["<nav>", "The main navigation links"],
                            ["<main>", "The primary content — once per page"],
                            ["<article>", "A self-contained piece, like a blog post"],
                            ["<footer>", "Closing information: contact, copyright"],
                        ],
                    ),
                    quiz(
                        "Which element should wrap a site's main navigation links?",
                        [("<div>", False), ("<nav>", True), ("<menu-bar>", False),
                         ("<section>", False)],
                        "<nav> marks navigation, so assistive technology can find it directly.",
                    ),
                ),
            ),
        ),
        module(
            "Styling and Interactivity",
            "Make pages look right on any screen, then make them respond.",
            lesson(
                "Layout with CSS",
                "How the browser sizes boxes, and how to arrange them.",
                section(
                    "The CSS Box Model", 8,
                    text(
                        "To the browser, every element is a rectangular box made of four "
                        "layers: the content, then padding around it, then a border, then a "
                        "margin that pushes other boxes away.\n\n"
                        "By default, width sets only the CONTENT width, so padding and border "
                        "make the box larger than the number you wrote. Setting box-sizing: "
                        "border-box makes width include padding and border, which is far "
                        "easier to reason about — most projects set it on every element."
                    ),
                    code(
                        ".card {\n"
                        "  width: 300px;\n"
                        "  padding: 20px;\n"
                        "  border: 2px solid #ccc;\n"
                        "  margin: 16px;\n"
                        "  box-sizing: border-box;  /* the card is exactly 300px wide */\n"
                        "}",
                        language="css",
                    ),
                    quiz(
                        "Without border-box, a box has width: 200px, padding: 10px and "
                        "border: 5px. How wide is it on screen?",
                        [("200px", False), ("215px", False), ("230px", True), ("210px", False)],
                        "200 + 10 + 10 (padding both sides) + 5 + 5 (border both sides) = 230px.",
                    ),
                ),
                with_variants(
                    section(
                        "Flexbox Layouts", 10,
                        text(
                            "display: flex turns an element into a flex container and its "
                            "children into flex items laid out along the main axis, which "
                            "flex-direction sets to row by default. justify-content distributes "
                            "items along the main axis; align-items aligns them on the cross "
                            "axis, perpendicular to it. When flex-direction is column the axes "
                            "swap, so justify-content becomes vertical and align-items "
                            "horizontal.\n\n"
                            "Items shrink to fit by default (flex-shrink: 1) and do not wrap "
                            "unless flex-wrap: wrap is set; flex-grow decides how leftover "
                            "space is shared between them."
                        ),
                        code(
                            ".toolbar {\n"
                            "  display: flex;\n"
                            "  justify-content: space-between;  /* spread along the row */\n"
                            "  align-items: center;             /* centre vertically */\n"
                            "  gap: 12px;\n"
                            "}",
                            language="css",
                        ),
                        callout(
                            "Stuck on which property to use? Ask: am I moving items ALONG the "
                            "direction they flow (justify-content) or ACROSS it (align-items)?",
                            variant="tip",
                        ),
                        quiz(
                            "A container has display: flex and flex-direction: column. Which "
                            "property centres the items horizontally?",
                            [("justify-content: center", False), ("align-items: center", True),
                             ("text-align: center", False), ("flex-wrap: center", False)],
                            "In a column the main axis is vertical, so the horizontal cross "
                            "axis is controlled by align-items.",
                        ),
                    ),
                    0,
                    simpler=(
                        "Flexbox lines up boxes in a row (or a column).\n\n"
                        "Put display: flex on the parent. Now its children sit side by side.\n"
                        "justify-content moves them along the line: to the start, the centre, "
                        "or spread out.\n"
                        "align-items moves them the other way: up, down or centred.\n\n"
                        "One catch: if you change the line to a column, the two properties "
                        "swap directions. justify-content now works up and down."
                    ),
                    alternative=(
                        "Think of books on a shelf. The shelf is the flex container, the books "
                        "are the items. justify-content decides where the books sit ALONG the "
                        "shelf — bunched left, centred, or spread out with gaps.\n\n"
                        "align-items decides how each book sits UP AND DOWN on the shelf — "
                        "standing at the bottom, the top or the middle. Turn the shelf on its "
                        "end (flex-direction: column) and 'along' becomes up-and-down, so the "
                        "two properties trade jobs."
                    ),
                ),
            ),
            lesson(
                "Making Pages Interactive",
                "Use JavaScript to change the page while someone is using it.",
                section(
                    "JavaScript and the DOM", 9,
                    text(
                        "When the browser reads your HTML it builds the DOM — the Document "
                        "Object Model — a tree of objects, one per element. JavaScript can "
                        "read and change that tree, and the page updates immediately.\n\n"
                        "document.querySelector() finds the first element matching a CSS "
                        "selector. Once you have it you can change its text with textContent, "
                        "its classes with classList, or its styles with style."
                    ),
                    code(
                        "const title = document.querySelector('h1');\n"
                        "title.textContent = 'Welcome back!';\n"
                        "title.classList.add('highlight');",
                        language="javascript",
                    ),
                    quiz(
                        "What does document.querySelector('.card') return?",
                        [("Every element with class card", False),
                         ("The first element with class card", True),
                         ("The text of the card", False), ("A CSS rule", False)],
                        "querySelector returns the FIRST match; querySelectorAll returns them all.",
                    ),
                ),
                section(
                    "Responding to Events", 8,
                    text(
                        "An event is something that happens on the page: a click, a key press, "
                        "a form being submitted. addEventListener() runs a function of yours "
                        "every time a chosen event happens on an element.\n\n"
                        "For forms, call event.preventDefault() first — otherwise the browser "
                        "submits the form and reloads the page before your code can use the "
                        "values."
                    ),
                    code(
                        "const button = document.querySelector('#like');\n"
                        "let likes = 0;\n\n"
                        "button.addEventListener('click', () => {\n"
                        "  likes += 1;\n"
                        "  button.textContent = `Like (${likes})`;\n"
                        "});",
                        language="javascript",
                    ),
                    callout(
                        "Pass the function itself — addEventListener('click', handle) — not "
                        "the result of calling it: handle() would run once, immediately.",
                        variant="warning",
                    ),
                    exercise(
                        "Which method stops a form submission from reloading the page?",
                        "event.preventDefault()",
                        "Call it at the start of the submit handler.",
                    ),
                ),
            ),
        ),
    )
