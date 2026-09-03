from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas import AugmentResponse


REQUIRED_FIELDS = {
    "contract_version",
    "answer",
    "analysis",
    "evidence",
    "documents",
    "refine",
    "elapsed_seconds",
    "route_fallback",
    "routing_explanation",
    "route_metrics",
}

ANALYSIS_FIELDS = {
    "strategy",
    "query_complexity",
    "relationship_intensity",
    "confidence",
    "reasoning_required",
    "reasoning",
}

EVIDENCE_FIELDS = {"mode", "reason", "top_rerank_score", "top_must_hit_count"}
DOCUMENT_FIELDS = {
    "display_title",
    "law_name",
    "article_id",
    "article_title",
    "snippet",
    "score",
    "search_type",
    "route_strategy",
    "search_source",
    "route_fallback",
    "rerank_model",
    "rerank_latency_ms",
    "rerank_fallback_reason",
}
REFINE_FIELDS = {
    "draft_claim_count",
    "refined_claim_count",
    "supported_count",
    "weak_count",
    "unsupported_count",
    "claims",
}


def test_v1_schema_keeps_existing_payload_fields():
    fields = set(AugmentResponse.model_fields)
    assert REQUIRED_FIELDS <= fields
    analysis = set(AugmentResponse.model_fields["analysis"].annotation.model_fields)
    evidence = set(AugmentResponse.model_fields["evidence"].annotation.model_fields)
    refine = set(AugmentResponse.model_fields["refine"].annotation.model_fields)
    assert ANALYSIS_FIELDS <= analysis
    assert EVIDENCE_FIELDS <= evidence
    assert REFINE_FIELDS <= refine


def test_v1_accepts_existing_ask_question_payload_shape():
    payload = {
        "contract_version": "v1",
        "answer": "draft",
        "analysis": {
            "strategy": "combined",
            "query_complexity": 0.7,
            "relationship_intensity": 0.6,
            "confidence": 0.5,
            "reasoning_required": True,
            "reasoning": "multi hop",
        },
        "evidence": {
            "mode": "weak",
            "reason": "partial",
            "top_rerank_score": 0.4,
            "top_must_hit_count": 1,
        },
        "documents": [
            {
                "display_title": "title",
                "snippet": "snippet",
            }
        ],
        "refine": {
            "draft_claim_count": 2,
            "refined_claim_count": 2,
            "supported_count": 1,
            "weak_count": 1,
            "unsupported_count": 0,
            "claims": [{"claim_id": "c1", "verdict": "supported"}],
        },
        "elapsed_seconds": 3.3,
        "route_fallback": "empty_result_to_traditional",
        "routing_explanation": "",
        "route_metrics": {"graph_attempted": True},
    }
    parsed = AugmentResponse.model_validate(payload)
    assert parsed.analysis.strategy == "combined"
    assert parsed.refine.claims[0]["verdict"] == "supported"
    assert parsed.route_fallback == "empty_result_to_traditional"
