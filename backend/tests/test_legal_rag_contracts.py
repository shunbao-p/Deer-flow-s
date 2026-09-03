from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.legal.contracts import CONTRACT_VERSION, LegalAugmentationResult


def _valid_payload(**overrides):
    payload = {
        "contract_version": CONTRACT_VERSION,
        "answer": "draft",
        "analysis": {
            "strategy": "hybrid_traditional",
            "query_complexity": 0.1,
            "relationship_intensity": 0.1,
            "confidence": 0.9,
            "reasoning_required": False,
            "reasoning": "ok",
        },
        "evidence": {"mode": "strong", "reason": "hit", "top_rerank_score": 0.8, "top_must_hit_count": 1},
        "documents": [{"display_title": "title", "law_name": "劳动合同法", "article_id": "第三十九条"}],
        "refine": {
            "draft_claim_count": 1,
            "refined_claim_count": 1,
            "supported_count": 1,
            "weak_count": 0,
            "unsupported_count": 0,
            "claims": [{"claim_id": "c1", "verdict": "supported"}],
        },
        "elapsed_seconds": 1.0,
    }
    payload.update(overrides)
    return payload


def test_valid_v1_result():
    result = LegalAugmentationResult.model_validate(_valid_payload())
    assert result.contract_version == "v1"
    assert result.refine.claims[0]["verdict"] == "supported"


def test_unknown_version_rejected():
    with pytest.raises(ValidationError):
        LegalAugmentationResult.model_validate(_valid_payload(contract_version="v9"))


def test_missing_authority_fields_rejected():
    payload = _valid_payload()
    del payload["documents"]
    with pytest.raises(ValidationError):
        LegalAugmentationResult.model_validate(payload)
