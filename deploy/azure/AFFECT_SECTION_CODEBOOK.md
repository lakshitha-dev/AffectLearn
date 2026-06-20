# Affect-Section Codebook — Pilot Courses

Maps each course section to the **affect state it is designed to elicit** for the study.
Section titles are intentionally topic-natural (not labelled "boring"/"confusing") so they
do **not** bias participants; this codebook is the analysis key. Source of truth:
`backend/app/db/seed_courses.py` (see the `# affect:` comments).

The four target states: **engaged**, **bored**, **confused**, **frustrated**.

## How each state is induced
- **Engaged** — clear, well-paced explanation, a relatable analogy, a Mermaid diagram, and an easy confidence-building quiz.
- **Bored** — long, dry, exhaustive prose (chronologies, taxonomies, field references); repetitive; no visuals; low cognitive challenge but tedious.
- **Confused** — dense jargon and formal notation introduced out of order, with symbols/terms used before they are defined; cognitive overload.
- **Frustrated** — a deceptively hard quiz/exercise that depends on the preceding (confusing) material, with tricky distractors and unforgiving numbers.

## Course 1 — Foundations of Agentic AI
| Lesson | Section | Intended affect |
|---|---|---|
| What Makes AI 'Agentic' | The Agent Loop | **engaged** |
| What Makes AI 'Agentic' | A Brief History of Autonomous Systems | **bored** |
| Inside an Agent | Formal Foundations: MDPs and Policies | **confused** |
| Inside an Agent | Check Your Understanding | **frustrated** |

## Course 2 — Building AI Agents: Tools, Memory & Planning
| Lesson | Section | Intended affect |
|---|---|---|
| Giving Agents Hands and Memory | Tool Use & Function Calling | **engaged** |
| Giving Agents Hands and Memory | A Catalogue of Memory Types | **bored** |
| Planning & Reasoning | ReAct, Reflexion, and the Reasoning Zoo | **confused** |
| Planning & Reasoning | Trace the Reasoning (Exercise) | **frustrated** |

## Course 3 — Multi-Agent Systems & Orchestration
| Lesson | Section | Intended affect |
|---|---|---|
| Coordinating Multiple Agents | Why Use More Than One Agent? | **engaged** |
| Coordinating Multiple Agents | Message-Passing Field Reference | **bored** |
| Reliability & Evaluation | Consensus, Byzantine Faults & Guarantees | **confused** |
| Reliability & Evaluation | Diagnose the Failure (Exercise) | **frustrated** |

## Notes for analysis
- Each course traverses all four states, so a single session yields a balanced affect spread.
- The intended affect is the **design hypothesis**, not ground truth — the actual affect is what the facial/behavioral models + self-reports record per section (`research_events`, `section_progress.affect_states`).
- To join captured affect to intended affect, match `section_progress.section_id` (or research-event section context) to the section titles above.
