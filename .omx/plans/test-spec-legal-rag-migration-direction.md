# Test Spec: Legal RAG Migration Direction

This is a high-level verification shape, not an implementation test listing.

## Behavioral lanes

1. Non-legal conversation remains unchanged and performs no Legal RAG call.
2. Explicit law/article questions trigger Legal RAG.
3. Relationship-heavy legal questions preserve GraphRAG/combined routing.
4. Simple legal fact questions may preserve traditional hybrid routing.
5. Neo4j empty/grounding failure falls back according to existing Legal rules.
6. Cross-encoder failure preserves lightweight rerank fallback metadata.
7. Evidence gate preserves strong/weak/insufficient semantics.
8. Unsupported claims never survive into Deer final output.
9. Legal service unavailable/timeout does not terminate the Deer conversation.
10. Existing Legal evaluation fields remain observable after integration.
11. Frozen Legal samples still exercise and distinguish `hybrid_traditional`, `graph_rag`, and `combined`; integration must not collapse them into one route.
12. Rerank fallback, evidence modes, and claim-level refine verdicts retain their original semantics, not merely their field names.
13. Deer treats `documents + evidence + refine.claims` as authoritative and Legal `answer` only as an evidence-checked draft/context.

## Stop condition

The direction is accepted when the architecture preserves Deer conversation ownership, Legal RAG capability completeness, explicit failure degradation, and a testable claim-grounding contract without requiring a rewrite of either core system. If Deer reintroduces any claim marked unsupported by Legal on the frozen integration set, the one-pass design is rejected and must switch to the two-stage Deer draft -> Legal verify/refine -> Deer final wording flow.
