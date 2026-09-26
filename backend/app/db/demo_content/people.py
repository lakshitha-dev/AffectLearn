"""The demo accounts: one designer, one learner, and the class around them.

Every address is on `DEMO_DOMAIN`, which is not a real mailbox, and every account is flagged
`is_demo`. Only the designer and the learner can log in; the background class exists to give the
designer's analytics a realistic cohort (every figure needs at least five learners) and is given
passwords nobody knows.
"""

from __future__ import annotations

from dataclasses import dataclass

DEMO_DOMAIN = "demo.affectlearn.io"

DESIGNER = {
    "email_address": f"anjali.jayasinghe@{DEMO_DOMAIN}",
    "first_name": "Anjali",
    "last_name": "Jayasinghe",
}

LEARNER = {
    "email_address": f"nimali.perera@{DEMO_DOMAIN}",
    "first_name": "Nimali",
    "last_name": "Perera",
    "age_range": "21-23",
    "degree_program": "BSc (Hons) Software Engineering",
}

#: The demo learner's baseline questionnaire (keys and values from
#: `frontend/src/components/onboarding/questionnaire-questions.ts`). A second-year student who
#: studies online several times a week, prefers hands-on practice, and — by her own account —
#: gets confused more often than bored.
LEARNER_QUESTIONNAIRE = {
    "Q1": "21-23",
    "Q2": "female",
    "Q3": "several_per_week",
    "Q4": "3-5",
    "Q5": "1-2",
    "Q6": "4",
    "Q7": "interactive",
    "Q8": {"boredom": "3", "confusion": "4", "frustration": "2", "engagement": "4"},
    "Q9": ["search_alternatives", "take_break"],
    "Q10": "yes_once_twice",
    "Q11": "4",
    "Q12": "4",
    "Q13": "3",
    "Q14": "3",
}


@dataclass(frozen=True)
class Classmate:
    first: str
    last: str
    degree: str
    age: str
    #: low | intermediate | advanced — drives affect, pace and quiz accuracy.
    level: str
    #: adaptive | control. Control learners are never shown help, as in the real study.
    group: str
    #: Share of each course completed; None = not enrolled.
    web: float | None
    python: float | None

    @property
    def email(self) -> str:
        return f"{self.first.lower()}.{self.last.lower()}@{DEMO_DOMAIN}"


CLASS: tuple[Classmate, ...] = (
    Classmate("Kavindu", "Fernando", "BSc Computer Science", "21-23", "advanced", "adaptive", 1.0, 1.0),
    Classmate("Tharushi", "Silva", "BSc Information Systems", "21-23", "intermediate", "control", 1.0, 0.875),
    Classmate("Ravindu", "Jayawardena", "BSc Software Engineering", "24-26", "low", "adaptive", 0.67, 0.5),
    Classmate("Sachini", "Wickramasinghe", "BSc Data Science", "21-23", "advanced", "control", 1.0, 1.0),
    Classmate("Dinuka", "Rathnayake", "HND in Computing", "18-20", "low", "adaptive", 0.5, 0.25),
    Classmate("Ishara", "Gunawardena", "BSc Computer Science", "21-23", "intermediate", "control", 0.83, 0.625),
    Classmate("Chamod", "Bandara", "BSc Software Engineering", "21-23", "intermediate", "adaptive", 1.0, 0.875),
    Classmate("Hiruni", "Dissanayake", "BSc Information Technology", "18-20", "intermediate", "control", 0.67, None),
    Classmate("Amaya", "Karunaratne", "MSc Information Technology", "27+", "advanced", "adaptive", 1.0, 0.875),
    Classmate("Yasiru", "Herath", "BSc Computer Engineering", "21-23", "low", "control", 0.5, None),
    Classmate("Nethmi", "Abeysekara", "BSc Data Science", "21-23", "intermediate", "adaptive", 0.83, 0.625),
    Classmate("Pasindu", "Weerasinghe", "BSc Software Engineering", "24-26", "advanced", "control", 1.0, 1.0),
)
