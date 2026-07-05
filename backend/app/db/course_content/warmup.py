"""Neutral warm-up course — the per-participant BASELINE task (#2).

Every participant completes this short, calm, low-stakes course FIRST. Its purpose is
NOT to teach or to elicit any affect — it is a neutral reading task so the platform can
record each learner's resting behavioral baseline (mouse/scroll/typing/idle rhythms).
Signals from the rest of the study are then normalized per-person against this baseline,
which the research shows matters because individual differences dominate raw signals.

Design notes (keep it neutral):
- Calm, easy, familiar content; no hard concepts, no dense notation.
- NO quizzes (so there is no gating friction / evaluation pressure that would perturb the baseline).
- Short (~3 min). Sections are affect-neutral (no engaged/bored/confused/frustrated targeting).
"""

from __future__ import annotations

from app.db.course_content_helpers import callout, course, lesson, module, section, text

WARMUP_TITLE = "Getting Comfortable: A Warm-Up"


def build():
    return course(
        WARMUP_TITLE,
        "A short, relaxed warm-up before the main courses — no test, nothing to memorise. "
        "It just helps you settle in.",
        "Get familiar with how lessons work and settle into a comfortable reading pace.",
        4,  # ~3-4 min
        module(
            "Warm-Up",
            "Settle in and get comfortable.",
            lesson(
                "Getting Comfortable",
                "A relaxed start — read at your own pace.",
                # affect: neutral (baseline)
                section(
                    "Welcome — Read at Your Own Pace", 2,
                    text(
                        "Welcome, and thanks for taking part. Before the main material, here is a "
                        "short, relaxed warm-up. There is nothing to memorise here and no quiz — "
                        "just read at whatever pace feels natural to you.\n\n"
                        "Each lesson shows one section at a time. When you have finished reading a "
                        "section, click the button at the bottom to continue to the next one. You can "
                        "always go back with the Previous button. That is all there is to it.\n\n"
                        "Take a moment to get comfortable — adjust your seat, your screen, and your "
                        "reading pace. When you are ready, continue to the next section."
                    ),
                    callout(
                        "There are no right or wrong answers in this warm-up. Just read naturally.",
                        variant="tip",
                    ),
                ),
                # affect: neutral (baseline)
                section(
                    "A Short, Easy Read", 2,
                    text(
                        "Here is a brief, everyday passage to ease you in.\n\n"
                        "Learning something new is a bit like taking a walk in an unfamiliar "
                        "neighbourhood. At first you notice the big landmarks — a park, a tall "
                        "building, a busy street. On your second visit, the smaller details start to "
                        "join up: which corner has the quiet cafe, which lane is a useful shortcut. "
                        "Nothing about the neighbourhood changed; you simply built a clearer map of "
                        "it in your head.\n\n"
                        "The courses ahead work the same way. You will meet a few big ideas first, "
                        "then fill in the details as you go. Some parts will feel easy and some will "
                        "take a little more thought — both are a normal part of learning. There is no "
                        "need to rush.\n\n"
                        "When you are ready, continue — the first course begins next."
                    ),
                ),
            ),
        ),
    )
