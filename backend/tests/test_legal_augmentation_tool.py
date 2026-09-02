from __future__ import annotations

import asyncio
import importlib

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


def _tool_names(enabled: bool, monkeypatch) -> list[str]:
    monkeypatch.setattr("deerflow.tools.tools.get_app_config", lambda: _config(enabled=enabled))
    return [tool.name for tool in get_available_tools(include_mcp=False)]


def test_tool_hidden_when_disabled(monkeypatch):
    assert "legal_augmentation" not in _tool_names(False, monkeypatch)


def test_tool_present_when_enabled(monkeypatch):
    assert "legal_augmentation" in _tool_names(True, monkeypatch)


def test_success_keeps_verdicts(monkeypatch):
    payload = LegalAugmentationResult.model_validate(
        {
            "contract_version": "v1",
            "answer": "draft",
            "analysis": {
                "strategy": "hybrid_traditional",
                "query_complexity": 0.1,
                "relationship_intensity": 0.1,
                "confidence": 0.9,
                "reasoning_required": False,
                "reasoning": "ok",
            },
            "evidence": {"mode": "strong", "reason": "hit"},
            "documents": [{"display_title": "title"}],
            "refine": {
                "claims": [
                    {"claim_id": "c1", "verdict": "supported"},
                    {"claim_id": "c2", "verdict": "unsupported", "claim_text": "should not be reused"},
                ]
            },
        }
    )

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def augment(self, request):
            return payload

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _FakeClient)
    result = asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "试用期辞退依据"}))
    assert "unsupported" in result
    assert "supported" in result


def test_known_failures_are_structured(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            raise LegalRAGClientError("timeout", "legal rag request timed out")

        async def aclose(self):
            return None

    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=True))
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", _FakeClient)
    result = asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "timeout"}))
    assert "timeout" in result


def test_disabled_failure_object(monkeypatch):
    monkeypatch.setattr(legal_aug_mod, "get_app_config", lambda: _config(enabled=False))
    result = asyncio.run(legal_aug_mod.legal_augmentation_tool.ainvoke({"question": "anything"}))
    assert "disabled" in result
