"""How each demo section tends to feel, and the help the seeded history says was given there.

SECTION_TAGS drives the simulated class: `intro` sections bore learners who already know the
material, `hard` ones confuse most of them, `moderate` ones some. The tags are the designer's
story for the analytics screens — the Flexbox and groupby sections are the hotspots she would
look at first.

HINTS are the texts in the seeded help history, written the way the Pedagogical agent writes:
grounded in the section, second person, short. They deliberately differ from the designer's
authored variants, because the Content Adapter will not repeat text a learner has already been
shown in a section — reusing a variant's wording here would stop a live demo from serving it.
"""

from __future__ import annotations

SECTION_TAGS: dict[str, str] = {
    # Python for Data Analysis
    "Lists: Ordered Collections": "normal",
    "Dictionaries: Looking Things Up by Key": "normal",
    "Defining and Calling Functions": "normal",
    "Default Arguments and Return Values": "moderate",
    "NumPy Arrays and Vectorised Maths": "normal",
    "Your First pandas DataFrame": "moderate",
    "Grouping and Aggregating with groupby": "hard",
    "Handling Missing Values": "moderate",
    # Web Development Fundamentals
    "How a Web Page Is Built": "intro",
    "Semantic HTML Tags": "normal",
    "The CSS Box Model": "moderate",
    "Flexbox Layouts": "hard",
    "JavaScript and the DOM": "normal",
    "Responding to Events": "moderate",
}

HINTS: dict[tuple[str, str], str] = {
    ("Grouping and Aggregating with groupby", "show_hint"): (
        "Try reading the line from left to right: groupby('region') decides WHICH rows belong "
        "together, ['amount'] picks the column to work on, and .sum() is what happens inside each "
        "group. Which part of that chain is the one you are unsure about?"
    ),
    ("Grouping and Aggregating with groupby", "show_breakdown"): (
        "Let's do it by hand first. Take just the West rows and add up their amounts — that one "
        "number is exactly what groupby produces for West. Now picture doing the same for East "
        "and North: the result is a small table with one total per region. The code simply does "
        "all three at once."
    ),
    ("Grouping and Aggregating with groupby", "show_alternative"): (
        "If you have used a pivot table in Excel, you already know groupby: the region is the "
        "row label, and sum of amount is the value field. pandas writes that pivot as "
        "sales.groupby('region')['amount'].sum()."
    ),
    ("Flexbox Layouts", "show_hint"): (
        "The quiz uses flex-direction: column, so the items stack top to bottom. That makes the "
        "vertical direction the MAIN axis — and horizontal centring the cross axis. Which "
        "property works on the cross axis?"
    ),
    ("Flexbox Layouts", "show_breakdown"): (
        "Step 1: find the main axis — row means left-to-right, column means top-to-bottom. "
        "Step 2: justify-content moves items along that main axis. Step 3: align-items moves "
        "them across it. For a column, 'across' is left-to-right, so horizontal centring is "
        "align-items: center."
    ),
    ("How a Web Page Is Built", "increase_difficulty"): (
        "You clearly know the basic structure already. Here's a stretch: open the developer "
        "tools on this page and compare View Source with the Elements panel. Can you find a "
        "place where the browser changed the HTML it was given?"
    ),
    ("The CSS Box Model", "show_hint"): (
        "Padding and border are added on BOTH sides of the box. Count them twice before adding "
        "them to the width."
    ),
    ("Default Arguments and Return Values", "show_hint"): (
        "Look for the word return in the function. If it is not there, what does Python hand "
        "back to the caller by default?"
    ),
    ("Your First pandas DataFrame", "show_hint"): (
        "sales['region'] == 'West' on its own gives a column of True and False. To turn that "
        "into rows, put it inside sales[ ... ] — the same way you filtered a NumPy array with "
        "prices[prices > 500]."
    ),
    ("NumPy Arrays and Vectorised Maths", "show_hint"): (
        "Remember the difference from a list: an array does maths on every element at once, "
        "while [1, 2] * 2 repeats a list. Which one is prices here?"
    ),
    ("Dictionaries: Looking Things Up by Key", "show_hint"): (
        "get() takes two things: the key to look for, and what to return if it is missing. "
        "Check the second argument in the question."
    ),
    ("Responding to Events", "show_hint"): (
        "Check whether the handler is passed as handle or called as handle(). Only one of them "
        "waits for the click."
    ),
    ("Handling Missing Values", "show_hint"): (
        "Before choosing between dropna and fillna, count the gaps: isna() marks each missing "
        "cell, and sum() adds them up per column."
    ),
}

ENCOURAGEMENT = (
    "You have worked through most of this section already — the last part builds directly on "
    "what you just did. Take it one line at a time."
)


def hint_for(section_title: str, action: str) -> str:
    """The seeded text for an action in a section, with a sensible fallback."""
    if (section_title, action) in HINTS:
        return HINTS[(section_title, action)]
    if action == "show_encouragement":
        return ENCOURAGEMENT
    if action == "increase_difficulty":
        return (
            f"You are moving quickly through {section_title}. Try predicting the output of the "
            "example before you run it, then change one value and predict again."
        )
    return (
        f"Go back to the example in {section_title} and trace it one line at a time — say what "
        "each line produces before looking at the next."
    )
