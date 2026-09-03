from __future__ import annotations

import asyncio
import importlib
import json

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.config.app_config import AppConfig
from deerflow.legal.client import LegalRAGClientError
from deerflow.legal.contracts import LegalAugmentationResult
from deerflow.tools.tools import get_available_tools

legal_aug_mod = importlib.import_module("deerflow.tools.builtins.legal_augmentation_tool")


def _config(*, enabled: bool) -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "legal_rag": {"enabled": enabled, "base_url": "http://127.0.0.1:8003", "timeout_seconds": 120},
        }
    )


def _result(**overrides) -> LegalAugmentationResult:
    payload = {
        "contract_version": "v1",
        "answer": "draft",
        "analysis": {
            "strategy": "hybrid_traditional",
            "query_complexity": 0.2,
            "relationship_intensity": 0.1,
            "confidence": 0.8,
            "reasoning_required": False,
            "reasoning": "ok",
        },
        "evidence": {"mode": "strong", "reason": "hit"},
        "documents": [{"display_title": "title", "law_name": "劳动合同法", "article_id": "第三十九条"}],
        "refine": {"claims": [{"claim_id": "c1", "verdict": "supported"}]},
    }
    payload.update(overrides)
    return LegalAugmentationResult.model_validate(payload)


def test_non_legal_rules_exist_only_when_enabled(monkeypatch):
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=True))
    text = prompt_module.get_legal_augmentation_prompt_section()
    assert "non-legal" in text
    assert "Do not call it for ordinary facts" in text
    monkeypatch.setattr("deerflow.tools.tools.get_app_config", lambda: _config(enabled=True))
    assert "legal_augmentation" in [tool.name for tool in get_available_tools(include_mcp=False)]


def test_simple_and_relational_share_one_tool(monkeypatch):
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=True))
    text = prompt_module.get_legal_augmentation_prompt_section()
    assert "Do not pick Milvus, Neo4j, or GraphRAG yourself" in text
    captured: list[str] = []

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def augment(self, request):
            captured.append(request.question)
            strategy = "combined" if "关系" in request.question else "hybrid_traditional"
            return _result(
                analysis={
                    "strategy": strategy,
                    "query_complexity": 0.4,
                    "relationship_intensity": 0.7 if strategy == "combined" else 0.1,
                    "confidence": 0.8,
                    "reasoning_required": strategy == "combined",
                    "reasoning": "ok",
                }
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _FakeClient)
    simple = asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "试用期解除依据"}))
    relational = asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "关联公司关系下的解除依据"}))
    assert json.loads(simple)["analysis"]["strategy"] == "hybrid_traditional"
    assert json.loads(relational)["analysis"]["strategy"] == "combined"
    assert len(captured) == 2


def test_timeout_and_unavailable_are_structured(monkeypatch):
    class _TimeoutClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            raise LegalRAGClientError("timeout", "legal rag request timed out")

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _TimeoutClient)
    timeout_body = json.loads(asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "q"})))
    assert timeout_body["error_type"] == "timeout"
    monkeypatch.setattr(
        "deerflow.config.app_config.get_app_config",
        lambda: _config(enabled=True),
    )
    prompt = prompt_module.get_legal_augmentation_prompt_section()
    assert "timeout/unavailable/invalid_response" in prompt
    assert "Do not invent a database-backed legal conclusion" in prompt
    assert "Do not supply statutes, article numbers, or legal rules from model memory" in prompt


def test_insufficient_evidence_is_preserved(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(evidence={"mode": "insufficient", "reason": "no_hit"})

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _FakeClient)
    body = json.loads(asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "q"})))
    assert body["evidence"]["mode"] == "insufficient"
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=True))
    assert "insufficient" in prompt_module.get_legal_augmentation_prompt_section()


def test_unsupported_claim_stays_in_tool_output(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(
                refine={
                    "unsupported_count": 1,
                    "claims": [{"claim_id": "c2", "verdict": "unsupported"}],
                }
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _FakeClient)
    body = json.loads(asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "q"})))
    assert body["refine"]["claims"][0]["verdict"] == "unsupported"
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=True))
    assert "Never include unsupported claims" in prompt_module.get_legal_augmentation_prompt_section()
