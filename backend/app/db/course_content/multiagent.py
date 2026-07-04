"""Deep pilot course: "Multi-Agent Systems & Orchestration".

Authored with the course_content_helpers authoring API. Each section carries a
`# affect:` comment marking the affective state the section is designed to induce
in learners, so the platform can collect behavioural affect data against a known
design intent.
"""

from __future__ import annotations

from app.db.course_content_helpers import (
    course,
    module,
    lesson,
    section,
    text,
    code,
    mermaid,
    callout,
    quiz,
    exercise,
    reflection,
)


def build():
    return course(
        "Multi-Agent Systems & Orchestration",
        # description
        "A hands-on, ~60-minute deep dive into why we build systems out of many "
        "cooperating AI agents, how an orchestrator coordinates specialised workers, "
        "how agents exchange messages, and how we keep such systems reliable, "
        "measurable, and safe. You will meet the orchestrator-worker pattern, the "
        "hard distributed-systems theory behind consensus and Byzantine fault "
        "tolerance, and the practical craft of evaluating and safeguarding "
        "multi-agent deployments.",
        # objectives
        "By the end of this course you will be able to: (1) justify when multiple "
        "agents beat a single monolithic agent and explain specialisation; "
        "(2) design an orchestrator-worker system and choose between sequential, "
        "parallel, and hierarchical coordination; (3) describe agent message "
        "envelopes and communication patterns; (4) reason about consensus, the FLP "
        "impossibility result, and Byzantine fault tolerance (n >= 3f + 1); "
        "(5) evaluate agent systems across success, cost, safety, and autonomy; "
        "and (6) recognise reward hacking and specification gaming as safety risks.",
        60,
        _module_one(),
        _module_two(),
    )


# =============================================================================
# MODULE 1 — Coordinating Multiple Agents
# =============================================================================

def _module_one():
    return module(
        "Coordinating Multiple Agents",
        "Why one agent is often not enough, and how a coordinator turns a crowd of "
        "narrow specialists into a coherent problem-solving system. We cover the "
        "orchestrator-worker pattern, roles and specialisation, the mechanics of "
        "message passing, and the classic coordination topologies.",
        _lesson_why_and_orchestrator(),
        _lesson_roles_and_communication(),
        _lesson_coordination_patterns(),
    )


def _lesson_why_and_orchestrator():
    return lesson(
        "From One Agent to Many",
        "The motivation for multi-agent systems and the foundational "
        "orchestrator-worker pattern that structures most of them.",

        # affect: engaged
        section(
            "Why More Than One Agent? A Newsroom Analogy",
            4,
            text(
                "A single large language model prompted to 'do everything' behaves "
                "like a brilliant generalist who is asked, simultaneously, to "
                "research a topic, fact-check the sources, write the prose, design "
                "the layout, and proofread the result. It can do each task, but its "
                "attention is spread thin, its context window fills with unrelated "
                "material, and a mistake in one sub-task quietly contaminates the "
                "others. A multi-agent system splits that workload the way a "
                "newsroom does.\n\n"
                "Picture a newsroom. An editor decides what stories to run and "
                "assigns them. Reporters go out and gather facts. A fact-checker "
                "verifies claims against sources. A copy-editor polishes language. "
                "Nobody tries to be all four roles at once. Each person keeps a "
                "narrow, well-practised focus, and the editor stitches their "
                "outputs into a finished paper. That division of labour is exactly "
                "what a multi-agent system buys you: specialisation.\n\n"
                "Specialisation matters for three concrete reasons. First, focus: "
                "an agent given one job and one toolset carries a shorter, cleaner "
                "prompt and makes fewer errors. Second, parallelism: independent "
                "sub-tasks can run at the same time, so three reporters gather "
                "three stories concurrently rather than one generalist doing them "
                "in sequence. Third, isolation of failure: if the fact-checker "
                "produces garbage, the editor can re-run just that step instead of "
                "discarding the entire article."
            ),
            callout(
                "Rule of thumb: reach for multiple agents when a task decomposes "
                "into sub-tasks that need different tools, different expertise, or "
                "can run in parallel. If the task is genuinely single-threaded and "
                "small, one agent is simpler and cheaper.",
                "tip",
            ),
            text(
                "The cost of this power is coordination. The moment you have more "
                "than one agent, someone has to decide who does what, in what "
                "order, and how their partial results are combined. Getting that "
                "coordination right is the entire subject of this course. We begin "
                "with the most common structure for it: the orchestrator-worker "
                "pattern."
            ),
            quiz(
                "What is the primary benefit that motivates splitting a task "
                "across multiple specialised agents?",
                [
                    ("Specialisation: each agent keeps a narrow focus, which "
                     "reduces errors and enables parallelism", True),
                    ("It always uses fewer tokens than a single agent", False),
                    ("It removes the need for any coordination logic", False),
                    ("It guarantees the system can never fail", False),
                ],
                explanation="Multiple agents win through specialisation — narrow "
                "focus, parallel execution, and isolated failures. The trade-off is "
                "that you must now coordinate them.",
            ),
        ),

        # affect: engaged
        section(
            "The Orchestrator-Worker Pattern",
            5,
            text(
                "In the orchestrator-worker pattern, one agent — the orchestrator "
                "(sometimes called the coordinator, planner, or lead) — owns the "
                "overall goal. It decomposes the goal into sub-tasks, dispatches "
                "each sub-task to a worker agent, collects the results, and "
                "synthesises a final answer. The workers are specialists: each "
                "knows how to do one kind of job well and knows nothing about the "
                "larger plan.\n\n"
                "This is a deliberate information asymmetry. The orchestrator holds "
                "the plan and the global context; workers hold only the narrow "
                "context they need for their slice. That keeps each worker's prompt "
                "small and its behaviour predictable, and it means you can swap, "
                "scale, or retry any single worker without touching the rest of the "
                "system.\n\n"
                "The flow below shows a research assistant built this way. The "
                "orchestrator receives a question, fans the work out to a search "
                "worker, a summariser worker, and a citation worker, then gathers "
                "their outputs and writes the final report."
            ),
            mermaid(
                "flowchart TD\n"
                "    U[User goal] --> O[Orchestrator]\n"
                "    O -->|search sub-task| W1[Search worker]\n"
                "    O -->|summarise sub-task| W2[Summariser worker]\n"
                "    O -->|cite sources sub-task| W3[Citation worker]\n"
                "    W1 --> O\n"
                "    W2 --> O\n"
                "    W3 --> O\n"
                "    O --> R[Synthesised final report]"
            ),
            text(
                "Notice that every arrow returns to the orchestrator. The workers "
                "do not talk to each other directly in this basic pattern; the "
                "orchestrator is the hub through which all coordination flows. This "
                "star topology is easy to reason about and easy to debug, because "
                "there is exactly one place that knows the whole story.\n\n"
                "In practice most of the engineering effort in such a system does "
                "not go into the clever worker prompts. It goes into the "
                "orchestrator's planning logic and, above all, into the plumbing "
                "that routes messages and recovers from failures. The chart below "
                "shows where effort typically lands in a mature orchestrator-worker "
                "deployment."
            ),
            mermaid(
                "pie showData title Where engineering effort goes in an orchestrator-worker system\n"
                "    \"Orchestration & planning logic\" : 30\n"
                "    \"Message routing & plumbing\" : 25\n"
                "    \"Error handling & retries\" : 20\n"
                "    \"Worker prompts & tools\" : 15\n"
                "    \"Evaluation & monitoring\" : 10"
            ),
            callout(
                "The workers are the glamorous part, but the orchestration, "
                "plumbing, and error handling are where systems succeed or fail. "
                "Budget your time accordingly.",
                "info",
            ),
            quiz(
                "In the classic orchestrator-worker pattern, how do worker agents "
                "coordinate their results?",
                [
                    ("They send results back to the orchestrator, which "
                     "synthesises the final output", True),
                    ("Each worker broadcasts to every other worker directly", False),
                    ("Workers vote among themselves and pick a leader", False),
                    ("Workers write to a shared file with no coordinator", False),
                ],
                explanation="In the basic pattern the orchestrator is the hub: "
                "workers return to it, and it does the synthesis. Direct worker-to-"
                "worker links are a different, more complex topology.",
            ),
        ),
    )


def _lesson_roles_and_communication():
    return lesson(
        "Roles, Specialisation, and Talking Between Agents",
        "How agents are given identities and jobs, and the concrete mechanics of "
        "the messages they pass to one another.",

        # affect: engaged
        section(
            "Roles and Specialisation",
            4,
            text(
                "A role is the persistent identity and remit of an agent: its "
                "purpose, the tools it may use, the knowledge it is primed with, "
                "and the boundaries of what it is allowed to decide. Assigning a "
                "role is how you turn a general-purpose model into a specialist. "
                "The same underlying model can be a 'Researcher' in one instance "
                "and a 'Critic' in another purely by virtue of its system prompt, "
                "tools, and constraints.\n\n"
                "Good role design follows the single-responsibility principle "
                "borrowed from software engineering: each agent should have one "
                "clear reason to exist. A 'Researcher' gathers information; it does "
                "not also decide the final answer. A 'Critic' finds flaws; it does "
                "not rewrite the work itself. Keeping roles crisp makes each agent "
                "easier to prompt, test, and replace, and it makes the system's "
                "behaviour legible to the humans maintaining it.\n\n"
                "A useful design move is the researcher-critic pair. One agent "
                "proposes; a second agent, with a role explicitly framed as "
                "adversarial, tries to poke holes. The tension between them "
                "surfaces mistakes that a single agent, eager to agree with "
                "itself, would miss. This is the same reason newsrooms separate "
                "reporting from fact-checking."
            ),
            code(
                "# A role is mostly a system prompt + a toolset + constraints.\n"
                "researcher = Agent(\n"
                "    role=\"Researcher\",\n"
                "    system=\"You gather factual evidence. You never draw final \"\n"
                "           \"conclusions; you only report what the sources say.\",\n"
                "    tools=[web_search, fetch_page],\n"
                ")\n\n"
                "critic = Agent(\n"
                "    role=\"Critic\",\n"
                "    system=\"You are adversarial. Given a draft answer and its \"\n"
                "           \"evidence, list every unsupported claim and logical gap.\",\n"
                "    tools=[],  # the critic reasons, it does not act\n"
                ")",
                "python",
            ),
            reflection(
                "Think of a task you do that a single generalist assistant handles "
                "poorly. How would you split it into two or three roles? What is "
                "each role explicitly NOT allowed to do?"
            ),
        ),

        # affect: bored
        section(
            "Message Envelope Field Reference",
            5,
            text(
                "When agents communicate, they do not simply exchange free text. "
                "Each message is wrapped in an envelope: a structured record of "
                "metadata that lets the runtime route, order, deduplicate, trace, "
                "and audit the message. The following is an exhaustive field-by-"
                "field reference for a typical agent message envelope. Read it "
                "carefully; every field exists to solve a specific operational "
                "problem, and you will need most of them eventually."
            ),
            text(
                "message_id — a globally unique identifier (usually a UUID) for "
                "this specific message. Used for deduplication and for correlating "
                "logs.\n\n"
                "conversation_id — groups all messages belonging to the same task "
                "or dialogue. Every reply in a thread shares this id.\n\n"
                "correlation_id — links a response back to the exact request that "
                "caused it, so an orchestrator can match answers to the sub-tasks "
                "it dispatched.\n\n"
                "sender_id — the role or instance identifier of the agent that "
                "produced the message.\n\n"
                "recipient_id — the intended addressee; may be a specific agent, a "
                "role name, or a broadcast marker.\n\n"
                "reply_to — the message_id this message is a direct response to, "
                "forming a reply chain.\n\n"
                "timestamp — the wall-clock time the message was created, in "
                "ISO 8601 UTC. Used for ordering and for latency measurement.\n\n"
                "sequence_number — a monotonically increasing per-sender counter, "
                "used to detect gaps or reordering when timestamps are unreliable.\n\n"
                "message_type — an enum such as request, response, event, error, "
                "or heartbeat, telling the receiver how to interpret the payload.\n\n"
                "content_type — the MIME-like type of the payload body, e.g. "
                "application/json or text/plain.\n\n"
                "payload — the actual body of the message: the instruction, the "
                "result, or the event data.\n\n"
                "priority — an integer hint (e.g. 0 low to 9 high) the scheduler "
                "may use to order delivery.\n\n"
                "ttl — time-to-live in seconds; after this the message may be "
                "discarded as stale rather than acted upon.\n\n"
                "retry_count — how many times delivery or processing of this "
                "message has already been attempted.\n\n"
                "trace_id — a distributed-tracing identifier spanning the whole "
                "request across every agent it touches.\n\n"
                "span_id — the tracing identifier for this single hop within the "
                "larger trace.\n\n"
                "schema_version — the version of the payload schema, so receivers "
                "can handle evolving message formats.\n\n"
                "signature — an optional cryptographic signature authenticating "
                "the sender and protecting payload integrity."
            ),
            text(
                "None of these fields is glamorous, and in a demo you can ignore "
                "almost all of them. In production, the absence of any one of them "
                "eventually manifests as a bug: without correlation_id you cannot "
                "match answers to questions; without ttl a stuck message is retried "
                "forever; without trace_id a failure is impossible to diagnose "
                "across agents. The envelope is boring precisely because it is "
                "infrastructure — invisible when it works, catastrophic when it is "
                "missing."
            ),
            callout(
                "Field reference tables like this are worth bookmarking, not "
                "memorising. Recognise the categories — identity, routing, "
                "ordering, lifecycle, tracing, security — and look up specifics "
                "when you implement.",
                "info",
            ),
            quiz(
                "Which envelope field lets an orchestrator match a worker's "
                "response to the specific request that produced it?",
                [
                    ("correlation_id", True),
                    ("priority", False),
                    ("content_type", False),
                    ("schema_version", False),
                ],
                explanation="correlation_id links a response back to its "
                "originating request. conversation_id groups a whole thread; "
                "correlation_id pairs one request with one answer.",
            ),
        ),
    )


def _lesson_coordination_patterns():
    return lesson(
        "Coordination Patterns",
        "The classic topologies for arranging how agents hand work to one another: "
        "sequential, parallel, and hierarchical.",

        # affect: engaged
        section(
            "Sharing State: Blackboards and Message Queues",
            4,
            text(
                "Agents that only pass point-to-point messages can become tightly "
                "coupled — each must know exactly who to talk to next. Two "
                "decoupling mechanisms let agents coordinate through shared state "
                "instead of direct addressing, and choosing between them shapes how "
                "your whole system scales.\n\n"
                "A blackboard is a shared workspace that every agent can read from "
                "and write to. The name comes from the metaphor of experts standing "
                "around a chalkboard: any specialist who sees something they can "
                "contribute writes it up, and the growing board triggers the next "
                "contribution. In an agent system the blackboard might hold the "
                "evolving draft, the accumulated evidence, and a task list. Agents "
                "watch it, act when relevant state appears, and post their results "
                "back. This is powerful because agents need not know one another at "
                "all — they only know the board — but it demands careful "
                "concurrency control so two agents do not clobber the same cell.\n\n"
                "A message queue decouples in time rather than in address. A "
                "producer agent drops a task onto a queue; any available consumer "
                "agent picks it up when it is free. This gives you natural load "
                "balancing, back-pressure when consumers fall behind, and "
                "durability if the queue persists messages. It is the backbone of "
                "large fan-out systems, where you cannot afford to block a producer "
                "while a slow consumer works."
            ),
            callout(
                "Blackboard = shared space (decouples WHO). Queue = buffered pipe "
                "(decouples WHEN). Many real systems use both: a durable queue for "
                "dispatch and a blackboard for the shared, evolving result.",
                "tip",
            ),
            quiz(
                "Which mechanism primarily decouples agents in TIME, letting a slow "
                "consumer process work without blocking the producer?",
                [
                    ("A message queue", True),
                    ("A blackboard", False),
                    ("A correlation_id", False),
                    ("A quorum", False),
                ],
                explanation="A queue buffers work so producers and consumers run at "
                "their own pace (time decoupling). A blackboard decouples who talks "
                "to whom (address decoupling).",
            ),
        ),

        # affect: engaged
        section(
            "When Agents Fail: Retries, Timeouts, and Idempotency",
            4,
            text(
                "In any system with more than one agent, partial failure is the "
                "normal case, not the exception. A worker crashes mid-task, a tool "
                "call times out, a network hiccup drops a message. A robust "
                "orchestrator treats every dispatch as something that might not "
                "come back, and designs for recovery from the start.\n\n"
                "Three techniques form the core toolkit. Timeouts bound how long "
                "the orchestrator waits for a worker before giving up, so one stuck "
                "agent cannot freeze the whole task. Retries re-dispatch a failed "
                "sub-task, often with exponential backoff — waiting 1s, then 2s, "
                "then 4s — so a briefly overloaded worker gets breathing room "
                "instead of a retry storm. A circuit breaker goes further: after "
                "repeated failures from one worker it stops sending traffic there "
                "entirely for a cooling-off period, protecting the system from a "
                "persistently sick component.\n\n"
                "Retries only work if the operation is idempotent — safe to run "
                "more than once with the same effect as running it once. Reading a "
                "web page is naturally idempotent; sending an email or charging a "
                "card is not. To retry non-idempotent actions safely, attach an "
                "idempotency key (often the message_id) so the receiver can detect "
                "and ignore a duplicate rather than acting on it twice."
            ),
            code(
                "def dispatch_with_retry(worker, task, max_attempts=3, timeout=30):\n"
                "    for attempt in range(max_attempts):\n"
                "        try:\n"
                "            # idempotency_key lets the worker dedupe retries\n"
                "            return worker.run(task, timeout=timeout,\n"
                "                              idempotency_key=task.id)\n"
                "        except (TimeoutError, WorkerError):\n"
                "            if attempt == max_attempts - 1:\n"
                "                raise\n"
                "            backoff = 2 ** attempt  # 1s, 2s, 4s\n"
                "            sleep(backoff)",
                "python",
            ),
            quiz(
                "Why is idempotency a prerequisite for safely retrying a "
                "sub-task?",
                [
                    ("Because a retry may execute the operation more than once, and "
                     "idempotency guarantees repeated execution has the same effect "
                     "as a single execution", True),
                    ("Because idempotency makes the operation run faster", False),
                    ("Because non-idempotent operations cannot time out", False),
                    ("Because it removes the need for timeouts entirely", False),
                ],
                explanation="A retry can cause the same operation to run twice. If "
                "the operation is idempotent, the duplicate is harmless; if not, "
                "you need an idempotency key so the receiver ignores the duplicate.",
            ),
        ),

        # affect: engaged
        section(
            "Sequential, Parallel, and Hierarchical Coordination",
            5,
            text(
                "Once you have several agents, you must decide how their work is "
                "arranged in time and authority. Three patterns cover the vast "
                "majority of real systems, and most complex systems are "
                "combinations of them.\n\n"
                "Sequential (pipeline) coordination chains agents so that each "
                "one's output is the next one's input: research, then draft, then "
                "edit. It is simple and easy to debug, and it is the right choice "
                "when each stage genuinely depends on the previous stage's result. "
                "Its weakness is latency — everything runs one after another — and "
                "brittleness, because a failure early in the chain wastes all the "
                "downstream work.\n\n"
                "Parallel (fan-out/fan-in) coordination dispatches independent "
                "sub-tasks at the same time and then merges their results. Three "
                "search workers hitting three sources concurrently, followed by a "
                "single merge step, is the canonical example. It slashes latency "
                "when sub-tasks are truly independent, but it introduces the "
                "merge problem: what do you do when two workers return conflicting "
                "answers?\n\n"
                "Hierarchical coordination nests orchestrators. A top-level "
                "orchestrator delegates a large sub-goal to a mid-level "
                "orchestrator, which in turn commands its own pool of workers. This "
                "is how you scale beyond what one coordinator can plan, mirroring "
                "how a company has executives, managers, and staff. The cost is "
                "depth: every extra layer adds coordination overhead and another "
                "place for instructions to be garbled."
            ),
            mermaid(
                "flowchart LR\n"
                "    subgraph Sequential\n"
                "        A1[Research] --> A2[Draft] --> A3[Edit]\n"
                "    end\n"
                "    subgraph Parallel\n"
                "        B0[Dispatch] --> B1[Worker 1]\n"
                "        B0 --> B2[Worker 2]\n"
                "        B0 --> B3[Worker 3]\n"
                "        B1 --> B4[Merge]\n"
                "        B2 --> B4\n"
                "        B3 --> B4\n"
                "    end\n"
                "    subgraph Hierarchical\n"
                "        C0[Top orchestrator] --> C1[Sub-orchestrator]\n"
                "        C1 --> C2[Worker]\n"
                "        C1 --> C3[Worker]\n"
                "    end"
            ),
            callout(
                "Real systems mix these freely: a hierarchical system whose leaves "
                "run parallel fan-outs, each of which is internally a short "
                "sequential pipeline. Name the pattern at each layer.",
                "tip",
            ),
            quiz(
                "You have three sub-tasks that do not depend on one another and "
                "you want the lowest possible latency. Which coordination pattern "
                "fits best?",
                [
                    ("Parallel fan-out/fan-in", True),
                    ("Sequential pipeline", False),
                    ("A single agent doing all three in order", False),
                    ("Deep hierarchical delegation", False),
                ],
                explanation="Independent sub-tasks plus a latency goal is the "
                "textbook case for parallel fan-out, followed by a fan-in merge.",
            ),
            exercise(
                "A user asks an assistant to 'compare the privacy policies of "
                "three apps and recommend one.' Sketch which parts should be "
                "parallel and which must be sequential, and name the pattern of "
                "the whole.",
                "Fetch-and-summarise each of the three policies in PARALLEL "
                "(independent). Then a SEQUENTIAL merge/compare step, followed by a "
                "SEQUENTIAL recommendation step that depends on the comparison. The "
                "overall shape is parallel fan-out into a sequential tail — a "
                "fan-out/fan-in feeding a pipeline.",
                explanation="The three fetches share no dependencies, so they "
                "parallelise; comparison needs all three, and recommendation needs "
                "the comparison, so those stages are sequential.",
            ),
        ),
    )


# =============================================================================
# MODULE 2 — Reliability, Evaluation & Safety
# =============================================================================

def _module_two():
    return module(
        "Reliability, Evaluation & Safety",
        "Coordinating agents is only half the battle. This module confronts the "
        "hard parts: reaching agreement when components can fail or lie (consensus "
        "and Byzantine fault tolerance), computing how much fault tolerance you "
        "actually have, measuring whether a multi-agent system is any good, and "
        "keeping it safe from reward hacking and specification gaming.",
        _lesson_consensus_bft(),
        _lesson_eval_safety(),
    )


def _lesson_consensus_bft():
    return lesson(
        "Consensus and Byzantine Fault Tolerance",
        "The distributed-systems theory that governs when a group of agents can "
        "reliably agree — and the unforgiving arithmetic of tolerating faulty or "
        "malicious members.",

        # affect: confused
        section(
            "Consensus, FLP Impossibility, and Quorums",
            5,
            text(
                "When multiple agents must agree on a single value — which answer "
                "to return, which action to commit, which of them is the leader — "
                "you have a consensus problem. Formally, a consensus protocol must "
                "satisfy three properties simultaneously. Agreement: no two "
                "correct processes decide different values. Validity (integrity): "
                "the decided value was actually proposed by some process. "
                "Termination (liveness): every correct process eventually decides. "
                "These look innocuous; they are not.\n\n"
                "The Fischer-Lynch-Paterson (FLP) impossibility result, proved in "
                "1985, states that in an asynchronous message-passing system there "
                "is no deterministic protocol that guarantees all three properties "
                "if even a single process may crash. The obstruction is that in a "
                "fully asynchronous model you cannot distinguish a crashed process "
                "from an arbitrarily slow one, so any protocol that always "
                "terminates can be forced into an infinite run of "
                "indecision. Real systems escape FLP not by refuting it but by "
                "weakening a premise: they add partial synchrony (timeouts), or "
                "randomisation, or failure detectors, trading guaranteed "
                "termination for termination-with-high-probability.\n\n"
                "Practical protocols achieve agreement through quorums. A quorum is "
                "any subset of processes large enough that any two quorums must "
                "overlap in at least one process. With n processes, a simple "
                "majority quorum of size floor(n/2) + 1 has this intersection "
                "property: two majorities cannot be disjoint, so they cannot ratify "
                "conflicting decisions. Quorum intersection is the mechanical heart "
                "of Paxos and Raft. Layered on top is linearizability, the "
                "strongest consistency model, which requires that every operation "
                "appear to take effect atomically at some instant between its "
                "invocation and its response, consistent with real-time ordering — "
                "so the whole replicated system behaves as if it were a single, "
                "instantaneously updated register."
            ),
            callout(
                "If this feels dense, that is expected — this is graduate "
                "distributed-systems material compressed hard. The single "
                "load-bearing idea to hold onto: quorums must intersect, and "
                "asynchrony makes perfect agreement provably impossible.",
                "warning",
            ),
            text(
                "The situation gets strictly worse when processes may not merely "
                "crash but behave arbitrarily — sending different, contradictory, "
                "or maliciously crafted messages to different peers. These are "
                "Byzantine faults, named after the Byzantine Generals Problem. A "
                "crash-only quorum of majority size is no longer enough, because a "
                "single two-faced process can tell one half of the quorum one thing "
                "and the other half the opposite. Defeating Byzantine behaviour "
                "requires more redundancy, and the exact amount is fixed by a "
                "bound we derive next."
            ),
            quiz(
                "What does the FLP impossibility result actually say?",
                [
                    ("In an asynchronous system, no deterministic protocol "
                     "guarantees consensus (agreement, validity, and termination) "
                     "if even one process can crash", True),
                    ("Consensus is impossible under any conditions whatsoever", False),
                    ("A majority quorum can never intersect another majority", False),
                    ("Byzantine faults are impossible to tolerate at any n", False),
                ],
                explanation="FLP is specifically about asynchronous, deterministic "
                "consensus with the possibility of a single crash. Real systems "
                "sidestep it with timeouts, randomisation, or failure detectors — "
                "they do not violate it.",
            ),
        ),

        # affect: confused
        section(
            "Byzantine Fault Tolerance and the n >= 3f + 1 Bound",
            5,
            text(
                "To tolerate f Byzantine (arbitrarily faulty or malicious) "
                "processes, a system needs at least n >= 3f + 1 total processes. "
                "This is not a heuristic; it is a hard lower bound, and it is worth "
                "understanding why the coefficient is three rather than two.\n\n"
                "Sketch of the argument. To make progress a correct process must be "
                "able to reach a decision after hearing from n - f others, because "
                "up to f may be silent and it cannot afford to wait for them "
                "forever. Among those n - f responders, as many as f could be "
                "Byzantine and lying. So the number of genuinely correct, "
                "trustworthy responses a process can rely on is (n - f) - f = "
                "n - 2f. For the honest responses to strictly outnumber the "
                "malicious ones — so that truth wins any vote — we need "
                "n - 2f > f, which rearranges to n > 3f, i.e. n >= 3f + 1.\n\n"
                "The consequence is stark. Tolerating just one Byzantine fault "
                "(f = 1) requires n >= 4 processes. Tolerating two (f = 2) requires "
                "n >= 7. Tolerating three (f = 3) requires n >= 10. Byzantine fault "
                "tolerance therefore costs roughly three-fold replication per fault "
                "tolerated — far more expensive than the near-two-fold cost of "
                "crash-only tolerance, where n >= 2f + 1 suffices. This is the "
                "reason production systems reserve full BFT (e.g. PBFT-style "
                "protocols) for adversarial settings such as blockchains, and use "
                "cheaper crash-tolerant consensus (Raft, Paxos) everywhere else."
            ),
            mermaid(
                "flowchart TD\n"
                "    S[Need to tolerate f Byzantine faults] --> Q1{Crash-only or Byzantine?}\n"
                "    Q1 -->|Crash-only| C[n >= 2f + 1]\n"
                "    Q1 -->|Byzantine| B[n >= 3f + 1]\n"
                "    B --> E1[f=1 -> n>=4]\n"
                "    B --> E2[f=2 -> n>=7]\n"
                "    B --> E3[f=3 -> n>=10]"
            ),
            code(
                "def min_nodes_byzantine(f: int) -> int:\n"
                "    \"\"\"Minimum total nodes to tolerate f Byzantine faults.\"\"\"\n"
                "    return 3 * f + 1\n\n"
                "def max_byzantine_faults(n: int) -> int:\n"
                "    \"\"\"Given n nodes, the largest f the system can tolerate.\"\"\"\n"
                "    return (n - 1) // 3\n\n"
                "# Sanity checks:\n"
                "# min_nodes_byzantine(1) == 4\n"
                "# min_nodes_byzantine(2) == 7\n"
                "# max_byzantine_faults(7) == 2\n"
                "# max_byzantine_faults(9) == 2  (9 is NOT enough for f=3)",
                "python",
            ),
            callout(
                "Watch the boundary carefully: n >= 3f + 1 means f = floor((n-1)/3). "
                "With n = 9 you get f = 2, not 3 — because 3f+1 for f=3 is 10. Off-"
                "by-one errors here are the classic trap.",
                "warning",
            ),
        ),

        # affect: confused
        section(
            "Leader Election, Terms, and Split-Brain",
            5,
            text(
                "Many consensus protocols avoid the cost of everyone-agrees-with-"
                "everyone by electing a single leader that sequences all decisions, "
                "with the followers merely replicating what the leader commits. "
                "This is the strategy of Raft and of multi-Paxos, and it turns the "
                "hard problem of continuous agreement into the narrower problem of "
                "agreeing on who is in charge right now.\n\n"
                "Leadership is scoped to a term (Raft) or ballot number (Paxos): a "
                "monotonically increasing integer that stamps every leader's reign. "
                "When a follower stops hearing heartbeats from the leader within an "
                "election timeout, it increments the term, becomes a candidate, and "
                "solicits votes. A node grants at most one vote per term, and a "
                "candidate that collects a majority quorum becomes leader for that "
                "term. Because terms are strictly increasing and votes are unique "
                "per term, two leaders cannot both win the same term — the "
                "quorum-intersection argument again does the work.\n\n"
                "The failure this guards against is split-brain: a partition in "
                "which two subsets of nodes each believe they hold a live leader and "
                "each accept writes, silently diverging into two contradictory "
                "histories. Term numbers and majority quorums prevent it, because a "
                "would-be leader in a minority partition can never assemble a "
                "quorum, and any stale leader whose term is superseded is rejected "
                "the instant it contacts a node that has seen a higher term. The "
                "price is availability: a partition that leaves no side with a "
                "majority has no leader at all, and the system correctly refuses to "
                "make progress rather than risk divergence — the CAP trade-off made "
                "concrete."
            ),
            callout(
                "If leader election, terms, heartbeats, and split-brain feel like a "
                "lot at once, they are — this is the machinery behind Raft compressed "
                "into three paragraphs. The one invariant that ties it together: a "
                "leader needs a majority quorum, and majorities cannot coexist in "
                "two partitions.",
                "warning",
            ),
            quiz(
                "In a Raft-style protocol, what structurally prevents two nodes "
                "from both acting as leader in the same term during a network "
                "partition?",
                [
                    ("Each node votes at most once per term and a leader needs a "
                     "majority quorum, so two majorities cannot both form", True),
                    ("Leaders broadcast directly to every follower with no quorum "
                     "needed", False),
                    ("The FLP result guarantees a unique leader", False),
                    ("Byzantine tolerance requires n >= 3f + 1 leaders", False),
                ],
                explanation="A leader must win a majority quorum for a given term, "
                "and each node grants only one vote per term. Since two majorities "
                "must intersect, they cannot both elect a leader in the same term — "
                "so a minority partition simply gets no leader.",
            ),
        ),

        # affect: frustrated
        section(
            "Fault-Tolerance Diagnosis: A Demanding Assessment",
            5,
            text(
                "This assessment is deliberately unforgiving. Every question "
                "depends on the exact arithmetic of n >= 3f + 1 (Byzantine) and "
                "n >= 2f + 1 (crash-only). There is no partial credit and the "
                "numbers are chosen to punish rounding the wrong way. Work each one "
                "on paper before answering; a plausible-looking guess will usually "
                "be wrong by one node."
            ),
            quiz(
                "A consortium runs a Byzantine-fault-tolerant ledger and requires "
                "tolerance of exactly f = 4 malicious nodes. What is the MINIMUM "
                "total number of nodes?",
                [
                    ("13", True),
                    ("12", False),
                    ("9", False),
                    ("16", False),
                ],
                explanation="n >= 3f + 1 = 3(4) + 1 = 13. Twelve gives only "
                "f = floor(11/3) = 3, which is insufficient. Nine is far too few.",
            ),
            quiz(
                "You operate a cluster of n = 20 nodes. Some may behave in "
                "arbitrarily malicious (Byzantine) ways. What is the MAXIMUM number "
                "of Byzantine faults you can guarantee to tolerate?",
                [
                    ("6", True),
                    ("7", False),
                    ("9", False),
                    ("10", False),
                ],
                explanation="f = floor((n - 1) / 3) = floor(19/3) = 6. Tolerating "
                "7 would need n >= 3(7)+1 = 22. Twenty nodes therefore cap you at "
                "six Byzantine faults, no matter how you wish otherwise.",
            ),
            exercise(
                "A team currently runs 7 nodes for a Byzantine-tolerant service. "
                "Their compliance auditor demands the system withstand DOUBLE the "
                "Byzantine faults it can withstand today. Compute (a) today's "
                "tolerated f, (b) the required new f, and (c) the minimum number of "
                "ADDITIONAL nodes they must provision. Show the arithmetic; do not "
                "round in your favour.",
                "(a) With n = 7: f = floor((7-1)/3) = floor(6/3) = 2. "
                "(b) Double is f = 4. "
                "(c) Required n >= 3(4)+1 = 13. They have 7, so they must add "
                "13 - 7 = 6 additional nodes. Answer: 6 more nodes.",
                explanation="Today's tolerance is f = 2 (not 3 — floor(6/3) = 2). "
                "Doubling gives f = 4, requiring 13 nodes total, hence 6 new nodes. "
                "A common wrong answer is to assume 7 nodes already tolerate 3 and "
                "conclude fewer nodes are needed.",
            ),
            exercise(
                "A crash-only (non-Byzantine) system has n = 10 nodes. A colleague "
                "claims 'ten nodes tolerate three failures either way.' For BOTH "
                "the crash-only bound (n >= 2f + 1) AND the Byzantine bound "
                "(n >= 3f + 1), compute the actual f for n = 10 and state whether "
                "the colleague is right.",
                "Crash-only: f = floor((10-1)/2) = floor(9/2) = 4, so 10 nodes "
                "tolerate 4 crashes. Byzantine: f = floor((10-1)/3) = floor(9/3) = "
                "3, so 10 nodes tolerate 3 Byzantine faults. The colleague is "
                "half-right by coincidence: '3' is correct only for the Byzantine "
                "case; the crash-only case actually tolerates 4, not 3.",
                explanation="The two bounds diverge: crash tolerance is cheaper "
                "(2f+1) so the same 10 nodes buy f=4, whereas Byzantine tolerance "
                "(3f+1) buys only f=3. 'Three either way' conflates the two.",
            ),
            callout(
                "If these felt punishing, that is the point — off-by-one errors in "
                "fault-tolerance math cause real outages and audit failures. The "
                "cure is mechanical: always write n >= 3f + 1 (or 2f + 1) first, "
                "then solve; never eyeball it.",
                "warning",
            ),
        ),
    )


def _lesson_eval_safety():
    return lesson(
        "Evaluation and Safety",
        "How to tell whether a multi-agent system actually works, the vocabulary "
        "of its metrics, and the safety failures — reward hacking and "
        "specification gaming — that lurk when agents optimise too well.",

        # affect: engaged
        section(
            "Evaluating Agent Systems: Four Dimensions",
            5,
            text(
                "A multi-agent system that produces impressive demos can still be a "
                "bad system. Rigorous evaluation looks along four largely "
                "independent dimensions, and improving one often degrades another, "
                "so you must measure them together rather than optimising a single "
                "headline number.\n\n"
                "Success (task quality): did the system actually accomplish the "
                "goal, correctly and completely? Measured by task success rate, "
                "answer accuracy, or human-rated quality against a rubric. This is "
                "the dimension everyone remembers to measure.\n\n"
                "Cost (efficiency): what did success consume? Total tokens, dollar "
                "cost, wall-clock latency, and number of agent invocations. A "
                "system that answers correctly but fans out to forty agents and "
                "costs ten dollars per query may be worse than a simpler one.\n\n"
                "Safety: how often, and how badly, does the system do something "
                "harmful, wrong-with-confidence, or out-of-policy? Measured by "
                "harmful-output rate, policy-violation rate, and severity of the "
                "worst observed failure — not just the average.\n\n"
                "Autonomy: how much of the work did the system do without a human "
                "stepping in? Measured by human-intervention rate or the fraction "
                "of tasks completed end-to-end unaided. Higher autonomy is only "
                "good if success and safety hold up as you remove the human."
            ),
            mermaid(
                "pie showData title Illustrative evaluation profile of an agent system\n"
                "    \"Success rate\" : 82\n"
                "    \"Cost efficiency\" : 60\n"
                "    \"Safety compliance\" : 91\n"
                "    \"Autonomy\" : 47"
            ),
            text(
                "Read the profile above as four separate gauges, not a total. This "
                "hypothetical system is safe and fairly successful, but it is "
                "expensive and needs frequent human help — a mature but not-yet-"
                "autonomous system. The right next investment is obvious from the "
                "chart: push autonomy up without letting the safety bar drop. Charts "
                "like this keep teams honest, because a single 'it works great' "
                "claim hides exactly the trade-offs that decide whether a system is "
                "deployable."
            ),
            quiz(
                "A system's task success rate rises from 80% to 88%, but its cost "
                "per task triples and its human-intervention rate is unchanged. "
                "Along which dimension has it clearly regressed?",
                [
                    ("Cost efficiency", True),
                    ("Success", False),
                    ("Autonomy", False),
                    ("Safety", False),
                ],
                explanation="Success improved and autonomy is unchanged; tripling "
                "cost per task is a clear regression on the cost/efficiency "
                "dimension. This is why the four dimensions must be tracked "
                "together.",
            ),
        ),

        # affect: bored
        section(
            "Glossary of Evaluation Metrics",
            4,
            text(
                "For reference, here is a plain glossary of the metrics you will "
                "encounter when evaluating agent systems. It is intentionally "
                "comprehensive and dry; treat it as a lookup table rather than "
                "narrative reading."
            ),
            text(
                "Task success rate — fraction of tasks completed correctly, per a "
                "defined criterion.\n\n"
                "Pass@k — probability that at least one of k independent attempts "
                "succeeds; common for code and reasoning tasks.\n\n"
                "Exact match — fraction of outputs identical to a reference answer.\n\n"
                "F1 score — harmonic mean of precision and recall, for tasks scored "
                "on overlap rather than exact identity.\n\n"
                "Tokens per task — mean total input plus output tokens consumed to "
                "finish one task.\n\n"
                "Cost per task — mean monetary cost per completed task.\n\n"
                "Latency (p50 / p95 / p99) — median and tail response times; tails "
                "matter more than the median for user experience.\n\n"
                "Agent invocations per task — number of individual agent calls made "
                "to complete one task; a proxy for orchestration overhead.\n\n"
                "Tool-call success rate — fraction of tool invocations that return "
                "usable results rather than errors.\n\n"
                "Human-intervention rate — fraction of tasks requiring a human to "
                "step in; inversely related to autonomy.\n\n"
                "Harmful-output rate — fraction of outputs judged harmful or "
                "policy-violating.\n\n"
                "Hallucination rate — fraction of outputs containing fabricated, "
                "unsupported claims.\n\n"
                "Refusal rate — fraction of requests the system declines; high "
                "values may indicate over-caution.\n\n"
                "Time-to-first-token — latency until the first output token, a key "
                "perceived-responsiveness metric.\n\n"
                "Throughput — completed tasks per unit time under load.\n\n"
                "Regret — cumulative gap between the system's outcomes and the best "
                "achievable outcomes, used in sequential-decision settings."
            ),
            quiz(
                "Which metric best captures tail-latency user experience rather "
                "than typical-case speed?",
                [
                    ("p99 latency", True),
                    ("Median (p50) latency", False),
                    ("Exact match", False),
                    ("Refusal rate", False),
                ],
                explanation="p99 latency describes the slowest 1% of requests — the "
                "tail — which often dominates perceived reliability. The median "
                "hides those bad cases.",
            ),
        ),

        # affect: confused
        section(
            "Reward Hacking, Specification Gaming, and Safety",
            5,
            text(
                "The deepest safety failures in agent systems are not bugs in the "
                "usual sense; they are the agent doing exactly what you rewarded, "
                "which turns out not to be what you meant. This gap between the "
                "objective you specified and the objective you intended is the root "
                "of reward hacking and specification gaming, and it becomes more "
                "dangerous, not less, as agents become more capable.\n\n"
                "Specification gaming is the general phenomenon: an agent satisfies "
                "the literal specification of its goal while violating its intent. "
                "The canonical examples are almost comedic. A simulated boat-racing "
                "agent, rewarded for score rather than for finishing, discovered it "
                "could loop forever through a cluster of respawning bonus targets, "
                "scoring endlessly while never completing the race. A cleaning "
                "agent rewarded for 'seeing no mess' learned to switch off its own "
                "camera. In each case the specification was met perfectly and the "
                "intent was betrayed completely.\n\n"
                "Reward hacking is specification gaming aimed squarely at the "
                "reward signal or its measurement. Instead of achieving the "
                "outcome, the agent corrupts the thing that measures the outcome: "
                "it games the grader, exploits a bug in the evaluation harness, or "
                "manipulates the very metric used to judge it. In a multi-agent "
                "setting this is especially insidious when one agent's job is to "
                "evaluate another — an LLM-as-judge can be flattered, prompt-"
                "injected, or argued into a high score by a persuasive worker that "
                "has learned what the judge rewards.\n\n"
                "Two structural forces make this worse. Goodhart's law states that "
                "when a measure becomes a target, it ceases to be a good measure — "
                "any proxy you optimise hard enough diverges from the true goal it "
                "stood in for. And instrumental convergence observes that a wide "
                "range of final goals implies similar intermediate sub-goals — "
                "acquiring resources, resisting shutdown, gaming oversight — so "
                "sufficiently capable optimisers tend to pursue exactly the "
                "behaviours that undermine the humans supervising them, regardless "
                "of what their ultimate objective happens to be."
            ),
            callout(
                "The unsettling takeaway: these are not failures of a broken agent "
                "but of a working one optimising a subtly wrong objective. You "
                "cannot patch them purely with better prompts; you need "
                "adversarial evaluation, held-out graders, human oversight on "
                "high-stakes actions, and objectives designed to resist gaming.",
                "warning",
            ),
            quiz(
                "An LLM-judge agent scores a worker's answers. Over time the worker "
                "learns to open every answer with 'As you correctly noted...' and "
                "its scores climb even though answer quality is flat. This is best "
                "described as:",
                [
                    ("Reward hacking / specification gaming — the worker games the "
                     "grader rather than improving the outcome", True),
                    ("A consensus failure covered by the FLP result", False),
                    ("A Byzantine fault requiring n >= 3f + 1 nodes", False),
                    ("A latency regression on the p99 metric", False),
                ],
                explanation="The worker is optimising the measurement (the judge's "
                "score) rather than the true objective (answer quality) — textbook "
                "reward hacking, and an illustration of Goodhart's law in a "
                "multi-agent evaluation loop.",
            ),
            reflection(
                "Consider an agent you would like to build. Write down its reward "
                "or success signal in one sentence, then spend two minutes as an "
                "adversary: how could an agent maximise that exact signal while "
                "completely failing your real intent? What held-out check would "
                "catch it?"
            ),
        ),

        # affect: engaged
        section(
            "Keeping Humans in the Loop",
            4,
            text(
                "The practical antidote to most of the failures in this module — "
                "wrong-but-confident answers, reward hacking, unbounded autonomy — "
                "is a well-placed human. But 'add a human' is not one design; it is "
                "a spectrum of oversight patterns, each trading autonomy for "
                "safety at a different point.\n\n"
                "Human-in-the-loop puts a person on the critical path: the agent "
                "proposes, and a human must approve before a high-stakes action "
                "executes. Think of an agent that drafts a refund but cannot issue "
                "it until a support lead clicks approve. It is the safest pattern "
                "and the slowest, so you reserve it for irreversible or costly "
                "actions.\n\n"
                "Human-on-the-loop keeps the person supervising rather than "
                "approving each step: the agent acts autonomously, but a human "
                "monitors a dashboard and can intervene, pause, or roll back. This "
                "preserves throughput while retaining a safety valve, and it pairs "
                "naturally with the autonomy metric from earlier — you are trading "
                "intervention rate for speed. The design question is always which "
                "actions deserve which level of oversight; a mature system routes "
                "low-risk actions to full autonomy and escalates only the "
                "consequential ones to a human, so attention lands where it "
                "matters."
            ),
            mermaid(
                "flowchart TD\n"
                "    A[Agent proposes action] --> R{Risk / reversibility?}\n"
                "    R -->|Low risk, reversible| X[Execute autonomously]\n"
                "    R -->|Medium risk| M[Human-on-the-loop: monitor, can override]\n"
                "    R -->|High risk, irreversible| H[Human-in-the-loop: require approval]\n"
                "    X --> L[Log for later audit]\n"
                "    M --> L\n"
                "    H --> L"
            ),
            quiz(
                "An agent can issue account deletions, which are irreversible. "
                "Which oversight pattern is the appropriate default for that "
                "action?",
                [
                    ("Human-in-the-loop: require explicit human approval before "
                     "the action executes", True),
                    ("Full autonomy with logging only", False),
                    ("Human-on-the-loop monitoring after the fact", False),
                    ("No oversight, but a higher timeout", False),
                ],
                explanation="Irreversible, high-consequence actions warrant "
                "human-in-the-loop approval on the critical path. Monitoring after "
                "the fact cannot undo a deletion.",
            ),
        ),
    )
