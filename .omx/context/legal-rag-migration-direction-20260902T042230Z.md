# Context Snapshot: Legal RAG Migration Direction

## Task statement

Give a high-level migration direction for integrating `/Users/yuh/Desktop/项目/Legal-consulting-expert` into Deer-flow-s. The answer should describe what areas will change, how capabilities connect, and what to watch for, without file-level implementation detail.

## Desired outcome

- Deer-flow-s remains the only conversation主体 and final response orchestrator.
- Legal RAG is triggered only when legal-domain augmentation is needed.
- Existing Legal RAG capabilities are preserved: internal query routing, Neo4j/Milvus/BM25 retrieval, fusion, rerank, quality filtering, evidence gating, and claim-level refine.
- Reuse existing modules and make only thin integration changes.

## Known facts / evidence

- Deer-flow-s uses one `lead_agent` graph with middleware and tool/MCP extensions.
- The fork's custom work centers on governed skill/tool evolution and MCP registration, not replacing the main dialogue graph.
- Legal RAG already has a complete orchestration chain in `main.py` and `rag_modules/`.
- Legal Refine occurs after a draft answer and is not merely a retrieval post-process.
- Legal API/UI are demo shells; the reusable core is the RAG orchestration and modules.
- The repositories currently use incompatible major dependency generations (Legal: LangChain Core 0.3.x/OpenAI <2; Deer-flow-s: LangChain Core 1.x/OpenAI 2.x).

## Constraints

- Do not build a second chatbot inside Deer-flow-s.
- Do not redesign the retrieval algorithms unless required by an integration contract.
- Do not omit or silently weaken rerank/refine/evidence gating.
- Do not migrate the Legal React frontend or duplicate Deer conversation/session management.
- Keep the current request at direction/architecture level; no source implementation.

## Unknowns / open decisions

- Whether the first delivery should run Legal RAG in-process or as an internal service; dependency evidence favors process isolation.
- How strictly the outer legal-domain trigger should be enforced: model-led tool selection only, or lightweight deterministic/domain middleware guidance.
- Whether Deer should consume the fully refined Legal answer as a legal draft, or participate in a two-stage draft/refine loop.

## Likely touchpoints

- Deer lead-agent tool/MCP loading and prompt/middleware routing.
- A thin Legal RAG adapter endpoint/tool returning a stable structured evidence bundle.
- Deployment/runtime configuration for Legal service, Neo4j, Milvus, models, health, and timeouts.
- Regression evaluation retaining Legal response metadata and Deer conversation behavior.
