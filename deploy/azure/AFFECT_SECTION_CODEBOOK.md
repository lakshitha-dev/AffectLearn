# Affect-Section Codebook — Pilot Courses

Maps each course section to the affect state it is designed to elicit. Section titles are
topic-natural so they do NOT bias participants; this codebook is the analysis key. Source of
truth: `backend/app/db/course_content/*.py` (see the `# affect:` comments). States: **engaged /
bored / confused / frustrated**, plus **neutral (baseline)** for the warm-up.

> **Pilot scope (live):** every participant takes the **same single study course — *Building AI
> Agents* — after the neutral warm-up baseline.** *Foundations of Agentic AI* and *Multi-Agent
> Systems & Orchestration* are **retired from the pilot** (kept in source, not seeded); their tables
> below are retained for reference only.

## Getting Comfortable: A Warm-Up  (baseline task — do FIRST)
Every participant completes this short, calm course **before** the study courses. It targets no
affect; its behavioral windows are the participant's **resting baseline** for per-person
normalization (see *Analysis notes → Baseline* below).
| Lesson | Section | Intended affect |
|---|---|---|
| Getting Comfortable | Welcome — Read at Your Own Pace | neutral (baseline) |
| Getting Comfortable | A Short, Easy Read | neutral (baseline) |

## Foundations of Agentic AI
| Lesson | Section | Intended affect |
|---|---|---|
| What Makes Software 'Agentic' | From Programs to Agents | **engaged** |
| What Makes Software 'Agentic' | The Reasoning Core: LLMs as the Brain | **engaged** |
| What Makes Software 'Agentic' | The Four Parts of an Agent | **engaged** |
| The Agent Loop | The Perceive-Reason-Act-Observe Loop | **engaged** |
| The Agent Loop | Levels of Autonomy | **engaged** |
| The Agent Loop | Where Agents Spend Their Effort | **engaged** |
| A Worked Example: The Support Agent | Tracing a Refund Request | **engaged** |
| A Worked Example: The Support Agent | A Field Guide: Agent, Chatbot, Assistant, and Workflow | **bored** |
| How Agents Reason: The ReAct Pattern | Reasoning and Acting Together | **engaged** |
| How Agents Reason: The ReAct Pattern | The Vocabulary: State, Observation, Action, Environment | **engaged** |
| How Agents Reason: The ReAct Pattern | The Anatomy of a Tool Definition | **bored** |
| Formal Foundations | The Sequential Decision Framework | **confused** |
| Formal Foundations | Optimality Operators and Their Consequences | **confused** |
| Where Agents Break | A Taxonomy of Failure Modes | **bored** |
| Where Agents Break | Diagnostic Assessment: Formalism and Failure | **frustrated** |

## Building AI Agents: Tools, Memory & Planning
| Lesson | Section | Intended affect |
|---|---|---|
| Tool Use & Function Calling | What a Tool Is and Why an Agent Needs One | **engaged** |
| Tool Use & Function Calling | Anatomy of a Tool Schema | **engaged** |
| Tool Use & Function Calling | The Tool-Call Round Trip | **engaged** |
| Tool Use & Function Calling | When (and When Not) to Give an Agent a Tool | **engaged** |
| Structured Output | Why Free Text Breaks Programs | **engaged** |
| Structured Output | Schema Edge Cases That Bite | **frustrated** |
| Structured Output | Constrained Decoding and Grammars | **confused** |
| Agent Memory | A Catalogue of Memory Types | **bored** |
| Agent Memory | Chunking and Retention Strategies | **bored** |
| Agent Memory | Short-Term vs Long-Term Memory in Practice | **engaged** |
| Planning & Reasoning Patterns | Planning and Task Decomposition | **engaged** |
| Planning & Reasoning Patterns | The ReAct Loop | **engaged** |
| Planning & Reasoning Patterns | The Reasoning-Pattern Zoo | **confused** |
| Planning & Reasoning Patterns | Which Pattern Fits? A Tricky Case | **frustrated** |
| Retrieval-Augmented Generation & Embeddings | The RAG Pipeline | **engaged** |
| Retrieval-Augmented Generation & Embeddings | Embeddings, Cosine Similarity & the Curse of Dimensionality | **confused** |
| Retrieval-Augmented Generation & Embeddings | Design and Trace the Agent | **frustrated** |

## Multi-Agent Systems & Orchestration
| Lesson | Section | Intended affect |
|---|---|---|
| From One Agent to Many | Why More Than One Agent? A Newsroom Analogy | **engaged** |
| From One Agent to Many | The Orchestrator-Worker Pattern | **engaged** |
| Roles, Specialisation, and Talking Between Agents | Roles and Specialisation | **engaged** |
| Roles, Specialisation, and Talking Between Agents | Message Envelope Field Reference | **bored** |
| Coordination Patterns | Sharing State: Blackboards and Message Queues | **engaged** |
| Coordination Patterns | When Agents Fail: Retries, Timeouts, and Idempotency | **engaged** |
| Coordination Patterns | Sequential, Parallel, and Hierarchical Coordination | **engaged** |
| Consensus and Byzantine Fault Tolerance | Consensus, FLP Impossibility, and Quorums | **confused** |
| Consensus and Byzantine Fault Tolerance | Byzantine Fault Tolerance and the n >= 3f + 1 Bound | **confused** |
| Consensus and Byzantine Fault Tolerance | Leader Election, Terms, and Split-Brain | **confused** |
| Consensus and Byzantine Fault Tolerance | Consensus in Practice: Choosing Your Guarantees | **engaged** |
| Consensus and Byzantine Fault Tolerance | Fault-Tolerance Diagnosis: A Demanding Assessment | **frustrated** |
| Evaluation and Safety | Evaluating Agent Systems: Four Dimensions | **engaged** |
| Evaluation and Safety | Glossary of Evaluation Metrics | **bored** |
| Evaluation and Safety | Reward Hacking, Specification Gaming, and Safety | **engaged** |
| Evaluation and Safety | Keeping Humans in the Loop | **engaged** |

---

# Analysis notes (Phase 1 validity controls)

These record the design decisions that let the fixed course order and per-person signal
differences be handled at analysis time rather than by scrambling the (now pedagogically
dependent) content.

## Serial position & fatigue — statistical control (choice #1A)
Section order is **fixed** (the deep content has real dependencies — e.g. a *frustrated*
assessment builds on the preceding *confused* material). Rather than counterbalance the order
and break coherence, treat **serial position** and **elapsed time** as covariates in the affect
models. Both are already recoverable from the durable data — no schema change:

- **Serial position (per participant):** order `section_progress` rows by `completed_at` per
  `user_id`/`enrollment_id` and rank; or use the canonical sequence (course→module `sort_order`
  → lesson `sort_order` → section `sort_order`). For event-level work, `research_events`
  `sequence_number` is monotonic per `session_id`.
- **Elapsed time / fatigue (per participant):** `research_events.timestamp` (unix ms) −
  the session's first event timestamp; or `section_progress.completed_at` − the participant's
  first completion. `section_progress.time_spent_seconds` gives time-on-section.
- **Affect target join:** join each section to its intended affect via this codebook (by title).

Recommended modelling: include serial-position rank and elapsed-minutes (and optionally
time-on-section) as fixed-effect covariates, with a per-participant random intercept, when
relating behavioral/facial signals to the intended affect. This removes the position/fatigue
confound analytically.

## Per-participant baseline (choice #2A)
The **warm-up course** (top of this codebook) is a neutral reading task completed first. Its
behavioral windows are each participant's **resting baseline**; normalize study-phase signals
per person against it (e.g. z-score or subtract baseline mean per feature) so individual
differences don't dominate raw signals.

- **Procedure:** assign/instruct participants to complete *Getting Comfortable: A Warm-Up*
  before any study course.
- **Identifying baseline windows:** the warm-up's two `section_progress` rows bound the baseline
  interval per participant (`completed_at` of its sections); behavioral `research_events` within
  that interval (before the first study-course section completes) are the baseline set. As the
  warm-up is done first, these are also the session's opening windows.

## Quiz answer timing (choice #4 — implemented)
Every gated quiz records time-to-answer. The `quiz_submitted` research event payload carries
`response_time_ms`, `section_id`, `is_correct`, and the selected answers — a
deliberation/frustration probe joinable to the section's intended affect via this codebook.

## Manipulation design (applied pre-pilot)
The elicitation is strengthened structurally so the affect labels come through cleaner:

- **Bored** sections are pure low-stimulation text — all diagrams and interactive blocks
  (quizzes, exercises, reflections) were stripped (boredom = monotony + no payoff).
- **Confused** sections each carry a genuine, *resolvable* contradiction (an apparent paradox
  the section — or the next one — reconciles): confusion via cognitive disequilibrium, kept
  productive by guaranteeing a resolution path.
- **Frustrated** sections keep their gated, tricky-distractor quizzes (solvable-but-hard).
- **Engaged** sections keep diagram + analogy + a fair quiz with immediate feedback.
- **Self-report reactivity:** ~20% of due prompts are randomly omitted and logged as
  `self_report {omitted:true}` — compare behavioral windows after a shown vs an omitted prompt
  to estimate the prompt's own (Hawthorne/reactivity) effect.
- **Consent / debrief:** consent warns the material "may feel clear, slow or tedious, or
  challenging or confusing" *without naming the manipulation* (avoids demand characteristics);
  the end-of-study screen debriefs that the study measured emotion during learning (not the
  participant) and that difficulty was by design.
- **Label hygiene (post course-review):** "Reward Hacking, Specification Gaming, and Safety"
  was relabeled confused→**engaged** (it reads as advanced example-driven narrative, not the
  notation-overload of the true confused sections). An engaged synthesis section — "Consensus
  in Practice: Choosing Your Guarantees" — was **inserted before** the Multi-Agent frustrated
  assessment so the three back-to-back confused sections (FLP/BFT/leader-election) don't bleed
  into it (Baker's confused→frustrated cascade), keeping the frustrated label clean.
