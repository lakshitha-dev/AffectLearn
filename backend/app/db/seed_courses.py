"""Seed real course content for the AffectLearn pilot study.

Three courses on **Agentic AI**. Each course has TWO modules; every module is built
so a learner passes through content deliberately designed to elicit the four target
affect states the study collects (engaged / bored / confused / frustrated). Section
titles stay topic-natural so they do NOT bias participants; the intended affect per
section is documented in `deploy/azure/AFFECT_SECTION_CODEBOOK.md` and in the
`# affect:` comments below.

Diagrams/charts use Mermaid: authored as `code` blocks with language "mermaid",
rendered by `frontend/.../MermaidDiagram.tsx`.

Idempotent by title. Re-run with reset to replace existing seeded courses:
    python -m app.db.seed_courses           # insert if missing
    python -m app.db.seed_courses --reset   # delete these courses (cascade) then re-insert
"""

import asyncio
import sys
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.course import (
    BlockType,
    ContentBlock,
    Course,
    Lesson,
    Module,
    Section,
)

T = BlockType.text
C = BlockType.code      # language "mermaid" => rendered as a diagram/chart
K = BlockType.callout
Q = BlockType.quiz
E = BlockType.exercise


def _blocks(*specs) -> list[ContentBlock]:
    out = []
    for i, (btype, content) in enumerate(specs):
        out.append(
            ContentBlock(
                block_type=btype,
                content=content,
                sort_order=i,
                variant_key="original",
                variant_group=uuid.uuid4(),
            )
        )
    return out


def _section(title, order, duration, *block_specs) -> Section:
    return Section(
        title=title,
        sort_order=order,
        estimated_duration_minutes=duration,
        content_blocks=_blocks(*block_specs),
    )


def _mermaid(code: str):
    return (C, {"language": "mermaid", "code": code})


# Reusable affect-eliciting section builders -----------------------------------
# Each takes a topic so the same "shape" can be reused across courses without the
# titles ever revealing the intended affect.

def _engaged(title, order, intro, diagram, tip, quiz):
    return _section(title, order, 6,
                    (T, {"text": intro}),
                    _mermaid(diagram),
                    (K, {"variant": "tip", "text": tip}),
                    (Q, quiz))


def _bored(title, order, p1, p2, p3):
    return _section(title, order, 9,
                    (T, {"text": p1}), (T, {"text": p2}), (T, {"text": p3}))


def _confused(title, order, p1, p2, note):
    return _section(title, order, 8,
                    (T, {"text": p1}), (T, {"text": p2}),
                    (K, {"variant": "info", "text": note}))


def _frustrated(title, order, lead, quiz, exercise):
    return _section(title, order, 7,
                    (T, {"text": lead}), (Q, quiz), (E, exercise))


# ======================================================================
# COURSE 1 — Foundations of Agentic AI
# ======================================================================
def _course_foundations() -> Course:
    return Course(
        title="Foundations of Agentic AI",
        description=(
            "What turns a language model into an agent? The perceive–reason–act loop, "
            "the ideas underneath autonomous behaviour, and what agents look like in the wild."
        ),
        estimated_duration_minutes=70,
        is_published=True,
        learning_objectives=(
            "Explain what makes an AI system 'agentic'; describe the agent loop; recognise "
            "the formal vocabulary behind agent behaviour; reason about real-world agents and "
            "their failure modes."
        ),
        modules=[
            Module(
                title="Understanding AI Agents",
                description="From a single model call to a system that acts on its own.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="What Makes AI 'Agentic'",
                        description="The core loop that separates an agent from a chatbot.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "The Agent Loop", 0,
                                ("A chatbot answers once and stops. An agent keeps going: it looks "
                                 "at the situation, decides what to do, does it, then looks again to "
                                 "see what changed. That cycle is what makes a system feel like it is "
                                 "*acting* rather than just *replying*.\n\n"
                                 "Think of a thermostat with ambition: it reads the temperature, "
                                 "decides to turn on the heater, runs it, and checks whether the room "
                                 "actually warmed up — adjusting if not."),
                                ("flowchart LR\n"
                                 "    A[Perceive\\nread the environment] --> B[Reason\\ndecide what to do]\n"
                                 "    B --> C[Act\\ntake an action]\n"
                                 "    C --> D[Observe\\nsee what changed]\n"
                                 "    D --> A\n"),
                                ("Whenever you meet a new agent design, find these four steps. If you "
                                 "can point to perceive, reason, act, and observe, you understand its skeleton."),
                                {
                                    "question": "What most clearly separates an agent from a plain chatbot?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "It uses a bigger model", "isCorrect": False},
                                        {"id": "b", "text": "It loops: it acts, observes the result, and continues", "isCorrect": True},
                                        {"id": "c", "text": "It always replies in JSON", "isCorrect": False},
                                        {"id": "d", "text": "It never makes mistakes", "isCorrect": False},
                                    ],
                                    "explanation": "The defining feature is the act–observe loop, not model size or output format.",
                                }),
                            # affect: BORED
                            _bored(
                                "A Brief History of Autonomous Systems", 1,
                                ("The idea of machines that act on their own is older than computing "
                                 "itself. This section lists the milestones in order. Read each one in full.\n\n"
                                 "In 1948, Norbert Wiener published his work on cybernetics. In 1950, Alan "
                                 "Turing proposed his imitation game. In 1956, the Dartmouth workshop coined "
                                 "the term artificial intelligence. In 1966, ELIZA simulated a conversation. "
                                 "In 1969, the robot Shakey combined perception and planning. In 1972, PROLOG "
                                 "was released. In 1979, the Stanford Cart crossed a room avoiding chairs."),
                                ("The list continues. In 1980, expert systems entered commercial use. In "
                                 "1986, the subsumption architecture was proposed. In 1992, temporal-difference "
                                 "learning was formalised. In 1997, a chess program defeated a world champion. "
                                 "In 2002, a robotic vacuum reached homes. In 2011, a question-answering system "
                                 "won a quiz show. In 2016, a Go program beat a top professional. In 2017, the "
                                 "transformer architecture was published. Re-read both paragraphs and make sure "
                                 "every year and event is firmly memorised before continuing."),
                                ("To summarise once more for completeness: cybernetics, imitation game, "
                                 "Dartmouth, ELIZA, Shakey, PROLOG, Stanford Cart, expert systems, subsumption, "
                                 "temporal-difference learning, chess, vacuum, quiz show, Go, transformer. The "
                                 "ordering is strictly chronological with no exceptions to note.")),
                        ],
                    ),
                    Lesson(
                        title="Inside an Agent",
                        description="The formal vocabulary behind agent behaviour.",
                        sort_order=1,
                        sections=[
                            # affect: CONFUSED
                            _confused(
                                "Formal Foundations: MDPs and Policies", 0,
                                ("Agent behaviour is formalised as a Markov Decision Process, the tuple "
                                 "(S, A, P, R, gamma). The policy pi: S -> Delta(A) induces a value function "
                                 "V^pi(s) = E_pi[ sum_t gamma^t R(s_t, a_t) | s_0 = s ], and the Bellman "
                                 "optimality operator T* satisfies T*V = max_a [ R + gamma P V ], whose fixed "
                                 "point V* is unique by the contraction property under the sup-norm since gamma < 1."),
                                ("Recall Q^pi(s,a) = R(s,a) + gamma sum_{s'} P(s'|s,a) V^pi(s'), and note pi "
                                 "is greedy w.r.t. Q iff optimal, by the policy improvement theorem (assumed). "
                                 "The advantage A^pi = Q^pi - V^pi closes the loop given the occupancy measure "
                                 "rho_pi defined earlier (it was not); partial observability replaces S with "
                                 "belief states b in Delta(S), yielding a POMDP whose belief MDP is solved by "
                                 "the same operator, modulo measurability."),
                                ("If the symbols arrived faster than the definitions, that is expected — "
                                 "note where you lost the thread.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Check Your Understanding", 1,
                                "Use only what was given in the previous section. Do not look anything up.",
                                {
                                    "question": "With gamma = 1 (not < 1) and the definitions above, T* is still guaranteed a unique fixed point.",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "True — uniqueness always holds", "isCorrect": False},
                                        {"id": "b", "text": "False — the contraction argument relied on gamma < 1", "isCorrect": True},
                                        {"id": "c", "text": "True, but only for POMDPs", "isCorrect": False},
                                        {"id": "d", "text": "It depends on rho_pi", "isCorrect": False},
                                    ],
                                    "explanation": "Uniqueness came from T* being a contraction under the sup-norm, which needed gamma < 1.",
                                },
                                {
                                    "prompt": "In one line, relate A^pi(s,a), Q^pi(s,a) and V^pi(s) using only the previous section.",
                                    "answer": "A^pi(s,a) = Q^pi(s,a) - V^pi(s)",
                                    "type": "text",
                                    "explanation": "The advantage is the action value minus the state value.",
                                }),
                        ],
                    ),
                ],
            ),
            Module(
                title="Agents in the Real World",
                description="What agents look like in practice — and where they break.",
                sort_order=1,
                lessons=[
                    Lesson(
                        title="From Theory to Practice",
                        description="A concrete agent, and the hard part underneath it.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "A Day in the Life of an Agent", 0,
                                ("Imagine a customer-support agent. A user writes 'my order never arrived'. "
                                 "The agent looks up the order, sees it is stuck in transit, decides to issue "
                                 "a refund and notify the courier, does both, then confirms with the user. "
                                 "Same four steps — perceive, reason, act, observe — now doing real work."),
                                ("sequenceDiagram\n"
                                 "    participant U as User\n"
                                 "    participant A as Support Agent\n"
                                 "    participant DB as Orders DB\n"
                                 "    U->>A: My order never arrived\n"
                                 "    A->>DB: lookup_order(user)\n"
                                 "    DB-->>A: status: stuck_in_transit\n"
                                 "    A->>A: decide: refund + notify courier\n"
                                 "    A-->>U: Refund issued, courier alerted\n"),
                                ("Notice the agent did several actions in one turn. Real agents often take "
                                 "multiple steps before they reply."),
                                {
                                    "question": "In the example, what played the role of 'Act'?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Reading the user's message", "isCorrect": False},
                                        {"id": "b", "text": "Issuing the refund and notifying the courier", "isCorrect": True},
                                        {"id": "c", "text": "Deciding what to do", "isCorrect": False},
                                    ],
                                    "explanation": "Issuing the refund and alerting the courier are the actions taken on the world.",
                                }),
                            # affect: CONFUSED
                            _confused(
                                "Partial Observability & Belief States", 1,
                                ("Real agents rarely see the full state, so the MDP becomes a POMDP "
                                 "(S, A, O, P, Z, R, gamma) where Z(o|s',a) is the observation model and the "
                                 "agent maintains a belief b in Delta(S) updated by the Bayes filter "
                                 "b'(s') ∝ Z(o|s',a) sum_s P(s'|s,a) b(s); the value function is then "
                                 "piecewise-linear-and-convex over the belief simplex, represented by alpha-vectors."),
                                ("Point-based solvers (PBVI, SARSOP) back up alpha-vectors at sampled beliefs, "
                                 "the curse of dimensionality is in |S| for the belief and |O|^horizon for the "
                                 "reachable tree, and finite-state controllers trade optimality for bounded memory; "
                                 "none of this was needed in the fully-observed case, which is why it is introduced "
                                 "abruptly here."),
                                ("If 'alpha-vectors over the belief simplex' meant nothing yet, that is the point "
                                 "to flag.")),
                        ],
                    ),
                    Lesson(
                        title="Limits & Risks",
                        description="How agents fail, and a test of the details.",
                        sort_order=1,
                        sections=[
                            # affect: BORED
                            _bored(
                                "A Taxonomy of Failure Modes", 0,
                                ("Agents fail in many ways. This section enumerates them. Read each entry.\n\n"
                                 "Hallucination: confidently stating false facts. Loop: repeating the same "
                                 "action forever. Tool misuse: calling a tool with wrong arguments. Goal drift: "
                                 "losing track of the objective. Over-refusal: declining valid requests. "
                                 "Sycophancy: agreeing regardless of correctness. Context overflow: exceeding "
                                 "the window. Stale memory: acting on outdated facts."),
                                ("Continuing: premature stopping, infinite planning, cost blowup, prompt "
                                 "injection, data leakage, unsafe action, partial completion, silent failure, "
                                 "cascading error, deadlock between agents, livelock, priority inversion, and "
                                 "starvation. Each may co-occur with any other, and the combinations are not "
                                 "enumerated here."),
                                ("Restated for completeness: hallucination, loop, tool misuse, goal drift, "
                                 "over-refusal, sycophancy, context overflow, stale memory, premature stopping, "
                                 "infinite planning, cost blowup, prompt injection, data leakage, unsafe action, "
                                 "partial completion, silent failure, cascading error, deadlock, livelock, "
                                 "priority inversion, starvation.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Spot the Failure (Exercise)", 1,
                                "Use only the taxonomy above. The categories are deliberately close.",
                                {
                                    "question": "An agent keeps calling the same search tool with identical args and never stops. Which is the BEST single label?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Hallucination", "isCorrect": False},
                                        {"id": "b", "text": "Loop", "isCorrect": True},
                                        {"id": "c", "text": "Tool misuse", "isCorrect": False},
                                        {"id": "d", "text": "Goal drift", "isCorrect": False},
                                    ],
                                    "explanation": "Repeating the same action forever is the 'loop' failure; the args are valid, so it is not tool misuse.",
                                },
                                {
                                    "prompt": "Name the failure: an agent reveals another user's data in its answer. (One term from the taxonomy.)",
                                    "answer": "data leakage",
                                    "type": "text",
                                    "explanation": "Exposing data that should stay private is 'data leakage'.",
                                }),
                        ],
                    ),
                ],
            ),
        ],
    )


# ======================================================================
# COURSE 2 — Building AI Agents: Tools, Memory & Planning
# ======================================================================
def _course_building() -> Course:
    return Course(
        title="Building AI Agents: Tools, Memory & Planning",
        description=(
            "Agents become useful when they can call tools, remember things, plan ahead, and "
            "ground answers in real knowledge. How function calling, memory, reasoning, and "
            "retrieval fit together."
        ),
        estimated_duration_minutes=75,
        is_published=True,
        learning_objectives=(
            "Describe how agents call tools; distinguish memory types; recognise reasoning "
            "patterns such as ReAct; explain retrieval-augmented generation and where it fails."
        ),
        modules=[
            Module(
                title="Agent Capabilities",
                description="Hands, memory, and a plan.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="Giving Agents Hands and Memory",
                        description="Tools let agents act; memory lets them carry context.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "Tool Use & Function Calling", 0,
                                ("On its own, a language model can only produce text. Give it tools and it "
                                 "can check the weather, query a database, or send an email. The model does "
                                 "not run the tool — it asks for it by name, your code runs it, and the result "
                                 "is handed back so the model can continue."),
                                ("sequenceDiagram\n"
                                 "    participant U as User\n"
                                 "    participant A as Agent (LLM)\n"
                                 "    participant Tl as Tool: get_weather\n"
                                 "    U->>A: Will it rain in Colombo today?\n"
                                 "    A->>Tl: get_weather(city=\"Colombo\")\n"
                                 "    Tl-->>A: {rain: true, temp: 29}\n"
                                 "    A-->>U: Yes — rain likely, around 29 C.\n"),
                                ("A tool is just a function plus a clear description. The description is the "
                                 "part the model reads — write it like a helpful docstring."),
                                {
                                    "question": "When an agent 'calls a tool', what actually happens?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "The model executes the code internally", "isCorrect": False},
                                        {"id": "b", "text": "The model requests it by name; your code runs it and returns the result", "isCorrect": True},
                                        {"id": "c", "text": "The user runs the tool manually each time", "isCorrect": False},
                                    ],
                                    "explanation": "The model emits a structured request; the surrounding program executes it and feeds the result back.",
                                }),
                            # affect: BORED
                            _bored(
                                "A Catalogue of Memory Types", 1,
                                ("Agent memory can be categorised many ways. This section enumerates them. "
                                 "Read each definition fully.\n\n"
                                 "Short-term memory holds the current conversation. Working memory holds "
                                 "intermediate results. Episodic memory holds past interactions. Semantic "
                                 "memory holds facts. Procedural memory holds learned routines. Sensory memory "
                                 "holds raw recent input. Buffer memory holds the last N messages. Summary "
                                 "memory holds a condensed history. Vector memory holds embeddings. Entity "
                                 "memory holds facts about specific entities."),
                                ("Continuing: persistent memory survives restarts; volatile memory does not. "
                                 "Shared memory is visible to multiple agents; private memory is not. Read-only "
                                 "memory cannot be written; read-write memory can. Indexed memory supports "
                                 "search; flat memory does not. Compressed memory trades fidelity for size; "
                                 "verbatim does not. Time-stamped memory records when; untimed does not. Each "
                                 "category may combine with each other category."),
                                ("Restated: short-term, working, episodic, semantic, procedural, sensory, "
                                 "buffer, summary, vector, entity, persistent, volatile, shared, private, "
                                 "read-only, read-write, indexed, flat, compressed, verbatim, time-stamped, "
                                 "untimed. The list is exhaustive for this section.")),
                        ],
                    ),
                    Lesson(
                        title="Planning & Reasoning",
                        description="How agents decide what to do over many steps.",
                        sort_order=1,
                        sections=[
                            # affect: CONFUSED
                            _confused(
                                "ReAct, Reflexion, and the Reasoning Zoo", 0,
                                ("ReAct interleaves CoT traces with acts in a TAO loop, whereas ToT generalises "
                                 "CoT to a search over thoughts with BFS/DFS backtracking, and GoT further "
                                 "generalises ToT to a DAG; Reflexion adds a verbal RL signal over episodic "
                                 "buffers, while LATS fuses MCTS with ReAct using a value model V and a "
                                 "reflection store, and Self-Refine iterates generate-critique-revise without "
                                 "external tools, orthogonal to RAG yet frequently conflated with it."),
                                ("Note ToT subsumes CoT-SC only under a particular aggregation, GoT's volume "
                                 "metric is incomparable to ToT's depth, and Reflexion's signal differs from "
                                 "PPO's despite both being called RL; the distinctions matter, are not restated, "
                                 "and are assumed next. PAL and PoT offload arithmetic to an interpreter, a "
                                 "different axis entirely."),
                                ("If the acronyms outran their definitions, that is the spot to flag.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Trace the Reasoning (Exercise)", 1,
                                "Answer using only the previous section. The distinctions are subtle on purpose.",
                                {
                                    "question": "Which statement is correct, per the previous section ONLY?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "GoT generalises ToT from a tree to a DAG", "isCorrect": True},
                                        {"id": "b", "text": "Reflexion and PPO use the same RL signal", "isCorrect": False},
                                        {"id": "c", "text": "Self-Refine requires external tools", "isCorrect": False},
                                        {"id": "d", "text": "ToT's depth and GoT's volume are directly comparable", "isCorrect": False},
                                    ],
                                    "explanation": "The text stated GoT generalises ToT to a DAG and called the others false.",
                                },
                                {
                                    "prompt": "Name the search structure each uses: CoT, ToT, GoT. (Answer 'chain, tree, graph'.)",
                                    "answer": "chain, tree, graph",
                                    "type": "text",
                                    "explanation": "CoT is a chain, ToT a tree, GoT a graph (DAG).",
                                }),
                        ],
                    ),
                ],
            ),
            Module(
                title="Retrieval & Grounding",
                description="Giving agents knowledge they were not trained on.",
                sort_order=1,
                lessons=[
                    Lesson(
                        title="Giving Agents Knowledge",
                        description="Retrieval-augmented generation, and how to chop up documents.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "Retrieval-Augmented Generation (RAG)", 0,
                                ("A model only knows what it was trained on. RAG fixes that: before answering, "
                                 "the agent searches a knowledge base for relevant passages and puts them into "
                                 "the prompt. The model then answers grounded in those passages instead of "
                                 "guessing from memory — fewer hallucinations, and you can cite sources."),
                                ("flowchart LR\n"
                                 "    Q[Question] --> R[Retrieve\\ntop-k passages]\n"
                                 "    R --> P[Augment prompt\\nquestion + passages]\n"
                                 "    P --> G[Generate answer]\n"
                                 "    G --> Ans[Grounded answer + citations]\n"),
                                ("RAG is 'open-book' answering. If the right passage is not retrieved, the model "
                                 "cannot use it — retrieval quality caps answer quality."),
                                {
                                    "question": "Why does RAG reduce hallucinations?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "It makes the model larger", "isCorrect": False},
                                        {"id": "b", "text": "It puts relevant source passages in the prompt to ground the answer", "isCorrect": True},
                                        {"id": "c", "text": "It turns off the model's creativity", "isCorrect": False},
                                    ],
                                    "explanation": "Grounding the answer in retrieved passages means the model relies on supplied evidence, not guesses.",
                                }),
                            # affect: BORED
                            _bored(
                                "Chunking Strategies, Exhaustively", 1,
                                ("Before retrieval, documents are split into chunks. This section lists the "
                                 "strategies. Read each.\n\n"
                                 "Fixed-size chunking splits every N tokens. Sentence chunking splits on "
                                 "sentences. Paragraph chunking splits on paragraphs. Recursive chunking splits "
                                 "on a priority list of separators. Sliding-window chunking overlaps adjacent "
                                 "chunks. Semantic chunking splits on embedding-similarity boundaries. "
                                 "Markdown-aware chunking splits on headings."),
                                ("Continuing: code-aware chunking splits on functions; table-aware chunking "
                                 "keeps rows together; layout-aware chunking uses PDF geometry; token-budget "
                                 "chunking targets a context fraction; hierarchical chunking nests small chunks "
                                 "in larger ones; proposition chunking splits into atomic claims. Each strategy "
                                 "has an overlap parameter, a size parameter, and a separator parameter, none of "
                                 "which are tabulated here."),
                                ("Restated: fixed-size, sentence, paragraph, recursive, sliding-window, semantic, "
                                 "markdown-aware, code-aware, table-aware, layout-aware, token-budget, "
                                 "hierarchical, proposition. The enumeration is complete for this section.")),
                        ],
                    ),
                    Lesson(
                        title="When Retrieval Fails",
                        description="The geometry of embeddings, and a test of it.",
                        sort_order=1,
                        sections=[
                            # affect: CONFUSED
                            _confused(
                                "Embeddings, Similarity & Dimensionality", 0,
                                ("Retrieval ranks chunks by similarity in an embedding space R^d, usually cosine "
                                 "sim(x,y) = <x,y> / (||x|| ||y||); but in high d, concentration of measure makes "
                                 "pairwise distances converge, so the contrast (d_max - d_min)/d_min -> 0, which "
                                 "is the curse of dimensionality, partially mitigated by ANN indexes (HNSW, IVF-PQ) "
                                 "that trade recall@k for latency via graph or quantisation structure."),
                                ("Note cosine on L2-normalised vectors is monotonic in Euclidean distance, MIPS "
                                 "is not a metric so it breaks triangle-inequality pruning, and learned vs. static "
                                 "embeddings shift the manifold so a re-index is required; none of these caveats "
                                 "were motivated before being used, which is intentional here."),
                                ("If 'concentration of measure' and 'MIPS' arrived undefined, mark the spot.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Tune the Retriever (Exercise)", 1,
                                "Use only the previous section. The reasoning is unforgiving.",
                                {
                                    "question": "Per the section, as embedding dimension d grows very large, what happens to the CONTRAST between nearest and farthest distances?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "It increases, making retrieval easier", "isCorrect": False},
                                        {"id": "b", "text": "It tends toward 0, making points look equidistant", "isCorrect": True},
                                        {"id": "c", "text": "It stays constant", "isCorrect": False},
                                        {"id": "d", "text": "It depends only on k", "isCorrect": False},
                                    ],
                                    "explanation": "Concentration of measure drives (d_max - d_min)/d_min toward 0 — the curse of dimensionality.",
                                },
                                {
                                    "prompt": "On L2-normalised vectors, cosine similarity ranks results the same as which distance? (one word)",
                                    "answer": "euclidean",
                                    "type": "text",
                                    "explanation": "On normalised vectors cosine is monotonic in Euclidean distance, so the ranking matches.",
                                }),
                        ],
                    ),
                ],
            ),
        ],
    )


# ======================================================================
# COURSE 3 — Multi-Agent Systems & Orchestration
# ======================================================================
def _course_multiagent() -> Course:
    return Course(
        title="Multi-Agent Systems & Orchestration",
        description=(
            "One agent is good; a team can be better — or much messier. Why we use multiple "
            "agents, how they coordinate, how we evaluate them, and where it all goes wrong."
        ),
        estimated_duration_minutes=75,
        is_published=True,
        learning_objectives=(
            "Explain when multiple agents help; describe an orchestrator–worker pattern; "
            "reason about coordination failures; evaluate agent systems and their safety."
        ),
        modules=[
            Module(
                title="Scaling to Many Agents",
                description="Coordination, communication, and reliability.",
                sort_order=0,
                lessons=[
                    Lesson(
                        title="Coordinating Multiple Agents",
                        description="Why and how we split work across agents.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "Why Use More Than One Agent?", 0,
                                ("A single agent juggling research, writing, and fact-checking is like one "
                                 "person doing every job in a kitchen. Split the work and each agent can "
                                 "specialise: one plans, others execute, one reviews. A common shape is the "
                                 "orchestrator–worker pattern, where a lead agent breaks a goal into tasks and "
                                 "hands them to focused workers."),
                                ("flowchart TD\n"
                                 "    O[Orchestrator] --> W1[Researcher]\n"
                                 "    O --> W2[Writer]\n"
                                 "    O --> W3[Fact-checker]\n"
                                 "    W1 --> O\n    W2 --> O\n    W3 --> O\n"
                                 "    O --> R[Final answer]\n"),
                                ("Specialising agents tends to lift task success — but it also adds "
                                 "coordination cost. More agents is not always better."),
                                {
                                    "question": "In an orchestrator–worker pattern, the orchestrator mainly:",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Does all the work itself", "isCorrect": False},
                                        {"id": "b", "text": "Splits the goal into tasks and delegates to workers", "isCorrect": True},
                                        {"id": "c", "text": "Replaces the language model", "isCorrect": False},
                                    ],
                                    "explanation": "The orchestrator decomposes the goal and coordinates specialised workers.",
                                }),
                            # affect: BORED
                            _bored(
                                "Message-Passing Field Reference", 1,
                                ("Agents coordinate by exchanging messages. This reference lists the envelope "
                                 "fields. Read every field.\n\n"
                                 "'id' holds a unique identifier. 'from' holds the sender. 'to' holds the "
                                 "recipient. 'reply_to' holds the reply address. 'timestamp' holds the send "
                                 "time. 'ttl' holds the time to live. 'priority' holds 0–9. 'content_type' "
                                 "holds a MIME type. 'encoding' holds the character encoding. 'body' holds the "
                                 "payload."),
                                ("Optional fields follow. 'trace_id' correlates messages. 'span_id' identifies "
                                 "a step. 'retry_count' counts attempts. 'idempotency_key' deduplicates. "
                                 "'signature' authenticates. 'compression' names the algorithm. 'schema_version' "
                                 "names the version. 'locale' names the language. Each defaults to null when "
                                 "absent, and the presence of one implies nothing about another."),
                                ("Restated: id, from, to, reply_to, timestamp, ttl, priority, content_type, "
                                 "encoding, body, trace_id, span_id, retry_count, idempotency_key, signature, "
                                 "compression, schema_version, locale. This concludes the field reference.")),
                        ],
                    ),
                    Lesson(
                        title="Reliability at Scale",
                        description="What breaks when many agents must agree.",
                        sort_order=1,
                        sections=[
                            # affect: CONFUSED
                            _confused(
                                "Consensus, Byzantine Faults & Guarantees", 0,
                                ("Coordination among unreliable agents reduces to consensus, which under "
                                 "asynchrony with a single crash fault is impossible (FLP), yet is circumvented "
                                 "by randomisation or partial synchrony (DLS); BFT tolerates f faulty nodes iff "
                                 "n >= 3f + 1, while CFT needs only n >= 2f + 1, and PBFT achieves the former in "
                                 "three phases (pre-prepare, prepare, commit) with a view-change subprotocol "
                                 "omitted here."),
                                ("Quorum intersection requires any two quorums to overlap in a correct node, "
                                 "hence 3f + 1; linearizability is strictly stronger than sequential consistency, "
                                 "which is incomparable to causal+ consistency, and CALM characterises exactly "
                                 "which coordinations avoid consensus (the monotone ones), assumed but not "
                                 "developed below."),
                                ("If the n >= 3f + 1 bound appeared without derivation, that is the point to flag.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Diagnose the Failure (Exercise)", 1,
                                "Use only the previous section. The numbers are unforgiving.",
                                {
                                    "question": "A BFT system must tolerate f = 2 Byzantine agents. What is the minimum n?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "5", "isCorrect": False},
                                        {"id": "b", "text": "6", "isCorrect": False},
                                        {"id": "c", "text": "7", "isCorrect": True},
                                        {"id": "d", "text": "4", "isCorrect": False},
                                    ],
                                    "explanation": "BFT needs n >= 3f + 1 = 7. (5 only satisfies the weaker crash-fault bound.)",
                                },
                                {
                                    "prompt": "Under pure asynchrony with one crash fault, is deterministic consensus solvable? Answer 'yes' or 'no' and name the result.",
                                    "answer": "no, FLP",
                                    "type": "text",
                                    "explanation": "The FLP impossibility result rules it out.",
                                }),
                        ],
                    ),
                ],
            ),
            Module(
                title="Evaluating Agent Systems",
                description="Knowing whether an agent is actually any good — and safe.",
                sort_order=1,
                lessons=[
                    Lesson(
                        title="Measuring Success",
                        description="What to measure, and what the numbers hide.",
                        sort_order=0,
                        sections=[
                            # affect: ENGAGED
                            _engaged(
                                "How Do We Know an Agent Is Good?", 0,
                                ("'It seems to work' is not evaluation. Good agent evaluation looks at several "
                                 "dimensions at once: did it finish the task (success rate), how often did it "
                                 "need help, how much did it cost in tokens and time, and was it safe. A single "
                                 "number hides trade-offs — a faster agent that fails more is not obviously better."),
                                ("pie showData title What a balanced agent eval weighs\n"
                                 "    \"Task success\" : 40\n"
                                 "    \"Cost (tokens/time)\" : 25\n"
                                 "    \"Safety\" : 20\n"
                                 "    \"Autonomy (no human help)\" : 15\n"),
                                ("Always report task success ALONGSIDE cost and safety. Optimising one metric "
                                 "alone usually wrecks another."),
                                {
                                    "question": "Why is a single success-rate number an incomplete evaluation?",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Success rate is never useful", "isCorrect": False},
                                        {"id": "b", "text": "It hides trade-offs like cost and safety", "isCorrect": True},
                                        {"id": "c", "text": "It only works for one agent", "isCorrect": False},
                                    ],
                                    "explanation": "Success alone ignores cost, safety, and autonomy — an agent can score high on one and badly on the rest.",
                                }),
                            # affect: BORED
                            _bored(
                                "A Glossary of Evaluation Metrics", 1,
                                ("Many metrics exist. This glossary lists them. Read each definition.\n\n"
                                 "Success rate: fraction of tasks completed. Pass@k: success within k attempts. "
                                 "Exact match: output equals reference. F1: harmonic mean of precision and recall. "
                                 "BLEU: n-gram overlap. ROUGE: recall-oriented overlap. Latency: time to respond. "
                                 "Throughput: tasks per minute. Token cost: tokens consumed."),
                                ("Continuing: step count, tool-call count, intervention rate, recovery rate, "
                                 "calibration error, hallucination rate, refusal rate, toxicity rate, win rate "
                                 "(vs. a baseline), Elo (from pairwise comparisons), and human-preference score. "
                                 "Each may be macro- or micro-averaged, and none are tabulated against each other "
                                 "here."),
                                ("Restated: success rate, pass@k, exact match, F1, BLEU, ROUGE, latency, "
                                 "throughput, token cost, step count, tool-call count, intervention rate, "
                                 "recovery rate, calibration error, hallucination rate, refusal rate, toxicity "
                                 "rate, win rate, Elo, human-preference score.")),
                        ],
                    ),
                    Lesson(
                        title="Safety & Failure",
                        description="Where capable agents go wrong on purpose.",
                        sort_order=1,
                        sections=[
                            # affect: CONFUSED
                            _confused(
                                "Reward Hacking & Specification Gaming", 0,
                                ("When an agent optimises a proxy objective J_hat that diverges from the true "
                                 "objective J, Goodhart's law bites: argmax of J_hat need not align with J, and "
                                 "the gap widens under distribution shift; specification gaming exploits "
                                 "under-specified reward, while reward tampering corrupts the channel that "
                                 "computes it, and mesa-optimisation introduces an inner objective that may be "
                                 "misaligned with the outer one even when the outer is correct."),
                                ("Note KL-regularisation to a reference policy bounds but does not eliminate the "
                                 "divergence, RLHF's reward model is itself a learned proxy hence doubly "
                                 "Goodhart-prone, and corrigibility is not implied by low training loss; these "
                                 "claims are stated without proof and assumed in the exercise."),
                                ("If 'mesa-optimisation' and 'corrigibility' landed undefined, that is the spot "
                                 "to flag.")),
                            # affect: FRUSTRATED
                            _frustrated(
                                "Audit the Agent (Exercise)", 1,
                                "Use only the previous section. The distinctions are deliberately fine.",
                                {
                                    "question": "An agent gets high reward by editing the file that stores its own score. Per the section, this is BEST called:",
                                    "type": "single",
                                    "options": [
                                        {"id": "a", "text": "Specification gaming", "isCorrect": False},
                                        {"id": "b", "text": "Reward tampering", "isCorrect": True},
                                        {"id": "c", "text": "Mesa-optimisation", "isCorrect": False},
                                        {"id": "d", "text": "Distribution shift", "isCorrect": False},
                                    ],
                                    "explanation": "Corrupting the channel that computes the reward is reward tampering, distinct from merely exploiting an under-specified reward (gaming).",
                                },
                                {
                                    "prompt": "Name the 'law' that says optimising a proxy metric makes it stop tracking the true goal. (One name.)",
                                    "answer": "Goodhart",
                                    "type": "text",
                                    "explanation": "Goodhart's law: when a measure becomes a target, it ceases to be a good measure.",
                                }),
                        ],
                    ),
                ],
            ),
        ],
    )


def _build_courses() -> list[Course]:
    return [_course_foundations(), _course_building(), _course_multiagent()]


_TITLES = [
    "Foundations of Agentic AI",
    "Building AI Agents: Tools, Memory & Planning",
    "Multi-Agent Systems & Orchestration",
]


async def reset_courses(db: AsyncSession) -> int:
    """Delete the seeded courses (cascade removes modules/lessons/sections/blocks)."""
    res = await db.execute(select(Course).where(Course.title.in_(_TITLES)))
    courses = res.scalars().all()
    for c in courses:
        await db.delete(c)
    await db.commit()
    return len(courses)


async def seed_courses(db: AsyncSession) -> list[str]:
    """Insert the real Agentic AI courses if absent (idempotent by title)."""
    created = []
    for course in _build_courses():
        existing = await db.execute(select(Course).where(Course.title == course.title))
        if existing.scalar_one_or_none() is None:
            db.add(course)
            created.append(course.title)
    await db.commit()
    return created


async def run_seed(reset: bool = False) -> None:
    async with async_session() as db:
        if reset:
            n = await reset_courses(db)
            print(f"Reset: deleted {n} existing course(s).")
        created = await seed_courses(db)
        if created:
            print(f"Seeded courses: {', '.join(created)}")
        else:
            print("All courses already exist — no changes.")


if __name__ == "__main__":
    asyncio.run(run_seed(reset="--reset" in sys.argv))
