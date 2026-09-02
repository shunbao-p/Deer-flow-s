# PRD: Legal RAG Migration Direction

## Document responsibility

This document is the approved direction baseline: it defines the target relationship, architectural boundary, capability-preservation rules, database ownership, major migration seams, non-goals, and architecture stop conditions. It intentionally does not define final field schemas, exhaustive file diffs, concrete timeout values, command sequences, or test implementation details. Those belong to the separate implementation plan derived from this direction and the current code of both repositories.

## Requirements summary

Integrate the existing Legal RAG as an on-demand legal augmentation capability under Deer-flow-s, while keeping Deer-flow-s as the sole conversation orchestrator and final answer surface. Preserve the Legal chain with minimal adaptation and avoid importing its standalone UI/session shell.

## RALPLAN-DR summary

### Principles

1. Deer is主, Legal RAG is辅.
2. Reuse the mature chain before considering rewrites.
3. Keep the integration boundary thin and structured.
4. Preserve evidence and refine semantics end-to-end.
5. Non-legal behavior must remain unchanged.

### Decision drivers

1. Preserve Legal RAG capability without dependency-driven rewrites.
2. Ensure legal queries trigger reliably while avoiding false activation for ordinary conversations.
3. Keep Deer responsible for conversation context, user interaction, and final response generation.

### Viable options

#### Option A: In-process module transplant

- Move `rag_modules` into the Deer backend and call them directly.
- Pros: one process and direct Python contracts.
- Cons: dependency generation conflicts, heavy model/database initialization inside LangGraph runtime, tighter lifecycle coupling, larger adaptation surface.

#### Option B: Internal Legal RAG service + Deer built-in tool (favored)

- Preserve the Legal core in an internal service boundary and expose one stable augmentation contract to Deer.
- Pros: maximum reuse, dependency isolation, independent health/degradation, small Deer changes, easy rollback.
- Cons: one internal network hop and an additional runtime component.

#### Option C: Deep LangGraph node/middleware transplant

- Split Legal stages into Deer graph nodes and embed them in the lead-agent workflow.
- Pros: maximum orchestration control and observability within one graph.
- Cons: largest rewrite, high coupling, risks changing Deer’s main loop and weakening existing Legal semantics.

## Favored architecture direction

Adopt Option B with a thin three-layer integration:

1. **Outer legal-domain trigger in Deer**
   - Decides only whether legal augmentation is needed.
   - It must not duplicate Legal's internal traditional/GraphRAG/combined strategy router.
   - Start with normal agent tool semantics plus a concise prompt policy; add a lightweight routing guard only if the frozen trigger evaluation proves systematic misses.

2. **Legal augmentation adapter**
   - Reuses existing Legal orchestration and returns one structured `LegalAugmentationResult`.
   - Result includes route analysis, evidence state, ranked documents, supported/weak/unsupported claims, fallbacks, and a legally refined draft/context.
   - The contract is explicitly versioned. `documents + evidence + refine.claims` are the legal-authority fields; Legal's `answer` is only an evidence-checked draft/context, never the sole source of truth.
   - Legal API/UI conversation ownership is not migrated.

3. **Deer final generation**
   - Deer consumes the evidence bundle in the same conversation turn.
   - It uses supported claims and sources as hard grounding, weak claims as qualified material, and excludes unsupported claims.
   - Deer remains responsible for tone, conversation continuity, tool orchestration, and final response.

## Target repository placement

The migration should follow the current Deer-flow-s repository boundaries instead of inserting the whole Legal project into the LangGraph package. The existing empty `services/` root and `backend/packages/harness/deerflow/legal/` package provide natural homes for the two sides of the boundary.

```text
Deer-flow-s/
├── backend/
│   ├── packages/harness/deerflow/
│   │   ├── agents/lead_agent/
│   │   │   └── prompt.py                  # legal-use and evidence-consumption policy only
│   │   ├── config/
│   │   │   └── legal_rag_config.py        # enabled/base_url/timeout configuration
│   │   ├── legal/
│   │   │   ├── contracts.py               # versioned request/result models
│   │   │   └── client.py                  # thin internal-service client
│   │   └── tools/builtins/
│   │       └── legal_augmentation_tool.py  # the one Deer-visible capability
│   └── tests/                              # Deer contract/tool/trigger tests
├── services/
│   └── legal_rag/
│       ├── api/
│       │   ├── app.py                      # health + stateless augmentation endpoint
│       │   ├── schemas.py                  # service-side v1 contract
│       │   └── service.py                  # singleton startup/prewarm/augmentation adapter
│       ├── rag_modules/                    # migrated with minimal internal change
│       ├── scripts/ingest/                 # existing law-data ingestion utilities
│       ├── data/eval/                      # frozen Legal regression samples
│       ├── main.py                         # AdvancedGraphRAGSystem and ask_question_payload
│       ├── config.py                       # existing Neo4j/Milvus/retrieval/model settings
│       ├── requirements.txt                # isolated Legal dependency set
│       └── Dockerfile
├── docker/docker-compose.yaml              # legal-rag runtime and DB endpoint wiring
└── config.example.yaml                     # Deer-side legal_rag client settings
```

Placement rules:

- Migrate the Legal core from `/Users/yuh/Desktop/项目/Legal-consulting-expert/main.py`, `config.py`, and `rag_modules/` into `services/legal_rag/` without reorganizing algorithms merely to match Deer code style.
- Reuse the useful lifecycle parts of Legal's `api/service.py:68-158` (singleton initialization, health, reranker prewarm), but expose a stateless augmentation call that reaches `AdvancedGraphRAGSystem.ask_question_payload` directly. The Legal chat/session and frontend shell do not enter the Deer runtime.
- Keep only Deer-facing contracts and the HTTP client under `deerflow/legal/`; do not install Neo4j, Milvus, embedding, reranker, or the Legal LangChain dependency stack into the Deer harness environment.
- After cutover, `services/legal_rag/` is the maintained runtime source inside Deer-flow-s. The old standalone repository remains a migration reference and parity baseline, not a second production implementation to change in parallel.

## Concrete migration seams

The integration is not between two chat applications. It is between Deer's built-in tool assembly point and Legal's existing structured-question entry point.

| Seam | Existing source | Target adaptation | Boundary rule |
| --- | --- | --- | --- |
| Deer tool registration | `backend/packages/harness/deerflow/tools/tools.py:26-38,46-124` | Export and register one `legal_augmentation_tool` in the existing built-in tool list | No new graph and no second agent |
| Deer orchestration | `backend/packages/harness/deerflow/agents/lead_agent/agent.py:334-340` | The existing lead agent receives the tool through `get_available_tools()` | `make_lead_agent` remains the only graph entry |
| Trigger policy | `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` and the tool description | Add a concise rule for when legal grounding is required and how to consume verdicts | First release uses normal agent tool selection; add middleware only if trigger evaluation proves systematic misses |
| Deer-to-Legal transport | Existing empty `backend/packages/harness/deerflow/legal/` package | Add a versioned contract and thin client with bounded timeout | No Legal SDK or database driver leaks into Deer |
| Legal service entry | `/Users/yuh/Desktop/项目/Legal-consulting-expert/api/service.py:68-158` | Reuse startup, health, singleton system, and prewarm behavior | No per-turn model/index initialization |
| Legal RAG invocation | `/Users/yuh/Desktop/项目/Legal-consulting-expert/main.py:630-847` | Stateless `/v1/augment` calls `ask_question_payload(question, ...)` and maps its existing payload into `LegalAugmentationResult v1` | Do not reimplement route/retrieval/rerank/refine in the adapter |
| Database access | `/Users/yuh/Desktop/项目/Legal-consulting-expert/main.py:202-270` | The migrated Legal runtime continues constructing the same Neo4j and Milvus modules from existing configuration | Deer uses the law database through Legal, never through direct Cypher/vector calls |
| Deployment | `docker/docker-compose.yaml` plus Legal's `docker-compose.yml:3-63` | Add the `legal-rag` service and point it to the existing Neo4j/Milvus endpoints; reuse Milvus dependencies where an integrated local deployment needs them | Do not create a second legal database or duplicate collections |

The minimum service request should contain a self-contained legal question plus optional trace/explanation flags. Deer may use conversation history to formulate that question before calling the tool, but Legal does not take ownership of the Deer thread. The service response should map the existing Legal payload nearly one-to-one: contract version, route analysis, documents, evidence, refine claims, refined draft, fallbacks, timing, and trace metadata.

## Legal database reuse and ownership

From the product perspective, Deer-flow-s is allowed to use the same legal knowledge database as the original Legal RAG. From the code perspective, the actual database calls remain inside the migrated Legal runtime. This preserves reuse while avoiding a new database abstraction in Deer.

- Neo4j remains the graph and legal-entity source used by `GraphDataPreparationModule`, `HybridRetrievalModule`, and `GraphRAGRetrieval`; Milvus remains the vector source used by `MilvusIndexConstructionModule` and enhanced vector search (`main.py:202-270`, `rag_modules/hybrid_retrieval.py:937-977`).
- Reuse the current Neo4j labels, relationships, full-text index names, Milvus collection name, embedding model, vector dimension, and metadata schema. The existing defaults include collection `legal_knowledge` and full-text index `legal_fulltext_idx` (`Legal-consulting-expert/config.py:12-93`).
- Deer stores only the internal Legal service URL, enable switch, timeout, and contract version. Neo4j/Milvus credentials and retrieval thresholds remain Legal-service configuration and are not copied into the Deer agent or tool arguments.
- Existing database instances and data are reused first. Startup should load the existing collection/indexes and must not delete, recreate, or silently rebuild them when they are healthy. Existing ingestion/build scripts remain the path for law-database construction and updates; user conversations do not become an ingestion path.
- Milvus collection compatibility is a hard precondition: the configured embedding model and dimension must match the existing stored vectors. Neo4j label/index names must likewise remain aligned. A mismatch is reported as service readiness failure rather than repaired by destructive automatic rebuilding.
- For local integrated deployment, the existing Milvus/etcd/MinIO services may be brought under Deer compose wiring, while Neo4j and Milvus may also remain externally managed through environment endpoints. In either case there is one logical legal knowledge base, not one copy per Deer component.

## End-to-end runtime linkage

### Startup path

1. `legal-rag` starts once, reads the migrated Legal configuration, connects to Neo4j and Milvus, loads the existing collection and graph data, builds only missing in-memory retrieval helpers, and prewarms the reranker.
2. Its health/readiness response distinguishes starting, ready, and failed states using the behavior already present in Legal `api/service.py:142-158`.
3. Deer starts independently. The legal tool client is lightweight and does not initialize Legal models or database connections.

### Query path

1. The existing Deer lead agent receives a user turn through the unchanged `lead_agent` graph (`backend/langgraph.json:8-13`).
2. For non-legal work, the turn proceeds exactly as today and no Legal call occurs.
3. For a question requiring legal grounding, the lead agent calls `legal_augmentation_tool` with a self-contained legal query.
4. The tool validates the small request contract and calls the internal `/v1/augment` endpoint through `deerflow/legal/client.py`.
5. The Legal adapter invokes the existing `ask_question_payload`; its inner router chooses `hybrid_traditional`, `graph_rag`, or `combined`, then executes the current Neo4j/Milvus/BM25 retrieval, fusion, rerank, evidence gate, and claim refine chain.
6. The service returns `LegalAugmentationResult v1`. The Deer client validates it and the tool exposes the bounded evidence package to the lead agent.
7. Deer writes the final conversational answer using `documents + evidence + refine.claims` as legal authority and the refined Legal answer only as a checked draft/context.
8. Timeout or service failure becomes a controlled tool result. Deer continues the conversation with an explicit lack-of-grounding limitation and must not fabricate a law-database-backed conclusion.

### Why this is the correct physical seam

- It reuses Deer's native extension mechanism: tools are already assembled centrally and bound to the sole lead agent (`tools.py:46-124`, `agent.py:334-340`).
- It reuses Legal's already-integrated core entry: `ask_question_payload` already performs routing, retrieval, rerank, evidence evaluation, refine, and structured output (`Legal-consulting-expert/main.py:630-847`).
- It avoids translating each Legal stage into LangGraph nodes, avoids a second conversation state, and avoids direct database clients in Deer. The only new logic is the contract/client/tool bridge needed to connect the two existing execution paths.

## Migration areas

1. **Core code movement/reuse**
   - Preserve query intent, internal route selection, hybrid retrieval, GraphRAG, Milvus index/search, cross-encoder rerank, graph quality gate, evidence gate, claim verification/refine, and LLM fallback behavior.

2. **Interface adaptation**
   - Add a stable augmentation-oriented contract that does not require Legal chat-session ownership.
   - Return full grounding material required by Deer, not merely UI snippets.

3. **Deer trigger and tool connection**
   - First release uses one versioned Deer built-in legal augmentation tool calling the internal Legal service.
   - MCP remains a future packaging option only if plugin-style distribution or cross-project reuse becomes necessary; it is not a parallel first-release path.
   - Keep outer domain recognition separate from Legal's inner retrieval-strategy router.

4. **Generation/refine handoff**
   - Preserve current Legal refined output as an evidence-checked legal draft/context for Deer, while treating `documents + evidence + refine.claims` as authoritative.
   - Constrain Deer final synthesis to supported/qualified claims so it cannot reintroduce unsupported conclusions.
   - If integration evaluation finds any unsupported claim reintroduced by Deer, the one-pass design fails its stop condition and must evolve to a two-stage Deer draft -> Legal verify/refine -> Deer final wording loop.

5. **Runtime and deployment**
   - Add the Legal RAG runtime/service and its Neo4j, Milvus, embedding, reranker, configuration, readiness, timeout, and fallback concerns to Deer deployment orchestration.
   - Keep heavy initialization outside per-message/per-agent construction.
   - Reuse existing law-database endpoints, collections, graph schema, indexes, and ingestion scripts; do not introduce a second storage model.

6. **Observability and regression**
   - Preserve route, fallback, evidence, rerank, and refine metadata.
   - Reuse the Legal evaluation set and add Deer conversation-level scenarios.
   - Freeze representative Legal evaluation samples and prove that `hybrid_traditional`, `graph_rag`, and `combined` remain distinguishable and exercisable after integration, including rerank fallback, evidence modes, and refine verdicts.

## Explicit non-goals

- No Legal React frontend migration.
- No second user-visible chat/session system.
- No replacement of Deer memory, uploads, sandbox, skills, or general tools.
- No rewrite of Neo4j/Milvus retrieval logic for stylistic consistency.
- No unconditional legal retrieval on every user turn.
- No use of Deer runtime tool self-evolution to generate this stable product capability dynamically; it should be a versioned built-in integration.
- No direct Neo4j or Milvus queries from the Deer lead agent/tool package; all database semantics stay behind the Legal service.
- No new database abstraction, event bus, plugin framework, caching layer, or retrieval rewrite merely for this migration.
- No automatic destructive rebuilding of existing Legal collections, graph data, or indexes.

## Direction-level migration stages

1. **Freeze the Legal baseline**
   - Preserve representative existing evaluation samples and capture a structured-semantic baseline for traditional, graph, combined, fallback, evidence, and refine cases; compare route/doc hits/verdict semantics rather than exact generated wording.
   - Record the active Neo4j schema/index names, Milvus collection metadata, embedding model, and vector dimension before moving runtime code.

2. **Move the Legal runtime into the Deer repository without changing its algorithms**
   - Place `main.py`, `config.py`, `rag_modules/`, required ingestion utilities, and evaluation fixtures under `services/legal_rag/`.
   - Keep a separate dependency manifest so the Legal LangChain/OpenAI/Milvus stack is not merged into `deerflow-harness`.
   - Prove the moved service still connects to the existing legal database and reproduces the frozen standalone semantics before touching Deer orchestration.

3. **Create the stateless augmentation boundary**
   - Reuse Legal startup/health/prewarm behavior and add one versioned `/v1/augment` endpoint that directly delegates to `ask_question_payload`.
   - Remove chat-session creation as a prerequisite for this endpoint; do not rewrite retrieval or generation internals.
   - Define the response by adapting existing fields, not inventing a second result model with different semantics.

4. **Connect the existing Deer lead agent**
   - Add typed Legal client configuration, `contracts.py`, and a thin service client under `deerflow/legal/`.
   - Add one built-in `legal_augmentation_tool`, export it from `tools/builtins`, and expose it through the existing built-in tool assembly path when Legal RAG is enabled.
   - Add concise trigger and evidence-consumption instructions to the lead-agent prompt. Do not add a new LangGraph graph/node; introduce a trigger middleware only if the frozen trigger suite demonstrates that normal tool selection is insufficient.

5. **Wire runtime configuration and database connectivity**
   - Add the Legal service to Deer compose and configure the internal base URL from the LangGraph container.
   - Pass Neo4j/Milvus/model/retrieval settings only to `legal-rag`; reuse the existing databases and data volumes/endpoints.
   - Verify readiness, one-time initialization, non-destructive loading, timeout behavior, and current reranker fallback.

6. **Run parity and conversation-level verification**
   - First compare standalone Legal and migrated Legal service outputs on the frozen set.
   - Then verify Deer trigger/no-trigger behavior and final synthesis against the same evidence/refine semantics.
   - Stop the one-pass design and adopt the already-defined two-stage verification flow if Deer reintroduces any claim marked unsupported by Legal.

## Acceptance criteria

1. Non-legal queries follow the existing Deer path without invoking Legal RAG.
2. Clear legal queries invoke the Legal augmentation chain and preserve route/rerank/evidence/refine metadata.
3. Deer remains the only final conversation response surface.
4. Supported claims remain grounded; unsupported Legal claims do not appear in Deer’s final answer.
5. Legal service failures degrade to Deer’s existing behavior with an explicit internal failure signal, not a broken conversation.
6. Existing Legal evaluation inputs can still measure law/article hit, route fallback, evidence mode, and refine verdicts.
7. The integration does not collapse the Legal chain to a single retrieval route: frozen samples continue to exercise and expose `hybrid_traditional`, `graph_rag`, and `combined`, as well as rerank fallback and claim-level refine verdicts.
8. Deer synthesis consumes `documents + evidence + refine.claims` as legal authority; Legal `answer` remains supporting draft/context only.
9. The migrated Legal service loads and queries the existing Neo4j graph and Milvus `legal_knowledge` collection without a new schema, duplicate database, or destructive rebuild.
10. Neo4j/Milvus credentials are available only to the Legal runtime; Deer reaches legal data only through the versioned augmentation tool contract.
11. The moved `services/legal_rag/` runtime reproduces the standalone Legal baseline before Deer integration is considered complete.
12. No second chat/session flow, frontend, new LangGraph node, or direct Deer database client is introduced.

## Risks and mitigations

- **Double routing confusion**: outer gate decides legal vs non-legal; inner router decides retrieval strategy.
- **Refine invalidated by Deer rewriting**: pass structured verdicts and constrain synthesis; escalate to two-stage verification only if evaluation proves necessary.
- **Dependency collision**: isolate Legal runtime rather than forcing immediate LangChain/OpenAI major-version migration.
- **Existing database incompatibility**: verify collection name, embedding model/dimension, Neo4j labels, relationships, and index names before startup; fail readiness rather than rebuilding automatically.
- **Cold-start/latency**: singleton service initialization, reranker prewarm, readiness checks, bounded timeout, existing lightweight rerank fallback.
- **Payload/context bloat**: return ranked top evidence and structured claims, not the entire recall pool.
- **False negatives in legal trigger**: combine clear rules with model/tool semantics and log missed-trigger evaluations.

## ADR

### Decision

Use an internal Legal RAG service exposed through one versioned Deer built-in legal augmentation tool. First rely on the existing lead agent's tool selection plus a concise legal-use policy; add a lightweight trigger guard only if evaluation shows systematic misses. Deer consumes the structured, evidence-checked result and produces the final answer. MCP is deferred unless later distribution or cross-project reuse needs justify it.

### Drivers

- Minimal adaptation and maximum code reuse.
- Dependency/runtime isolation.
- Preserve Deer as conversation主体 and Legal RAG as auxiliary capability.

### Alternatives considered

- Direct in-process transplant.
- Deep Deer LangGraph node/middleware rewrite.

### Why chosen

The service/tool boundary best matches the existing code and minimizes the risk that dependency upgrades or graph rewrites silently change either system's mature behavior.

### Consequences

- Adds an internal runtime service and network contract.
- Keeps Legal core independently testable and rollbackable.
- Requires a strict structured output contract and synthesis rules in Deer.
- Allows Deer to use the existing legal database while database ownership, credentials, and query implementation remain in the reused Legal runtime.

### Follow-ups

- Freeze the outer-trigger sample set and exact `LegalAugmentationResult v1` field mapping before implementation.
- Inventory the current Neo4j schema/indexes and Milvus collection/embedding metadata before moving the service.
- Benchmark whether one-pass refined-draft consumption is sufficient or a post-Deer verification pass is required.

### Architecture stop condition

If Deer final synthesis reintroduces any claim marked unsupported by Legal on the frozen integration evaluation set, the one-pass architecture is rejected and implementation must switch to the two-stage Deer draft -> Legal verify/refine -> Deer final wording flow.

## Planning status

Direction baseline is sufficient and closed after independent review. Repository placement, database reuse, migration seams, runtime linkage, boundaries, and architecture stop conditions are fixed here. Concrete implementation work is delegated to `.omx/plans/implementation-plan-legal-rag-migration.md`; this direction artifact is not the execution checklist.
