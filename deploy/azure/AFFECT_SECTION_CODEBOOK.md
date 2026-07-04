# Affect-Section Codebook — Pilot Courses

Maps each course section to the affect state it is designed to elicit. Section titles are
topic-natural so they do NOT bias participants; this codebook is the analysis key. Source of
truth: `backend/app/db/course_content/*.py` (see the `# affect:` comments). States: **engaged /
bored / confused / frustrated**.

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
| Consensus and Byzantine Fault Tolerance | Fault-Tolerance Diagnosis: A Demanding Assessment | **frustrated** |
| Evaluation and Safety | Evaluating Agent Systems: Four Dimensions | **engaged** |
| Evaluation and Safety | Glossary of Evaluation Metrics | **bored** |
| Evaluation and Safety | Reward Hacking, Specification Gaming, and Safety | **confused** |
| Evaluation and Safety | Keeping Humans in the Loop | **engaged** |
