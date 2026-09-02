from __future__ import annotations

import asyncio

import httpx
import pytest

from deerflow.config.legal_rag_config import LegalRAGConfig
from deerflow.legal.client import LegalRAGClient, LegalRAGClientError, resolve_legal_rag_base_url
from deerflow.legal.contracts import LegalAugmentationRequest


def _ok_payload() -> dict:
    return {
        "contract_version": "v1",
        "answer": "draft",
        "analysis": {
            "strategy": "graph_rag",
            "query_complexity": 0.8,
            "relationship_intensity": 0.7,
            "confidence": 0.6,
            "reasoning_required": True,
            "reasoning": "path",
        },
        "evidence": {"mode": "weak", "reason": "partial", "top_rerank_score": 0.4, "top_must_hit_count": 1},
        "documents": [{"display_title": "title"}],
        "refine": {
            "draft_claim_count": 1,
            "refined_claim_count": 1,
            "supported_count": 0,
            "weak_count": 1,
            "unsupported_count": 0,
            "claims": [{"claim_id": "c1", "verdict": "weak"}],
        },
        "elapsed_seconds": 2.0,
        "route_fallback": "",
        "routing_explanation": "",
        "route_metrics": {},
    }


def _run(coro):
    return asyncio.run(coro)


def _client_with(handler) -> LegalRAGClient:
    client = LegalRAGClient(LegalRAGConfig())
    asyncio.run(client.aclose())
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://legal")
    return client


def test_augment_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/augment"
        return httpx.Response(200, json=_ok_payload())

    client = _client_with(handler)
    result = _run(client.augment(LegalAugmentationRequest(question="关系型责任链")))
    assert result.analysis.strategy == "graph_rag"
    _run(client.aclose())


def test_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="timeout case")))
    assert exc.value.error_type == "timeout"
    _run(client.aclose())


def test_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="unavailable case")))
    assert exc.value.error_type == "unavailable"
    _run(client.aclose())


def test_non_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "failed"})

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="http error")))
    assert exc.value.error_type == "unavailable"
    _run(client.aclose())


def test_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="bad json")))
    assert exc.value.error_type == "invalid_response"
    _run(client.aclose())


def test_version_mismatch():
    payload = _ok_payload()
    payload["contract_version"] = "v0"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="version")))
    assert exc.value.error_type == "invalid_response"
    _run(client.aclose())


def test_missing_authority_field():
    payload = _ok_payload()
    del payload["refine"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _client_with(handler)
    with pytest.raises(LegalRAGClientError) as exc:
        _run(client.augment(LegalAugmentationRequest(question="missing refine")))
    assert exc.value.error_type == "invalid_response"
    _run(client.aclose())


def test_health_returns_failed_body_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(503, json={"status": "failed", "system_ready": False})

    client = _client_with(handler)
    payload = _run(client.health())
    assert payload["status"] == "failed"
    assert payload["system_ready"] is False
    _run(client.aclose())


def test_env_overrides_yaml(monkeypatch):
    monkeypatch.setenv("LEGAL_RAG_BASE_URL", "http://legal-rag:8003")
    assert resolve_legal_rag_base_url(LegalRAGConfig(base_url="http://127.0.0.1:8003")) == "http://legal-rag:8003"
    monkeypatch.delenv("LEGAL_RAG_BASE_URL")
    assert resolve_legal_rag_base_url(LegalRAGConfig(base_url="http://127.0.0.1:8003")) == "http://127.0.0.1:8003"
