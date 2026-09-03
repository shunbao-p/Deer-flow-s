from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


CONTRACT_VERSION = "v1"


class AugmentRequest(BaseModel):
    contract_version: Literal["v1"] = Field(default=CONTRACT_VERSION)
    question: str = Field(..., min_length=1, description="Self-contained legal question")
    explain_routing: bool = False
    eval_batch_id: Optional[str] = None
    eval_fast_mode: Optional[bool] = None


class AnalysisDTO(BaseModel):
    strategy: str
    query_complexity: float
    relationship_intensity: float
    confidence: float
    reasoning_required: bool
    reasoning: str


class EvidenceStateDTO(BaseModel):
    mode: str
    reason: str
    top_rerank_score: float = 0.0
    top_must_hit_count: int = 0


class DocumentDTO(BaseModel):
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


class RefineDTO(BaseModel):
    draft_claim_count: int = 0
    refined_claim_count: int = 0
    supported_count: int = 0
    weak_count: int = 0
    unsupported_count: int = 0
    claims: List[Dict[str, Any]] = Field(default_factory=list)


class AugmentResponse(BaseModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    answer: str
    analysis: AnalysisDTO
    evidence: EvidenceStateDTO
    documents: List[DocumentDTO]
    refine: RefineDTO = Field(default_factory=RefineDTO)
    elapsed_seconds: float
    route_fallback: str = ""
    routing_explanation: str = ""
    route_metrics: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    initialized: bool
    system_ready: bool
    startup_error: str = ""
    reranker_ready: bool = False
    reranker_model: str = ""
    reranker_prewarm_latency_ms: int = 0
    reranker_prewarm_reason: str = ""
