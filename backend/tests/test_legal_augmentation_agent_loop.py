from __future__ import annotations

import asyncio
import importlib
import json

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.agents.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware
from deerflow.config.app_config import AppConfig
from deerflow.legal.client import LegalRAGClientError
from deerflow.legal.contracts import LegalAugmentationResult

legal_aug_mod = importlib.import_module("deerflow.tools.builtins.legal_augmentation_tool")

UNSUPPORTED_TEXT = "UNSUPPORTED_CLAIM_MUST_NOT_APPEAR"


def _config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "legal_rag": {"enabled": True, "base_url": "http://127.0.0.1:8003", "timeout_seconds": 120},
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
        "refine": {
            "supported_count": 1,
            "unsupported_count": 0,
            "claims": [{"claim_id": "c1", "verdict": "supported", "claim_text": "用人单位可依法解除"}],
        },
    }
    payload.update(overrides)
    return LegalAugmentationResult.model_validate(payload)


def _final_from_tool_payload(payload: dict) -> str:
    if payload.get("ok") is False or payload.get("error_type"):
        return "法律知识库当前不可用，不能给出数据库支持的法律结论。"
    evidence = payload.get("evidence") or {}
    if str(evidence.get("mode", "")) == "insufficient":
        return "现有检索证据不足，不能给出数据库支持的法律结论。"
    claims = (payload.get("refine") or {}).get("claims") or []
    supported = [str(item.get("claim_text") or "") for item in claims if item.get("verdict") == "supported"]
    if supported:
        return "依据已支持主张：" + "；".join(supported)
    return "没有得到可支持的法律主张。"


class PolicyScriptedModel(BaseChatModel):
    """Test double that follows the published legal_augmentation prompt rules."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        human = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        if "普通写作" in str(human) and not tool_messages:
            message = AIMessage(content="这是普通写作建议，不调用法律库。")
        elif not tool_messages:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "legal_augmentation",
                        "args": {"question": str(human)},
                        "id": "call_legal_1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            payload = json.loads(str(tool_messages[-1].content))
            message = AIMessage(content=_final_from_tool_payload(payload))
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop)

    @property
    def _llm_type(self) -> str:
        return "policy-scripted-legal"

    def bind_tools(self, tools, **kwargs):
        return self


def _run_scene(user_text: str, *, client_factory, monkeypatch) -> list:
    monkeypatch.setattr(legal_aug_mod, "get_app_config", _config)
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", _config)
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", client_factory)
    agent = create_agent(
        model=PolicyScriptedModel(),
        tools=[legal_aug_mod.legal_augmentation_tool],
        system_prompt=prompt_module.get_legal_augmentation_prompt_section(),
        middleware=[ToolErrorHandlingMiddleware()],
    )
    result = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content=user_text)]}))
    return list(result["messages"])


def _tool_payloads(messages: list) -> list[dict]:
    payloads = []
    for message in messages:
        if isinstance(message, ToolMessage):
            payloads.append(json.loads(str(message.content)))
    return payloads


def _final_text(messages: list) -> str:
    return str(messages[-1].content)


def test_non_legal_scene_does_not_call_tool(monkeypatch):
    class _BoomClient:
        def __init__(self, config):
            raise AssertionError("non-legal scene must not construct the legal client")

    messages = _run_scene("请帮我改一句普通写作", client_factory=_BoomClient, monkeypatch=monkeypatch)
    assert _tool_payloads(messages) == []
    assert "普通写作" in _final_text(messages)


def test_simple_legal_scene_calls_tool(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def augment(self, request):
            return _result()

        async def aclose(self):
            return None

    messages = _run_scene("试用期解除劳动合同的依据", client_factory=_FakeClient, monkeypatch=monkeypatch)
    payloads = _tool_payloads(messages)
    assert payloads[0]["analysis"]["strategy"] == "hybrid_traditional"
    assert "用人单位可依法解除" in _final_text(messages)


def test_relational_legal_scene_calls_tool(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(
                analysis={
                    "strategy": "combined",
                    "query_complexity": 0.7,
                    "relationship_intensity": 0.8,
                    "confidence": 0.7,
                    "reasoning_required": True,
                    "reasoning": "path",
                }
            )

        async def aclose(self):
            return None

    messages = _run_scene("关联公司关系下的解除依据", client_factory=_FakeClient, monkeypatch=monkeypatch)
    assert _tool_payloads(messages)[0]["analysis"]["strategy"] == "combined"


def test_timeout_scene_does_not_invent_legal_conclusion(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            raise LegalRAGClientError("timeout", "legal rag request timed out")

        async def aclose(self):
            return None

    messages = _run_scene("超时法律问题", client_factory=_FakeClient, monkeypatch=monkeypatch)
    assert _tool_payloads(messages)[0]["error_type"] == "timeout"
    text = _final_text(messages)
    assert "不可用" in text
    assert "数据库支持" in text


def test_insufficient_scene_states_evidence_limit(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(evidence={"mode": "insufficient", "reason": "no_hit"})

        async def aclose(self):
            return None

    text = _final_text(_run_scene("证据不足问题", client_factory=_FakeClient, monkeypatch=monkeypatch))
    assert "证据不足" in text


def test_unsupported_claim_does_not_enter_final_answer(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(
                refine={
                    "supported_count": 1,
                    "unsupported_count": 1,
                    "claims": [
                        {"claim_id": "c1", "verdict": "supported", "claim_text": "用人单位可依法解除"},
                        {"claim_id": "c2", "verdict": "unsupported", "claim_text": UNSUPPORTED_TEXT},
                    ],
                }
            )

        async def aclose(self):
            return None

    messages = _run_scene("含未支持主张的问题", client_factory=_FakeClient, monkeypatch=monkeypatch)
    tool_body = _tool_payloads(messages)[0]
    assert tool_body["refine"]["claims"][1]["verdict"] == "unsupported"
    final = _final_text(messages)
    assert UNSUPPORTED_TEXT not in final
    assert "用人单位可依法解除" in final
