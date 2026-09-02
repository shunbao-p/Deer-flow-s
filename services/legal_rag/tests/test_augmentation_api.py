from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import app as app_module  # noqa: E402


SAMPLE_PAYLOAD = {
    "answer": "checked draft",
    "analysis": {
        "strategy": "hybrid_traditional",
        "query_complexity": 0.2,
        "relationship_intensity": 0.1,
        "confidence": 0.8,
        "reasoning_required": False,
        "reasoning": "simple article lookup",
    },
    "evidence": {
        "mode": "strong",
        "reason": "top_hit",
        "top_rerank_score": 0.9,
        "top_must_hit_count": 2,
    },
    "documents": [
        {
            "display_title": "劳动合同法 第三十九条",
            "law_name": "中华人民共和国劳动合同法",
            "article_id": "第三十九条",
            "article_title": "过失性辞退",
            "snippet": "劳动者有下列情形之一的，用人单位可以解除劳动合同",
            "score": 0.91,
            "search_type": "vector_enhanced",
            "route_strategy": "hybrid_traditional",
            "search_source": "milvus",
            "route_fallback": "",
            "rerank_model": "BAAI/bge-reranker-v2-m3",
            "rerank_latency_ms": 12,
            "rerank_fallback_reason": "",
        }
    ],
    "refine": {
        "draft_claim_count": 1,
        "refined_claim_count": 1,
        "supported_count": 1,
        "weak_count": 0,
        "unsupported_count": 0,
        "claims": [
            {
                "claim_id": "c1",
                "claim_text": "用人单位可依法解除",
                "verdict": "supported",
            }
        ],
    },
    "elapsed_seconds": 1.2,
    "route_fallback": "",
    "routing_explanation": "",
    "route_metrics": {"graph_attempted": False},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module.service, "startup", lambda: None)
    monkeypatch.setattr(app_module.service, "shutdown", lambda: None)
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


def _ready_system(payload=None) -> MagicMock:
    system = MagicMock()
    system.system_ready = True
    system.ask_question_payload.return_value = payload or SAMPLE_PAYLOAD
    app_module.service._system = system
    app_module.service._initialized = True
    app_module.service._startup_error = ""
    return system


def test_augment_forwards_fields_and_keeps_payload(client):
    system = _ready_system()
    response = client.post(
        "/v1/augment",
        json={
            "contract_version": "v1",
            "question": "试用期严重违纪能否解除劳动合同",
            "explain_routing": True,
            "eval_fast_mode": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    system.ask_question_payload.assert_called_once_with(
        "试用期严重违纪能否解除劳动合同",
        explain_routing=True,
        eval_fast_mode=False,
    )
    assert body["contract_version"] == "v1"
    assert body["analysis"]["strategy"] == "hybrid_traditional"
    assert body["documents"][0]["law_name"] == "中华人民共和国劳动合同法"
    assert body["evidence"]["mode"] == "strong"
    assert body["refine"]["claims"][0]["verdict"] == "supported"
    assert body["answer"] == "checked draft"


def test_empty_question_rejected(client):
    _ready_system()
    response = client.post("/v1/augment", json={"contract_version": "v1", "question": ""})
    assert response.status_code == 422


def test_unknown_contract_version_rejected(client):
    _ready_system()
    response = client.post(
        "/v1/augment",
        json={"contract_version": "v2", "question": "试用期严重违纪能否解除劳动合同"},
    )
    assert response.status_code == 422


def test_not_ready_returns_503(client):
    app_module.service._system = None
    app_module.service._initialized = False
    app_module.service._startup_error = "missing database"
    response = client.post(
        "/v1/augment",
        json={"contract_version": "v1", "question": "试用期严重违纪能否解除劳动合同"},
    )
    assert response.status_code == 503


def test_internal_error_returns_500(client):
    system = _ready_system()
    system.ask_question_payload.side_effect = RuntimeError("boom")
    response = client.post(
        "/v1/augment",
        json={"contract_version": "v1", "question": "试用期严重违纪能否解除劳动合同"},
    )
    assert response.status_code == 500


def test_health_ready_200_and_failed_503(client):
    _ready_system()
    ready = client.get("/health")
    assert ready.status_code == 200
    assert ready.json()["system_ready"] is True

    app_module.service._system = None
    app_module.service._initialized = False
    app_module.service._startup_error = "init failed"
    failed = client.get("/health")
    assert failed.status_code == 503
    assert failed.json()["status"] == "failed"
