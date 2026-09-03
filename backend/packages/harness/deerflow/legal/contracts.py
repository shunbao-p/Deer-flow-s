from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "v1"


class LegalAnalysis(BaseModel):
    strategy: str
    query_complexity: float
    relationship_intensity: float
    confidence: float
    reasoning_required: bool
    reasoning: str = ""


class LegalEvidence(BaseModel):
    mode: str
    reason: str
    top_rerank_score: float = 0.0
    top_must_hit_count: int = 0


class LegalDocument(BaseModel):
    display_title: str
    law_name: str = ""
    article_id: str = ""
    article_title: str = ""
    snippet: str = ""
    score: float = 0.0
    search_type: str = ""
    route_strategy: str = ""
    search_source: str = ""
    route_fallback: str = ""
    rerank_model: str = ""
    rerank_latency_ms: int = 0
    rerank_fallback_reason: str = ""


class LegalRefine(BaseModel):
    draft_claim_count: int = 0
    refined_claim_count: int = 0
    supported_count: int = 0
    weak_count: int = 0
    unsupported_count: int = 0
    claims: list[dict[str, Any]] = Field(default_factory=list)


class LegalAugmentationRequest(BaseModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    question: str = Field(..., min_length=1)
    explain_routing: bool = False
    eval_batch_id: str | None = None
    eval_fast_mode: bool | None = None


class LegalAugmentationResult(BaseModel):
    contract_version: Literal["v1"]
    answer: str
    analysis: LegalAnalysis
    evidence: LegalEvidence
    documents: list[LegalDocument]
    refine: LegalRefine = Field(default_factory=LegalRefine)
    elapsed_seconds: float = 0.0
    route_fallback: str = ""
    routing_explanation: str = ""
    route_metrics: dict[str, Any] = Field(default_factory=dict)


class LegalAugmentationFailure(BaseModel):
    ok: bool = False
    error_type: Literal["disabled", "timeout", "unavailable", "invalid_response"]
    message: str
