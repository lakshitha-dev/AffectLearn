"""Course: "Building AI Agents: Tools, Memory & Planning".

A ~60-minute deep-dive authored with the course_content_helpers API. Sections are
deliberately varied to induce each of the four affect states we study (engaged,
bored, confused, frustrated); the `# affect:` comment above every section() call
records the intended state for the behavioral-data instrument.
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
    reflection,
    section,
    text,
)


def build():
    return course(
        "Building AI Agents: Tools, Memory & Planning",
        (
            "A practical, depth-first course on turning a bare language model into a "
            "capable agent. You will learn how tools and function calling extend a "
            "model beyond text, how structured output makes tool use reliable, how the "
            "different flavours of agent memory work, and how planning, the ReAct loop, "
            "and retrieval-augmented generation let an agent reason over long tasks and "
            "external knowledge."
        ),
        (
            "By the end of this course you will be able to: (1) explain what a tool is "
            "and design a JSON tool schema a model can call; (2) decide when giving an "
            "agent a tool is warranted; (3) distinguish short-term, working, episodic, "
            "semantic, and vector memory; (4) describe planning and task decomposition; "
            "(5) compare ReAct, Tree-of-Thoughts, Graph-of-Thoughts, and Reflexion; "
            "(6) build a retrieval-augmented generation pipeline; and (7) reason about "
            "embeddings, similarity, and the curse of dimensionality."
        ),
        60,
        _module_capabilities(),
        _module_reasoning(),
    )


# =============================================================================
# MODULE 1 — Giving Agents Capabilities
# =============================================================================

def _module_capabilities() -> "module":
    return module(
        "Giving Agents Capabilities",
        (
            "A language model on its own can only produce text. This module covers the "
            "first thing that turns a model into an agent: the ability to act through "
            "tools, to return machine-readable output, and to remember."
        ),
        _lesson_tools(),
        _lesson_structured_output(),
        _lesson_memory(),
    )


def _lesson_tools() -> "lesson":
    return lesson(
        "Tool Use & Function Calling",
        "How an agent reaches outside its own weights to call code, APIs, and services.",

        # affect: engaged
        section(
            "What a Tool Is and Why an Agent Needs One",
            4,
            text(
                "A base language model is a function from text to text. It predicts the "
                "next token given everything it has seen. That is enormously useful, but "
                "it has hard limits: the model cannot look up today's weather, run a "
                "database query, send an email, or do reliable arithmetic on large "
                "numbers. Everything it 'knows' is frozen into its weights at training "
                "time, and everything it does is confined to emitting text.\n\n"
                "A tool removes that ceiling. A tool is simply a function the agent is "
                "allowed to call: a small, named capability with a described set of "
                "inputs and a predictable output. `get_weather(city)`, "
                "`search_documents(query)`, and `send_email(to, subject, body)` are all "
                "tools. The model does not execute the tool itself. Instead, the model "
                "emits a structured request that says 'call get_weather with "
                "city=Colombo', your application runs the real function, and the result "
                "is handed back to the model so it can continue.\n\n"
                "This split is the whole idea. The model supplies judgement — deciding "
                "which tool to call and with what arguments — while your code supplies "
                "the actual capability and keeps control of anything sensitive. Function "
                "calling is the protocol that makes this handoff reliable, because the "
                "model is constrained to produce a request that matches a schema you "
                "defined, rather than free-form prose your code would have to parse."
            ),
            callout(
                "Mental model: the model is the brain, tools are the hands. The brain "
                "decides what to do; the hands actually touch the world. Keeping them "
                "separate is what makes an agent both capable and controllable.",
                "tip",
            ),
            text(
                "Consider a concrete worked example. A user asks: 'What is 4,817 times "
                "2,933, and is it bigger than a million?' A raw model might guess the "
                "product and get it subtly wrong. An agent with a `calculator(expr)` "
                "tool instead emits a call `calculator(\"4817 * 2933\")`, receives the "
                "exact value 14,128,261 back, and only then writes the final answer. The "
                "model contributed the reasoning ('multiply, then compare to 1,000,000') "
                "and the tool contributed the exactness. Neither could do the job well "
                "alone."
            ),
        ),

        # affect: engaged
        section(
            "Anatomy of a Tool Schema",
            4,
            text(
                "For a model to call a tool correctly, it needs a precise description of "
                "that tool: its name, what it does, and exactly what arguments it takes. "
                "That description is the tool schema, and it is almost always expressed "
                "as JSON Schema. The schema is passed to the model alongside the "
                "conversation so the model knows the menu of actions available to it.\n\n"
                "A good schema is self-documenting. The `description` fields are not "
                "decoration — the model reads them to decide when and how to call the "
                "tool, so they function as instructions. Well-chosen parameter names, "
                "clear descriptions, sensible `enum` constraints, and an accurate "
                "`required` list dramatically improve how reliably a model calls your "
                "tool. A sloppy schema produces sloppy calls."
            ),
            code(
                """{
  "name": "get_weather",
  "description": "Get the current weather for a city. Use when the user asks about temperature, rain, or conditions right now.",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string",
        "description": "City name, e.g. 'Colombo' or 'Tokyo'."
      },
      "units": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "description": "Temperature unit to return. Defaults to celsius.",
        "default": "celsius"
      }
    },
    "required": ["city"]
  }
}""",
                "json",
            ),
            text(
                "Read the schema top-down the way the model does. The `name` is the "
                "identifier the model emits when it wants this action. The top-level "
                "`description` tells it when the tool is appropriate. Inside "
                "`input_schema`, each property has a type and a description; `units` is "
                "constrained to an enum so the model cannot invent an unsupported value; "
                "and `required` marks `city` as mandatory while `units` is optional. When "
                "the model decides to call this tool, it produces an arguments object "
                "such as `{\"city\": \"Colombo\", \"units\": \"celsius\"}` that validates "
                "against this schema."
            ),
        ),

        # affect: engaged
        section(
            "The Tool-Call Round Trip",
            4,
            text(
                "Function calling is not one request — it is a loop. The model does not "
                "get the tool result magically; your application is the middle layer that "
                "executes the tool and feeds the output back. Understanding the sequence "
                "of messages is the single most useful thing for debugging agents.\n\n"
                "The round trip has five steps. First, your app sends the user's message "
                "plus the tool schemas. Second, the model responds not with a final "
                "answer but with a tool-call request. Third, your app executes the real "
                "function. Fourth, your app sends the tool's result back to the model as "
                "a new message. Fifth, the model incorporates the result and produces the "
                "final natural-language answer. If more than one tool is needed, steps two "
                "through four simply repeat."
            ),
            mermaid(
                """sequenceDiagram
    participant U as User
    participant A as Your App
    participant M as Model
    participant T as Tool (get_weather)
    U->>A: "What's the weather in Colombo?"
    A->>M: message + tool schemas
    M-->>A: tool_call get_weather(city="Colombo")
    A->>T: run get_weather("Colombo")
    T-->>A: {"temp_c": 30, "sky": "clear"}
    A->>M: tool_result {"temp_c": 30, "sky": "clear"}
    M-->>A: "It's 30 C and clear in Colombo."
    A->>U: final answer"""
            ),
            quiz(
                "In the tool-call round trip, who actually executes the tool function?",
                [
                    ("The model executes it internally.", False),
                    ("Your application code executes it and returns the result to the model.", True),
                    ("The user runs it manually.", False),
                    ("The JSON schema executes it.", False),
                ],
                explanation=(
                    "The model only emits a structured request. Your application runs the "
                    "real function and sends the result back as a tool_result message. This "
                    "separation is what keeps side effects under your control."
                ),
            ),
        ),

        # affect: engaged
        section(
            "When (and When Not) to Give an Agent a Tool",
            4,
            text(
                "Every tool you add is also a liability: more surface area for the model "
                "to misuse, more failure modes, and more schema for it to read. So the "
                "decision to add a tool should be deliberate. A tool earns its place when "
                "it gives the agent a capability the model genuinely lacks, or when it "
                "makes an otherwise unreliable behaviour reliable.\n\n"
                "Give an agent a tool when the task needs (a) fresh or private data the "
                "model was never trained on, such as live prices or your company's "
                "records; (b) exactness the model cannot guarantee, such as arithmetic or "
                "date math; (c) a side effect in the real world, such as writing to a "
                "database or sending a message; or (d) a specialised system that already "
                "does the job well, such as a search engine.\n\n"
                "Do not add a tool when the model can already do the task reliably from "
                "its own knowledge, when the tool duplicates another tool, or when the "
                "task is so open-ended that no clean schema captures it. Redundant or "
                "vague tools confuse the model and make it more likely to pick the wrong "
                "one. Fewer, sharper tools beat a sprawling toolbox."
            ),
            callout(
                "Rule of thumb: add a tool to buy freshness, exactness, side effects, or "
                "specialisation. If the model already answers well without it, the tool is "
                "just extra risk.",
                "info",
            ),
            exercise(
                "For each task, decide whether the agent needs a tool and name it if so: "
                "(1) summarise a paragraph the user pasted; (2) tell the user tomorrow's "
                "exchange rate; (3) capitalise a sentence; (4) cancel the user's most "
                "recent order.",
                answer=(
                    "(1) No tool — summarising provided text is core model ability. "
                    "(2) Yes — a live rate lookup tool (fresh data). "
                    "(3) No tool — trivial text transformation. "
                    "(4) Yes — a cancel_order(order_id) tool (a real-world side effect)."
                ),
                explanation=(
                    "Tools are justified by freshness (2) and side effects (4). Pure text "
                    "manipulation the model already handles (1, 3) needs no tool."
                ),
            ),
        ),
    )


def _lesson_structured_output() -> "lesson":
    return lesson(
        "Structured Output",
        "Making a model return machine-readable data your program can trust.",

        # affect: engaged
        section(
            "Why Free Text Breaks Programs",
            4,
            text(
                "Tool calling works because the model is forced to produce a request that "
                "matches a schema. The same principle applies whenever your program needs "
                "to consume the model's answer, not just show it to a human. If you ask a "
                "model to 'return the customer's name and priority' and it replies 'Sure! "
                "The customer is Ada, and I'd rate this high priority.', your code now has "
                "to parse prose, and prose is fragile. The next call might say 'high-"
                "priority' or 'HIGH' or wrap it in a sentence, and your parser breaks.\n\n"
                "Structured output solves this by constraining the model to emit data in a "
                "fixed shape — almost always JSON conforming to a schema you supply. "
                "Instead of hoping the wording is stable, you get "
                "`{\"name\": \"Ada\", \"priority\": \"high\"}` every time, with "
                "`priority` restricted to a known set of values. Your code can then treat "
                "the model like any other well-behaved API."
            ),
            code(
                """{
  "type": "object",
  "properties": {
    "name":     {"type": "string"},
    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
    "tags":     {"type": "array", "items": {"type": "string"}}
  },
  "required": ["name", "priority"]
}""",
                "json",
            ),
            text(
                "This is the same JSON Schema vocabulary you saw for tool arguments — and "
                "that is not a coincidence. A tool call is really just structured output "
                "with a name attached. Learn the schema shape once and you can constrain "
                "both what the agent calls and what it returns."
            ),
        ),

        # affect: frustrated
        section(
            "Schema Edge Cases That Bite",
            5,
            text(
                "Structured output looks simple until you meet the edge cases. A schema "
                "that is technically valid can still lead a model into producing output "
                "your downstream code silently mishandles. The quiz below depends on "
                "reading the schema in the previous section precisely — every word of "
                "`required`, `enum`, and `type` matters, and the distractors are designed "
                "to look plausible."
            ),
            quiz(
                "Given the schema above (name/priority/tags), which of the following "
                "model outputs is BOTH schema-valid AND safe for a program that later does "
                "`for tag in result['tags']`?",
                [
                    (
                        "{\"name\": \"Ada\", \"priority\": \"urgent\", \"tags\": [\"vip\"]}",
                        False,
                    ),
                    (
                        "{\"name\": \"Ada\", \"priority\": \"high\"}",
                        False,
                    ),
                    (
                        "{\"name\": \"Ada\", \"priority\": \"high\", \"tags\": []}",
                        True,
                    ),
                    (
                        "{\"name\": \"Ada\", \"priority\": \"high\", \"tags\": \"vip\"}",
                        False,
                    ),
                ],
                explanation=(
                    "The trap is subtle. Option 1 fails validation: 'urgent' is not in the "
                    "priority enum. Option 2 validates (tags is optional) but then "
                    "`result['tags']` raises KeyError — schema-valid is not the same as "
                    "safe to iterate. Option 4 fails validation because tags must be an "
                    "array, not a string. Only option 3 both validates and gives an "
                    "iterable (an empty list iterates zero times, harmlessly). 'Valid' and "
                    "'safe to use' are different guarantees."
                ),
            ),
            callout(
                "If your code assumes a field exists, put it in `required` — do not rely "
                "on the model to include optional fields. Otherwise a valid response can "
                "still crash you.",
                "warning",
            ),
        ),

        # affect: confused
        section(
            "Constrained Decoding and Grammars",
            4,
            text(
                "How is the model actually forced to obey a schema? The mechanism is "
                "constrained decoding. At each decoding step a model produces a "
                "probability distribution over the next token; normally it samples from "
                "that distribution freely. Under constrained decoding the runtime "
                "intersects the schema — compiled into a formal grammar, typically a "
                "context-free or regular grammar with a corresponding automaton — with the "
                "token vocabulary, and masks out every token that could not continue a "
                "grammar-valid string. The logits of forbidden tokens are driven to "
                "negative infinity before the softmax, so their sampling probability is "
                "exactly zero.\n\n"
                "Concretely, JSON Schema is lowered to a grammar; the grammar induces a "
                "finite-state or pushdown recogniser; and at position t the recogniser's "
                "current state defines the admissible next-token set A_t. The sampler is "
                "restricted to A_t, guaranteeing the emitted token sequence is a member of "
                "the language L(G) the grammar generates. This is why constrained "
                "generation cannot emit malformed JSON — malformed strings are simply not "
                "in L(G) — but it also interacts with tokenisation in awkward ways, since "
                "a single grammar symbol may span sub-token boundaries and force partial-"
                "token masking. The upshot: constrained decoding trades a little "
                "generative freedom and some latency for a hard structural guarantee."
            ),
            callout(
                "Here is something that should feel wrong. The model was trained to "
                "put probability on those forbidden tokens — so by masking them to "
                "zero, are we not overriding the model and forcing it to write text "
                "it 'believes' is wrong? The resolution: masking removes only the "
                "grammar-INVALID continuations; among the tokens that remain, the "
                "model's relative preferences are untouched. We are pruning the "
                "impossible, not rewriting the model's judgement — which is why the "
                "output stays fluent, just guaranteed well-formed.",
                "info",
            ),
            reflection(
                "In your own words, why can a model under grammar-constrained decoding "
                "never emit invalid JSON? What might it give up in exchange?"
            ),
        ),
    )


def _lesson_memory() -> "lesson":
    return lesson(
        "Agent Memory",
        "What an agent remembers, for how long, and where it is stored.",

        # affect: bored
        section(
            "A Catalogue of Memory Types",
            5,
            text(
                "Agent memory is not one thing. The literature borrows terms from "
                "cognitive science and from systems engineering, and an agent framework "
                "will often expose several of these at once. What follows is an exhaustive "
                "catalogue. Read it carefully; the distinctions are dry but they recur "
                "constantly in agent design documents."
            ),
            text(
                "Short-term memory: the information available within the current "
                "reasoning step or turn. In practice this is whatever currently sits in "
                "the model's context window. It is fast, it is free to read, and it "
                "vanishes the moment it scrolls out of the window.\n\n"
                "Working memory: the small, actively-manipulated scratch space the agent "
                "uses while solving the immediate task — intermediate results, the current "
                "sub-goal, a running tally. Working memory is a subset of short-term "
                "memory that is being operated on right now.\n\n"
                "Episodic memory: a record of specific past events and interactions — "
                "'on Tuesday the user asked about invoices and I looked up order 44.' "
                "Episodic entries are timestamped, particular, and autobiographical.\n\n"
                "Semantic memory: general facts and knowledge abstracted away from any "
                "single episode — 'the user prefers metric units', 'invoices are due in "
                "30 days.' Semantic memory is the distilled, timeless residue of many "
                "episodes.\n\n"
                "Procedural memory: learned how-to knowledge — the steps or skills the "
                "agent applies, such as a saved routine for reconciling a ledger. It is "
                "knowledge of process rather than of facts.\n\n"
                "Vector memory: a storage backend, not a cognitive category. Text is "
                "embedded into vectors and stored in a vector database so it can be "
                "retrieved later by similarity. Episodic and semantic memory are commonly "
                "implemented on top of vector memory.\n\n"
                "Buffer memory: the simplest long-term store — a rolling log of the last "
                "N messages kept verbatim.\n\n"
                "Summary memory: instead of keeping raw messages, the agent periodically "
                "compresses old turns into a running summary to save context space.\n\n"
                "Entity memory: per-entity facts, keyed by the person, product, or place "
                "they concern, so the agent can recall 'everything I know about Ada.'"
            ),
            callout(
                "Do not memorise the taxonomy for its own sake. The one distinction that "
                "actually drives design decisions is short-term (in-context, ephemeral) "
                "versus long-term (externally stored, retrieved on demand).",
                "info",
            ),
        ),

        # affect: bored
        section(
            "Chunking and Retention Strategies",
            4,
            text(
                "Whenever memory is stored externally, text must be broken into pieces — "
                "chunks — before it is embedded and saved. The choice of chunking "
                "strategy is unglamorous but it shapes everything downstream. Here is the "
                "standard catalogue of strategies, each with its trade-off."
            ),
            text(
                "Fixed-size chunking: split every N characters or tokens. Trivial to "
                "implement; frequently cuts sentences in half.\n\n"
                "Fixed-size with overlap: the same, but each chunk repeats the last few "
                "tokens of the previous chunk so context is not lost at boundaries. The "
                "overlap costs storage.\n\n"
                "Sentence-based chunking: split on sentence boundaries. Keeps thoughts "
                "intact; produces uneven chunk sizes.\n\n"
                "Paragraph-based chunking: split on blank lines. Preserves more context; "
                "some paragraphs are far too long.\n\n"
                "Recursive chunking: try to split on the largest structural boundary "
                "(sections), fall back to paragraphs, then sentences, then characters, "
                "until pieces fit the size budget.\n\n"
                "Semantic chunking: embed sentences and start a new chunk when the "
                "meaning shifts. The most faithful, the most expensive.\n\n"
                "Document-structure chunking: use headings, lists, and tables from the "
                "source markup as natural chunk boundaries.\n\n"
                "For retention — deciding what to keep — the usual policies are: keep "
                "everything (simple, unbounded growth); recency windows (drop the oldest); "
                "least-recently-used eviction; importance scoring (keep entries the agent "
                "flagged as significant); and summarise-then-discard (compress old detail "
                "into semantic memory, then delete the raw episodes)."
            ),
        ),

        # affect: engaged
        section(
            "Short-Term vs Long-Term Memory in Practice",
            4,
            text(
                "Strip away the taxonomy and one distinction does the real work: "
                "short-term memory lives in the context window and disappears; long-term "
                "memory lives in external storage and is retrieved on demand. Designing an "
                "agent's memory is mostly deciding what belongs in each and how information "
                "moves between them.\n\n"
                "Short-term memory is the conversation so far, plus the current task's "
                "scratch work. It is instantly available but bounded by the context window "
                "and gone once the window fills. Long-term memory is anything the agent "
                "should still know next week: user preferences, past outcomes, reference "
                "documents. It is stored outside the model — often in a vector database — "
                "and only the relevant slice is pulled back into the context window when "
                "needed.\n\n"
                "The flow between them is the interesting part. As a conversation grows, "
                "the agent summarises old turns and writes durable facts to long-term "
                "memory (consolidation). When a new request arrives, it retrieves the most "
                "relevant long-term entries and places them into short-term context "
                "(recall). This write-then-retrieve cycle is exactly the RAG pattern you "
                "will build in Module 2 — long-term memory and retrieval are two names for "
                "the same machinery."
            ),
            mermaid(
                """flowchart LR
    A[User turn] --> B[Short-term memory: context window]
    B --> C{Important or durable?}
    C -->|yes| D[Consolidate: summarise + embed]
    D --> E[(Long-term store: vector DB)]
    C -->|no| F[Let it scroll out]
    G[New request] --> H[Retrieve relevant entries]
    E --> H
    H --> B"""
            ),
            quiz(
                "Where does short-term memory physically live in a typical agent?",
                [
                    ("In a vector database on disk", False),
                    ("In the model's context window", True),
                    ("In the tool schemas", False),
                    ("In the model's trained weights", False),
                ],
                explanation=(
                    "Short-term memory is whatever currently occupies the context window. "
                    "It is fast and free to read but ephemeral — it is lost when it scrolls "
                    "out. Long-term memory is what lives in the vector database."
                ),
            ),
        ),
    )


# =============================================================================
# MODULE 2 — Reasoning, Retrieval & Planning
# =============================================================================

def _module_reasoning() -> "module":
    return module(
        "Reasoning, Retrieval & Planning",
        (
            "Capabilities are not enough; an agent must decide how to use them over a "
            "multi-step task. This module covers planning and decomposition, the family "
            "of reasoning patterns, retrieval-augmented generation, and the vector math "
            "that makes retrieval work."
        ),
        _lesson_planning(),
        _lesson_retrieval(),
    )


def _lesson_planning() -> "lesson":
    return lesson(
        "Planning & Reasoning Patterns",
        "How an agent breaks a big task into steps and structures its own thinking.",

        # affect: engaged
        section(
            "Planning and Task Decomposition",
            4,
            text(
                "A capable agent rarely solves a real task in a single shot. Asked to "
                "'plan a three-day trip to Kandy under a budget', it must break the goal "
                "into sub-goals — pick dates, find transport, find lodging, sum the cost, "
                "check it against the budget — and tackle them in order, feeding the "
                "result of each step into the next. This breaking-down is task "
                "decomposition, and the ordered set of steps is the plan.\n\n"
                "Decomposition matters because language models reason better on small, "
                "concrete sub-problems than on one sprawling request. A plan also gives "
                "you inspection points: you can see the intended steps before any tool "
                "runs, and you can detect when a step failed. Some agents plan everything "
                "up front (plan-then-execute); others interleave planning and acting, "
                "revising the plan as new information arrives. The interleaved style is "
                "more robust when the world can surprise the agent — which it usually "
                "can."
            ),
            mermaid(
                """flowchart TD
    G[Goal: 3-day Kandy trip under budget] --> S1[Sub-goal: choose dates]
    G --> S2[Sub-goal: find transport]
    G --> S3[Sub-goal: find lodging]
    S1 --> C[Combine + total cost]
    S2 --> C
    S3 --> C
    C --> D{Under budget?}
    D -->|yes| F[Return plan]
    D -->|no| R[Revise: cheaper options] --> C"""
            ),
            quiz(
                "What is the main reason agents decompose a large task into sub-goals?",
                [
                    ("It uses fewer tokens overall", False),
                    ("Models reason more reliably on small concrete steps, and the plan "
                     "becomes inspectable", True),
                    ("It removes the need for any tools", False),
                    ("It guarantees the task will succeed", False),
                ],
                explanation=(
                    "Decomposition improves reliability (small, concrete sub-problems are "
                    "easier for a model) and gives you visibility into the intended steps "
                    "before and while they run. It does not guarantee success."
                ),
            ),
        ),

        # affect: engaged
        section(
            "The ReAct Loop",
            4,
            text(
                "ReAct — short for Reasoning + Acting — is the workhorse pattern for tool-"
                "using agents. The idea is to interleave three moves in a loop: Thought "
                "(the model reasons in text about what to do next), Action (it calls a "
                "tool), and Observation (it reads the tool's result). It then thinks "
                "again in light of the observation, acts again, and repeats until it has "
                "enough to answer.\n\n"
                "The power of ReAct is that reasoning and acting inform each other. Pure "
                "reasoning with no actions cannot get fresh facts; pure acting with no "
                "reasoning flails without a strategy. By alternating, the agent can adjust "
                "its plan based on what each tool actually returns. The loop needs a stop "
                "condition — a final-answer action or a step limit — otherwise a confused "
                "agent will loop forever."
            ),
            code(
                '''state = "user question"
for step in range(MAX_STEPS):
    thought = model.think(state)            # Thought
    if thought.is_final:
        return thought.answer
    action = thought.chosen_tool_call       # Action
    observation = run_tool(action)          # Observation
    state = state + thought + action + observation   # feed back in''',
                "python",
            ),
            callout(
                "ReAct is just the tool-call round trip from Module 1, run in a loop, with "
                "an explicit 'Thought' before each 'Action'. If you understood that "
                "sequence diagram, you already understand ReAct.",
                "tip",
            ),
        ),

        # affect: confused
        section(
            "The Reasoning-Pattern Zoo",
            5,
            text(
                "ReAct is one point in a fast-growing design space of inference-time "
                "reasoning structures, and the literature has produced a thicket of "
                "acronyms. Chain-of-Thought (CoT) elicits a single linear reasoning "
                "trace. Self-Consistency samples k independent CoT traces and takes a "
                "majority vote over their answers, trading compute for variance "
                "reduction. Tree-of-Thoughts (ToT) generalises the linear chain into a "
                "search tree: each node is a partial 'thought', the model expands "
                "children by proposing continuations, a heuristic value function scores "
                "frontier nodes, and a search policy — BFS, DFS, or beam — explores and "
                "backtracks, so the reasoning is no longer a path but a traversal.\n\n"
                "Graph-of-Thoughts (GoT) drops the tree constraint entirely: thoughts "
                "become vertices in an arbitrary DAG where edges denote dependency, "
                "aggregation, or refinement, allowing partial results to be merged "
                "(fan-in) and reused across branches rather than only branched (fan-out). "
                "Reflexion adds an orthogonal axis — a verbal reinforcement loop: after an "
                "episode the agent generates a self-critique in natural language, writes "
                "it to an episodic buffer, and conditions the next attempt on that "
                "reflective memory, approximating policy improvement without any gradient "
                "update. Layer in ReAct's act/observe interleaving, tool-augmented "
                "variants, and planner-executor splits, and the taxonomy is combinatorial: "
                "CoT vs ToT vs GoT is a topology axis (path / tree / graph), while "
                "Self-Consistency, Reflexion, and ReAct are orthogonal axes over sampling, "
                "memory, and grounding respectively."
            ),
            callout(
                "A claim that seems to follow — but does not. Graph-of-Thoughts "
                "allows an arbitrary DAG, which strictly contains paths (CoT) and "
                "trees (ToT) as special cases. So surely GoT can do everything the "
                "others can, and the weaker patterns are obsolete? Hold that thought: "
                "generality is not free, and 'can represent' is not 'should use'. Why "
                "the most general structure is often the wrong choice is exactly what "
                "the next section forces you to work out.",
                "info",
            ),
            reflection(
                "Try to place four patterns on the 'topology' axis: which of CoT, ToT, "
                "GoT, and Reflexion describe the SHAPE of the reasoning (path/tree/graph), "
                "and which one is really about something else? Write down your grouping "
                "before moving on."
            ),
        ),

        # affect: frustrated
        section(
            "Which Pattern Fits? A Tricky Case",
            4,
            text(
                "Choosing a reasoning pattern under real constraints is where the "
                "distinctions from the previous section stop being academic. The following "
                "question depends on holding all four patterns and their orthogonal axes "
                "in mind at once. The options are deliberately close; read each against "
                "the precise definitions above."
            ),
            quiz(
                "An agent must solve a puzzle where many partial solutions should be "
                "generated, independently explored WITH backtracking, and where a good "
                "solution is found by SEARCHING and scoring partial states — but partial "
                "results never need to be merged together. It should also LEARN from a "
                "failed attempt across episodes using written self-critique. Which "
                "combination is the most precise fit?",
                [
                    (
                        "Graph-of-Thoughts, because it supports the richest structure and "
                        "therefore covers every case.",
                        False,
                    ),
                    (
                        "Tree-of-Thoughts for the search-with-backtracking, plus Reflexion "
                        "for the cross-episode learning from a written critique.",
                        True,
                    ),
                    (
                        "Self-Consistency, because sampling many traces and voting explores "
                        "partial solutions and learns from failures.",
                        False,
                    ),
                    (
                        "Chain-of-Thought with ReAct, because a linear trace plus tools can "
                        "do anything the others can.",
                        False,
                    ),
                ],
                explanation=(
                    "The task never merges partial results (fan-in), so Graph-of-Thoughts "
                    "is over-powered and its distinguishing feature is unused — 'richest "
                    "structure covers everything' is a trap. Search with backtracking over "
                    "scored partial states is exactly Tree-of-Thoughts (a tree topology, "
                    "not a graph). Self-Consistency only votes over independent complete "
                    "traces; it neither backtracks nor learns across episodes. CoT is a "
                    "single path with no search. The cross-episode learning from a written "
                    "self-critique is the defining feature of Reflexion, which is "
                    "orthogonal to topology — so ToT + Reflexion is the precise pairing."
                ),
            ),
            callout(
                "If that felt like a lot to juggle, that is the point: the patterns live on "
                "different axes (topology vs sampling vs memory), and picking one means "
                "naming which axis your problem actually stresses.",
                "warning",
            ),
        ),
    )


def _lesson_retrieval() -> "lesson":
    return lesson(
        "Retrieval-Augmented Generation & Embeddings",
        "Grounding an agent in external knowledge, and the vector math that makes it work.",

        # affect: engaged
        section(
            "The RAG Pipeline",
            4,
            text(
                "Retrieval-augmented generation (RAG) is the standard way to give an agent "
                "knowledge it was never trained on without retraining the model. The idea "
                "is simple: before answering, fetch the most relevant documents from an "
                "external store and put them into the model's context, so the answer is "
                "grounded in real sources rather than the model's memory.\n\n"
                "A RAG system has two phases. Offline (indexing), you chunk your documents, "
                "embed each chunk into a vector, and store the vectors in a vector "
                "database. Online (querying), you embed the user's question with the same "
                "model, find the chunks whose vectors are most similar to the question "
                "vector, and hand those chunks to the model alongside the question. The "
                "model then answers using the retrieved context. Because retrieval is just "
                "the 'recall' half of long-term memory from Module 1, RAG and long-term "
                "memory share the same backbone."
            ),
            mermaid(
                """flowchart LR
    subgraph Indexing (offline)
        D[Documents] --> Ch[Chunk] --> Em1[Embed] --> V[(Vector DB)]
    end
    subgraph Query (online)
        Q[User question] --> Em2[Embed] --> R[Similarity search]
        V --> R
        R --> Ctx[Top-k chunks]
        Ctx --> LLM[Model answers with context]
        Q --> LLM
    end"""
            ),
            quiz(
                "In RAG, what is put into the model's context to ground its answer?",
                [
                    ("The entire document store", False),
                    ("The top-k most similar retrieved chunks", True),
                    ("Only the raw user question", False),
                    ("The vector database schema", False),
                ],
                explanation=(
                    "RAG retrieves the top-k chunks whose embeddings are most similar to "
                    "the question and places just those into the context. Passing the whole "
                    "store would blow the context window and add noise."
                ),
            ),
        ),

        # affect: confused
        section(
            "Embeddings, Cosine Similarity & the Curse of Dimensionality",
            5,
            text(
                "Retrieval hinges on embeddings. An embedding is a learned map f: text -> "
                "R^d that sends a piece of text to a dense vector in a d-dimensional space "
                "(d is often 768, 1024, or 1536), trained so that semantically similar "
                "texts land near each other. 'Similarity' is then a geometric quantity. "
                "The dominant measure is cosine similarity: for vectors u and v, "
                "cos(u, v) = (u . v) / (||u|| ||v||), the dot product normalised by both "
                "magnitudes, which equals the cosine of the angle between them and lies in "
                "[-1, 1]. Because it ignores magnitude and looks only at direction, cosine "
                "similarity compares meaning rather than length; nearest-neighbour "
                "retrieval returns the k chunks with the highest cosine to the query "
                "vector.\n\n"
                "Now the twist: high-dimensional geometry is deeply unintuitive, and this "
                "is the curse of dimensionality. As d grows, the volume of the space "
                "explodes exponentially, so any fixed set of points becomes vanishingly "
                "sparse; worse, the distances between all pairs of random points "
                "concentrate — the ratio (max_dist - min_dist) / min_dist tends toward "
                "zero — so 'nearest' and 'farthest' neighbours become almost "
                "indistinguishable, and naive distance-based retrieval loses "
                "discriminative power. Embedding models fight this because training forces "
                "meaningful structure onto a low-dimensional manifold embedded within the "
                "ambient R^d, so real queries do not behave like uniformly random points. "
                "Practical systems further mitigate cost and concentration with "
                "approximate nearest-neighbour indexes (HNSW graphs, IVF partitioning, "
                "product quantisation) that trade exact recall for sub-linear query time. "
                "The takeaway under the notation: similarity is an angle, the ambient "
                "space is treacherous, and learned structure plus ANN indexing is what "
                "keeps retrieval usable."
            ),
            callout(
                "Two things you were just told seem to collide. More dimensions "
                "should give the model more room to pull different meanings apart — "
                "yet the curse of dimensionality says that as d grows, all points "
                "drift toward equidistant and 'nearest' loses meaning. So are more "
                "dimensions helping retrieval or wrecking it? The reconciliation is "
                "in the paragraph above: the curse is about UNIFORMLY RANDOM points, "
                "but trained embeddings are not random — they lie on a low-dimensional "
                "manifold inside R^d, so the extra dimensions buy expressive structure "
                "while ANN indexing tames the geometry.",
                "info",
            ),
            exercise(
                "Compute the cosine similarity between u = [1, 0, 1] and v = [1, 1, 0]. "
                "Show the dot product, the two magnitudes, and the final value.",
                answer=(
                    "u . v = 1*1 + 0*1 + 1*0 = 1. ||u|| = sqrt(1+0+1) = sqrt(2). "
                    "||v|| = sqrt(1+1+0) = sqrt(2). cos = 1 / (sqrt(2)*sqrt(2)) = 1/2 = 0.5."
                ),
                explanation=(
                    "Cosine similarity is the dot product divided by the product of the "
                    "magnitudes. Here it works out to exactly 0.5, i.e. a 60-degree angle "
                    "between the two vectors."
                ),
            ),
        ),

        # affect: frustrated
        section(
            "Design and Trace the Agent",
            5,
            text(
                "This final assessment asks you to combine everything: tools, memory, "
                "planning, a reasoning pattern, and RAG. It is intentionally demanding. "
                "Work through the trace exercise first, then test yourself with the "
                "capstone quiz, whose distractors each embed a subtle error that only the "
                "precise definitions from this course rule out."
            ),
            exercise(
                "Trace, step by step, how a RAG-backed ReAct agent answers: 'Per our "
                "returns policy, can I return item #7 bought 20 days ago?' The agent has "
                "tools search_policy(query) and get_order(id), plus long-term memory. "
                "List the Thought/Action/Observation steps until the final answer.",
                answer=(
                    "Thought: I need the policy and the order date. "
                    "Action: search_policy('return window days'). "
                    "Observation: 'Returns allowed within 30 days of purchase.' "
                    "Thought: Now I need when item #7 was bought. "
                    "Action: get_order(7). "
                    "Observation: {purchased: 20 days ago}. "
                    "Thought: 20 <= 30, so it is within the window. "
                    "Final answer: 'Yes — item #7 was bought 20 days ago and the policy "
                    "allows returns within 30 days.'"
                ),
                explanation=(
                    "The agent interleaves reasoning with two tool calls (ReAct). "
                    "search_policy is a RAG retrieval over the policy documents; get_order "
                    "fetches fresh private data. Only after both observations does the "
                    "model reason 20 <= 30 and answer. Note the retrieval grounds the rule "
                    "and the tool grounds the fact — neither alone suffices."
                ),
            ),
            quiz(
                "For that returns-policy agent, which design choice is CORRECT?",
                [
                    (
                        "Use cosine similarity to fetch the order record by its exact ID, "
                        "since embeddings handle all lookups.",
                        False,
                    ),
                    (
                        "Retrieve the policy text with embedding similarity search, but "
                        "fetch the order with an exact-ID tool call, because one is fuzzy "
                        "semantic lookup and the other is a precise keyed lookup.",
                        True,
                    ),
                    (
                        "Put the entire policy document and all orders into the context "
                        "window every turn to avoid any retrieval.",
                        False,
                    ),
                    (
                        "Skip tools entirely and let the model recall the policy and the "
                        "order date from its training data.",
                        False,
                    ),
                ],
                explanation=(
                    "The two lookups have different natures. Finding the relevant policy "
                    "passage is a fuzzy semantic match — embeddings and similarity search "
                    "shine. Fetching order #7 is an exact keyed lookup — you want a "
                    "get_order(id) tool, not cosine similarity, which would be both wrong "
                    "and unreliable for exact IDs. Stuffing everything into context wastes "
                    "the window and adds noise, and relying on training data fails for "
                    "fresh, private order data. Matching the retrieval mechanism to the "
                    "nature of the lookup is the core skill."
                ),
            ),
            reflection(
                "Look back across the whole course. Pick one design decision for an agent "
                "you might build — which tools, what memory split, which reasoning pattern, "
                "and whether RAG is needed — and justify each choice in two sentences."
            ),
        ),
    )
