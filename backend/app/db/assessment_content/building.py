"""Pre/post assessments for "Building AI Agents: Tools, Memory & Planning" — the study course.

THE DEPENDENT VARIABLE

This is the study's learning-outcome measure. Without it, control-vs-adaptive has nothing to
compare: affect data alone shows what the system detected, never whether it helped.

MATCHED-PAIR DESIGN

Every item exists twice — once in `pre`, once in `post` — testing the SAME construct with DIFFERENT
surface details (different scenario, different names, different numbers). Reusing an item verbatim
would make a gain score measure recall of that item rather than learning of the concept.
`pair_key` links the two, and `section_title` maps each to the section that teaches it, so gains can
be attributed to content rather than assumed.

ITEM CONSTRUCTION

Distractors are drawn from the misconceptions the course text explicitly corrects, not invented.
A distractor nobody would pick adds length without adding measurement: if every learner rules an
option out immediately, that option contributes nothing and the item is effectively 3-choice.

Difficulty deliberately varies. All-easy items ceiling out and hide any effect; all-hard items floor
out and do the same. Both destroy the ability to detect a difference between conditions.

COVERAGE

Weighted toward the sections annotated `# affect: confused` / `frustrated` in `course_content/
building.py`, because those are where adaptations fire — and therefore where a control-vs-adaptive
difference, if one exists, would appear.
"""

from __future__ import annotations

from app.db.assessment_content_helpers import assessment, option, question

MODULE_TITLE = "Giving Agents Capabilities"
PRE_TITLE = "Giving Agents Capabilities — Pre-Test"
POST_TITLE = "Giving Agents Capabilities — Post-Test"


def build_pre():
    return assessment(
        PRE_TITLE,
        "pre",
        question(
            "A language model is asked for today's exchange rate. Why can it not answer reliably "
            "from its own weights alone?",
            [
                option("Its knowledge is frozen at training time and cannot include today's data", True),
                option("It can only process text, not numbers"),
                option("Exchange rates are too complex for a neural network"),
                option("It would need a larger context window"),
            ],
            pair_key="tool-need",
            section_title="What a Tool Is and Why an Agent Needs One",
            explanation="A base model maps text to text using weights fixed at training time. "
                        "Live data requires a tool that fetches it.",
        ),
        question(
            "What is the primary purpose of a tool schema?",
            [
                option("To tell the model the tool's name, purpose and exact argument shape", True),
                option("To validate the tool's output before returning it"),
                option("To restrict which users may invoke the tool"),
                option("To cache tool results between calls"),
            ],
            pair_key="schema-purpose",
            section_title="Anatomy of a Tool Schema",
            explanation="The schema is passed to the model so it knows the menu of actions and how "
                        "to call each one correctly.",
        ),
        question(
            "In a tool-call round trip, which component actually executes the tool?",
            [
                option("Your application, which then feeds the result back to the model", True),
                option("The model, which runs the function internally"),
                option("The tool schema, which is executable"),
                option("The inference server, transparently"),
            ],
            pair_key="round-trip-executor",
            section_title="The Tool-Call Round Trip",
            explanation="Function calling is a loop. The model REQUESTS a call; the application "
                        "executes it and returns the observation.",
        ),
        question(
            "An agent already answers a question reliably without any tool. What is the main "
            "argument against adding a tool for it anyway?",
            [
                option("Each tool adds surface area to misuse, more failure modes and more schema to read", True),
                option("Tools always make responses slower than the latency budget allows"),
                option("Models cannot choose correctly between more than three tools"),
                option("Tool schemas must be regenerated whenever the model is updated"),
            ],
            pair_key="tool-liability",
            section_title="When (and When Not) to Give an Agent a Tool",
            explanation="A tool earns its place by adding a capability the model lacks, or by making "
                        "an unreliable behaviour reliable. Otherwise it is a liability.",
        ),
        question(
            "Why is free-text output unsuitable when a program must consume the model's answer?",
            [
                option("The wording varies between calls, so a parser built on it is fragile", True),
                option("Free text uses more tokens than JSON"),
                option("Models produce lower-quality reasoning in prose"),
                option("Free text cannot contain numbers reliably"),
            ],
            pair_key="freetext-fragility",
            section_title="Why Free Text Breaks Programs",
            explanation="'high priority', 'high-priority' and 'HIGH' all mean the same thing to a "
                        "human and break the same parser.",
        ),
        question(
            "Under grammar-constrained decoding, why can the model never emit invalid JSON?",
            [
                option("Tokens that cannot continue a grammar-valid string are masked before sampling", True),
                option("The output is validated after generation and regenerated if invalid"),
                option("The model is fine-tuned until it stops making JSON errors"),
                option("A post-processor repairs malformed JSON automatically"),
            ],
            pair_key="constrained-mechanism",
            section_title="Constrained Decoding and Grammars",
            explanation="Forbidden tokens have their logits driven to negative infinity before the "
                        "softmax, so their sampling probability is exactly zero.",
        ),
        question(
            "Constrained decoding masks tokens the model assigned probability to. Why does the "
            "output still read fluently?",
            [
                option("Masking removes only grammar-invalid continuations; preferences among the rest are unchanged", True),
                option("The model is retrained to prefer only valid tokens"),
                option("Fluency is restored by a separate rewriting pass"),
                option("The grammar is built from the model's own most likely outputs"),
            ],
            pair_key="constrained-fluency",
            section_title="Constrained Decoding and Grammars",
            explanation="It prunes the impossible rather than rewriting the model's judgement.",
        ),
        question(
            "Which distinction does the real work when designing an agent's memory?",
            [
                option("Short-term lives in the context window and disappears; long-term is stored externally and retrieved", True),
                option("Episodic memory is faster to read than semantic memory"),
                option("Procedural memory must always be stored as embeddings"),
                option("Working memory is a subtype of long-term memory"),
            ],
            pair_key="memory-core",
            section_title="Short-Term vs Long-Term Memory in Practice",
            explanation="The taxonomy is large, but this one split determines what to store where.",
        ),
        question(
            "What is the main trade-off of fixed-size chunking?",
            [
                option("It is trivial to implement but can split a coherent idea across two chunks", True),
                option("It preserves meaning perfectly but is computationally expensive"),
                option("It requires a language model to compute chunk boundaries"),
                option("It only works for documents under a fixed length"),
            ],
            pair_key="chunking-tradeoff",
            section_title="Chunking and Retention Strategies",
            explanation="Splitting every N characters ignores structure, so a sentence or argument "
                        "can be cut in half.",
        ),
        question(
            "A tool schema marks `priority` as an enum of low/medium/high, and `required` lists "
            "only `name`. What may the model legitimately return?",
            [
                option("An object with `name` but no `priority` at all", True),
                option("An object with `priority` set to 'urgent'"),
                option("An object with neither field"),
                option("An object with `priority` as a number"),
            ],
            pair_key="schema-required",
            section_title="Schema Edge Cases That Bite",
            explanation="`required` governs presence; `enum` governs the permitted values when the "
                        "field IS present. Omitting a non-required field is valid.",
        ),
    )


def build_post():
    return assessment(
        POST_TITLE,
        "post",
        question(
            "An agent is asked how many items are currently in a warehouse. Why can the model not "
            "answer this from its weights alone?",
            [
                option("Its knowledge is fixed at training time and cannot reflect current stock", True),
                option("Inventory counts exceed the model's numeric range"),
                option("The model cannot perform counting tasks"),
                option("The answer would require a longer context window"),
            ],
            pair_key="tool-need",
            section_title="What a Tool Is and Why an Agent Needs One",
            explanation="Same reason as any live-data question: weights are frozen, so a tool must "
                        "fetch the current value.",
        ),
        question(
            "A developer writes a tool schema. What is that schema chiefly for?",
            [
                option("Describing the tool's name, behaviour and argument shape so the model can call it correctly", True),
                option("Logging every invocation for later auditing"),
                option("Converting the tool's response into natural language"),
                option("Deciding which model version may use the tool"),
            ],
            pair_key="schema-purpose",
            section_title="Anatomy of a Tool Schema",
            explanation="It is the menu of actions plus the calling convention for each.",
        ),
        question(
            "During a function-calling loop, the model emits a tool call. What happens next?",
            [
                option("The application runs the tool and returns its output to the model as an observation", True),
                option("The model executes the call and continues"),
                option("The runtime resolves the call against the schema and returns a value"),
                option("The conversation ends and the tool output is shown to the user"),
            ],
            pair_key="round-trip-executor",
            section_title="The Tool-Call Round Trip",
            explanation="Your application is the middle layer; the model only requests.",
        ),
        question(
            "A team proposes adding a fifth tool that duplicates something the agent already does "
            "well. What is the strongest objection?",
            [
                option("Every added tool widens the surface for misuse and adds schema the model must read", True),
                option("Five tools exceed the maximum most APIs allow"),
                option("Duplicate tools cause the model to call both simultaneously"),
                option("Each tool requires its own fine-tuning run"),
            ],
            pair_key="tool-liability",
            section_title="When (and When Not) to Give an Agent a Tool",
            explanation="Tools are a liability as well as a capability; adding one needs a reason.",
        ),
        question(
            "A program parses the model's prose reply to extract a status field. Why is this fragile?",
            [
                option("Phrasing varies between calls, so the same meaning arrives in forms the parser misses", True),
                option("Prose replies are truncated more often than structured ones"),
                option("The model reasons less accurately when writing prose"),
                option("Prose cannot express categorical values"),
            ],
            pair_key="freetext-fragility",
            section_title="Why Free Text Breaks Programs",
            explanation="Stable meaning, unstable wording — which is exactly what a parser cannot "
                        "absorb.",
        ),
        question(
            "What mechanism guarantees a constrained-decoding runtime cannot produce malformed JSON?",
            [
                option("At each step, tokens that cannot extend a grammar-valid string are excluded from sampling", True),
                option("Invalid outputs are detected afterwards and the call is retried"),
                option("The schema is embedded in the prompt so the model complies"),
                option("A repair pass fixes structural errors before returning"),
            ],
            pair_key="constrained-mechanism",
            section_title="Constrained Decoding and Grammars",
            explanation="Malformed strings are simply not in the language the grammar generates.",
        ),
        question(
            "If constrained decoding suppresses tokens the model wanted, why is the result not "
            "distorted or stilted?",
            [
                option("Only invalid continuations are removed; the relative ranking of valid ones is untouched", True),
                option("A fluency model post-processes the constrained output"),
                option("The constraint is applied only to the first token of each field"),
                option("The model is trained jointly with the grammar"),
            ],
            pair_key="constrained-fluency",
            section_title="Constrained Decoding and Grammars",
            explanation="Pruning the impossible is not the same as overriding the model's judgement.",
        ),
        question(
            "Stripped of taxonomy, what is the operative distinction in agent memory design?",
            [
                option("Whether the information lives in the context window or in external storage retrieved on demand", True),
                option("Whether the memory is written by the user or by the agent"),
                option("Whether the memory is stored as text or as vectors"),
                option("Whether the memory survives a model upgrade"),
            ],
            pair_key="memory-core",
            section_title="Short-Term vs Long-Term Memory in Practice",
            explanation="Everything else is refinement on top of that split.",
        ),
        question(
            "Why might a team reject fixed-size chunking despite its simplicity?",
            [
                option("A single coherent idea can be split across a chunk boundary, harming retrieval", True),
                option("It cannot be parallelised across documents"),
                option("It produces chunks too large for most embedding models"),
                option("It requires labelled training data"),
            ],
            pair_key="chunking-tradeoff",
            section_title="Chunking and Retention Strategies",
            explanation="Splitting on length ignores meaning; the cut can land mid-argument.",
        ),
        question(
            "A schema defines `status` as an enum of open/closed and lists only `id` as required. "
            "Which response is schema-valid?",
            [
                option("`{\"id\": \"a1\"}` with no `status` field", True),
                option("`{\"id\": \"a1\", \"status\": \"pending\"}`"),
                option("`{\"status\": \"open\"}` with no `id`"),
                option("`{\"id\": \"a1\", \"status\": true}`"),
            ],
            pair_key="schema-required",
            section_title="Schema Edge Cases That Bite",
            explanation="A non-required field may be omitted entirely; if present it must match the "
                        "enum and type.",
        ),
    )
