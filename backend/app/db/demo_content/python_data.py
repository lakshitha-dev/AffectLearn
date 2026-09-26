"""Demo course: Python for Data Analysis (published).

The course the demo learner is part-way through. Its groupby section is written the way a real
first draft often is — correct, but dense — so the seeded class shows it as the course's
confusion hotspot, and the designer's authored variants for it are what the Content Adapter
reaches for when a learner is confused there.
"""

from __future__ import annotations

from app.db.assessment_content_helpers import assessment, option, question
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

TITLE = "Python for Data Analysis"
FOUNDATIONS_MODULE = "Python Foundations for Data Work"


def build():
    return course(
        TITLE,
        "Go from Python basics to answering real questions with data. You will work with lists "
        "and dictionaries, write your own functions, then use NumPy and pandas to load, "
        "summarise and clean a real sales dataset.",
        "Use lists and dictionaries to hold data; write reusable functions; perform vectorised "
        "maths with NumPy; load, filter, group and aggregate tabular data with pandas; and "
        "decide how to handle missing values.",
        95,
        module(
            FOUNDATIONS_MODULE,
            "The core Python you need before touching a data library.",
            lesson(
                "Working with Collections",
                "Lists and dictionaries: the two containers every analysis starts from.",
                section(
                    "Lists: Ordered Collections", 7,
                    text(
                        "A list holds several values in order, inside square brackets. It is the "
                        "simplest way to keep a column of data together — a week of daily sales, "
                        "the names of your customers, the scores from a quiz.\n\n"
                        "Every item has a position called its index, and Python counts from zero: "
                        "the first item is at index 0, the second at index 1. A negative index "
                        "counts from the end, so -1 is always the last item.\n\n"
                        "Lists can change after you create them. You can add an item with "
                        "append(), change one by assigning to its index, and find out how many "
                        "items there are with len()."
                    ),
                    code(
                        "daily_sales = [120, 95, 143, 110, 188]\n\n"
                        "print(daily_sales[0])    # 120  (first day)\n"
                        "print(daily_sales[-1])   # 188  (last day)\n\n"
                        "daily_sales.append(162)  # a sixth day\n"
                        "print(len(daily_sales))  # 6\n"
                        "print(sum(daily_sales) / len(daily_sales))  # average: 136.33..."
                    ),
                    quiz(
                        "daily_sales = [120, 95, 143, 110, 188]. What does daily_sales[1] return?",
                        [("120", False), ("95", True), ("143", False), ("An IndexError", False)],
                        "Indexes start at 0, so index 1 is the SECOND item: 95.",
                    ),
                ),
                with_variants(
                    section(
                        "Dictionaries: Looking Things Up by Key", 8,
                        text(
                            "A dictionary stores pairs: a key and the value that belongs to it. "
                            "Instead of asking for the item at position 2, you ask for the value "
                            "stored under a name — the price of 'tea', the population of "
                            "'Kandy'.\n\n"
                            "Keys must be unique and are usually strings. Looking a key up is "
                            "fast no matter how large the dictionary is, which is why "
                            "dictionaries are everywhere in data work: counting how often "
                            "something happens, mapping codes to labels, or holding one row of a "
                            "table.\n\n"
                            "Asking for a key that does not exist raises a KeyError. The get() "
                            "method avoids that by returning a default instead."
                        ),
                        code(
                            "prices = {'tea': 350, 'coffee': 520, 'juice': 450}\n\n"
                            "print(prices['coffee'])        # 520\n"
                            "prices['water'] = 100          # add a new pair\n"
                            "print(prices.get('cake', 0))   # 0 -- no KeyError\n\n"
                            "for item, price in prices.items():\n"
                            "    print(item, price)"
                        ),
                        callout(
                            "Reach for a list when ORDER matters, and a dictionary when you need "
                            "to find things by NAME.",
                            variant="tip",
                        ),
                        quiz(
                            "prices = {'tea': 350, 'coffee': 520}. What does prices.get('cake', 0) "
                            "return?",
                            [("None", False), ("0", True), ("A KeyError", False), ("'cake'", False)],
                            "get() returns the default you pass when the key is missing — here 0.",
                        ),
                    ),
                    0,
                    simpler=(
                        "Think of a dictionary as a real dictionary. You look up a WORD (the key) "
                        "and read its MEANING (the value). You never read it page by page.\n\n"
                        "In Python: prices = {'tea': 350}. The word is 'tea', the meaning is "
                        "350. prices['tea'] looks it up and gives you 350.\n\n"
                        "If the word is not in the dictionary, prices['cake'] fails. "
                        "prices.get('cake', 0) says: 'look it up, and if it is not there, give "
                        "me 0 instead.'"
                    ),
                    alternative=(
                        "Picture the price board in a café. You do not ask for 'the third item' "
                        "— you find 'coffee' and read the number beside it. A dictionary works "
                        "the same way: each label (key) points to its value.\n\n"
                        "Adding a new drink to the board is prices['water'] = 100. Asking for a "
                        "drink the café does not sell is an error, unless you use "
                        "prices.get('cake', 0), which answers 0 instead of failing."
                    ),
                ),
            ),
            lesson(
                "Writing Reusable Functions",
                "Stop copying code: package a calculation once and call it everywhere.",
                section(
                    "Defining and Calling Functions", 8,
                    text(
                        "A function is a named, reusable piece of code. You define it once with "
                        "def, give it parameters for the values it needs, and return a result. "
                        "Then you call it as often as you like with different arguments.\n\n"
                        "Functions make analysis code shorter and safer. If the way you calculate "
                        "a discount changes, you fix it in one place instead of hunting through "
                        "every copy."
                    ),
                    code(
                        "def apply_discount(price, rate):\n"
                        "    \"\"\"Return the price after a percentage discount.\"\"\"\n"
                        "    return price * (1 - rate / 100)\n\n"
                        "print(apply_discount(1000, 10))   # 900.0\n"
                        "print(apply_discount(450, 25))    # 337.5"
                    ),
                    exercise(
                        "Write a function vat(amount) that returns the amount plus 18% VAT. "
                        "What does vat(200) return?",
                        "236.0",
                        "def vat(amount): return amount * 1.18 — so vat(200) is 236.0.",
                    ),
                ),
                section(
                    "Default Arguments and Return Values", 7,
                    text(
                        "A parameter can have a default value, used when the caller leaves it "
                        "out. Defaults keep the common case short while still allowing the "
                        "unusual one.\n\n"
                        "A function can also return more than one value by returning a tuple, "
                        "which the caller can unpack into separate variables. A function with no "
                        "return statement returns None — a frequent source of surprise when a "
                        "result seems to vanish."
                    ),
                    code(
                        "def summarise(values, decimals=2):\n"
                        "    total = sum(values)\n"
                        "    mean = round(total / len(values), decimals)\n"
                        "    return total, mean\n\n"
                        "total, mean = summarise([120, 95, 143])\n"
                        "print(total, mean)   # 358 119.33"
                    ),
                    quiz(
                        "A function has no return statement. What does calling it give back?",
                        [("0", False), ("An empty string", False), ("None", True),
                         ("The last value it computed", False)],
                        "Without return, every Python function returns None.",
                    ),
                ),
            ),
        ),
        module(
            "Analysing Data with NumPy and pandas",
            "Load a real dataset, then summarise and clean it.",
            lesson(
                "Arrays and DataFrames",
                "The two structures data analysis in Python is built on.",
                section(
                    "NumPy Arrays and Vectorised Maths", 9,
                    text(
                        "A NumPy array looks like a list but is built for numbers. Every element "
                        "has the same type and the array is stored compactly, so maths on a "
                        "million values is fast.\n\n"
                        "The key idea is vectorisation: an operation applies to every element at "
                        "once, with no loop. prices * 1.18 adds VAT to every price in one line, "
                        "and prices > 500 gives an array of True/False you can use to filter."
                    ),
                    code(
                        "import numpy as np\n\n"
                        "prices = np.array([350, 520, 450, 610])\n"
                        "print(prices * 1.18)        # VAT on every price\n"
                        "print(prices.mean())        # 482.5\n"
                        "print(prices[prices > 500]) # [520 610]"
                    ),
                    quiz(
                        "prices = np.array([350, 520, 450]). What is prices * 2?",
                        [("[350, 520, 450, 350, 520, 450]", False),
                         ("array([700, 1040, 900])", True),
                         ("A TypeError", False), ("2640", False)],
                        "Arithmetic on an array is element-wise. (Multiplying a LIST by 2 would "
                        "repeat it — one of the big differences between the two.)",
                    ),
                ),
                section(
                    "Your First pandas DataFrame", 10,
                    text(
                        "A DataFrame is a table: named columns, one row per record, like a "
                        "spreadsheet you control with code. Each column is a Series — a "
                        "labelled NumPy array.\n\n"
                        "You will usually create one by reading a file with pd.read_csv(). "
                        "head() shows the first rows, df['column'] selects a column, and a "
                        "condition inside square brackets keeps only the rows where it is True."
                    ),
                    code(
                        "import pandas as pd\n\n"
                        "sales = pd.read_csv('sales.csv')\n"
                        "print(sales.head())\n\n"
                        "print(sales['amount'].sum())\n"
                        "big = sales[sales['amount'] > 1000]   # rows over 1000\n"
                        "print(len(big))"
                    ),
                    callout(
                        "sales['amount'] > 1000 is a Series of True/False. Putting it inside "
                        "sales[...] keeps the True rows — the same filtering idea as NumPy.",
                        variant="info",
                    ),
                    quiz(
                        "Which expression keeps only the rows where region is 'West'?",
                        [("sales['region'] == 'West'", False),
                         ("sales[sales['region'] == 'West']", True),
                         ("sales.region('West')", False),
                         ("sales.filter('West')", False)],
                        "The comparison alone gives True/False values; wrapping it in sales[...] "
                        "uses them to select rows.",
                    ),
                ),
            ),
            lesson(
                "Summarising and Cleaning Data",
                "Answer questions per group, and deal with the gaps real data always has.",
                with_variants(
                    section(
                        "Grouping and Aggregating with groupby", 12,
                        text(
                            "groupby implements split-apply-combine: the DataFrame is split into "
                            "groups by the values of one or more key columns, an aggregation "
                            "function is applied independently to each group, and the results "
                            "are combined into a new object indexed by the group keys.\n\n"
                            "sales.groupby('region')['amount'].sum() therefore returns a Series "
                            "whose index is the distinct regions and whose values are each "
                            "region's total. Passing a list of keys produces a MultiIndex; "
                            "agg() accepts several functions, or a dict mapping columns to "
                            "functions, to compute multiple aggregates in one pass. Note that "
                            "the grouped object itself is lazy — nothing is computed until an "
                            "aggregation is called on it."
                        ),
                        code(
                            "by_region = sales.groupby('region')['amount'].sum()\n"
                            "print(by_region)\n"
                            "# region\n"
                            "# East     8450\n"
                            "# North    6120\n"
                            "# West    11230\n\n"
                            "summary = sales.groupby('region').agg(\n"
                            "    total=('amount', 'sum'),\n"
                            "    orders=('amount', 'count'),\n"
                            "    average=('amount', 'mean'),\n"
                            ")"
                        ),
                        table(
                            ["Step", "What happens", "In the example"],
                            [
                                ["Split", "Rows are grouped by the key column", "one group per region"],
                                ["Apply", "A function runs on each group", "sum() of amount"],
                                ["Combine", "Results form a new table", "one row per region"],
                            ],
                        ),
                        quiz(
                            "What does sales.groupby('region')['amount'].mean() return?",
                            [("The mean of the whole amount column", False),
                             ("One average amount per region", True),
                             ("The regions sorted by amount", False),
                             ("A DataFrame with the same rows as sales", False)],
                            "groupby splits by region, mean() runs on each group, and the result "
                            "has one value per region.",
                        ),
                        exercise(
                            "Write the expression that counts how many orders each region has.",
                            "sales.groupby('region')['amount'].count()",
                            "Any column works with count(); size() also counts rows per group.",
                        ),
                    ),
                    0,
                    simpler=(
                        "groupby answers questions like 'what is the total for EACH region?'. "
                        "It happens in three small steps.\n\n"
                        "1. Split: put the rows into piles, one pile per region.\n"
                        "2. Apply: add up the amounts in each pile.\n"
                        "3. Combine: write the answers in a small table, one line per region.\n\n"
                        "In pandas all three steps are one line: "
                        "sales.groupby('region')['amount'].sum(). Read it left to right: "
                        "group the sales by region, take the amount column, sum each group."
                    ),
                    alternative=(
                        "Imagine sorting a pile of receipts into envelopes, one envelope per "
                        "shop branch. Then you add up the receipts in each envelope and write "
                        "each total on the front. That is exactly what groupby does.\n\n"
                        "groupby('region') makes the envelopes, ['amount'] picks what is written "
                        "on each receipt, and .sum() adds up each envelope. Swap .sum() for "
                        ".mean() and you get the average receipt per branch instead."
                    ),
                    harder=(
                        "Beyond single aggregates: transform() returns a result aligned to the "
                        "ORIGINAL rows, so sales['share'] = sales['amount'] / "
                        "sales.groupby('region')['amount'].transform('sum') gives each order's "
                        "share of its region's total without a merge.\n\n"
                        "filter() drops whole groups — sales.groupby('region').filter(lambda g: "
                        "len(g) >= 50) keeps only regions with at least fifty orders. Try "
                        "combining both: which region's largest single order is the biggest "
                        "share of that region's total?"
                    ),
                ),
                section(
                    "Handling Missing Values", 9,
                    text(
                        "Real data has gaps. pandas marks a missing value as NaN, and most "
                        "calculations skip it — sum() and mean() quietly ignore NaN — which can "
                        "hide how much data is actually missing.\n\n"
                        "Start by measuring the problem with isna().sum(). Then choose: dropna() "
                        "removes incomplete rows, and fillna() replaces gaps with a value such as "
                        "0 or the column's median. Which is right depends on WHY the value is "
                        "missing, not on which line of code is shorter."
                    ),
                    code(
                        "print(sales.isna().sum())      # missing values per column\n\n"
                        "complete = sales.dropna(subset=['amount'])\n"
                        "sales['discount'] = sales['discount'].fillna(0)\n"
                        "median = sales['amount'].median()\n"
                        "sales['amount'] = sales['amount'].fillna(median)"
                    ),
                    callout(
                        "Filling a missing discount with 0 is reasonable — no discount was "
                        "given. Filling a missing SALE amount with 0 would invent a sale that "
                        "earned nothing.",
                        variant="warning",
                    ),
                    quiz(
                        "Which call shows how many values are missing in each column?",
                        [("sales.dropna()", False), ("sales.isna().sum()", True),
                         ("sales.fillna(0)", False), ("sales.count(NaN)", False)],
                        "isna() marks each missing cell True; sum() counts the Trues per column.",
                    ),
                ),
            ),
        ),
    )


def build_pre():
    """Pre-check on the foundations module: sets the learner's starting skill level."""
    return assessment(
        "Python Foundations — Pre-check",
        "pre",
        question(
            "What does [10, 20, 30][-1] return?",
            [option("10"), option("30", True), option("An IndexError"), option("-1")],
            pair_key="list_index", section_title="Lists: Ordered Collections",
            explanation="A negative index counts from the end; -1 is the last item.",
        ),
        question(
            "Which structure is best for looking up a product's price by its name?",
            [option("A list"), option("A dictionary", True), option("A string"),
             option("A tuple")],
            pair_key="dict_lookup", section_title="Dictionaries: Looking Things Up by Key",
            explanation="A dictionary maps a key (the name) to a value (the price).",
        ),
        question(
            "def f(x): x * 2   — what does f(3) return?",
            [option("6"), option("None", True), option("3"), option("An error")],
            pair_key="return_none", section_title="Default Arguments and Return Values",
            explanation="There is no return statement, so the function returns None.",
        ),
        question(
            "def greet(name, greeting='Hello'): ... — which call is valid?",
            [option("greet()"), option("greet('Ama')", True),
             option("greet(greeting='Hi')"), option("None of them")],
            pair_key="default_args", section_title="Default Arguments and Return Values",
            explanation="Only name is required; greeting falls back to its default.",
        ),
    )
