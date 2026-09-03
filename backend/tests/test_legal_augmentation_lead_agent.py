"""Deterministic six-scene checks through official make_lead_agent."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from deerflow.agents.lead_agent.agent import make_lead_agent
from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.config.app_config import AppConfig, set_app_config
from deerflow.config.memory_config import MemoryConfig, set_memory_config
from deerflow.config.title_config import TitleConfig, set_title_config
from deerflow.legal.client import LegalRAGClientError
from deerflow.legal.contracts import LegalAugmentationResult
from deerflow.tools.tools import get_available_tools

legal_aug_mod = importlib.import_module("deerflow.tools.builtins.legal_augmentation_tool")

UNSUPPORTED_TEXT = "在月球工作也必须由用人单位缴纳社会保险"
UNSUPPORTED_MARKERS = ("月球", "月亮")


def _install_config(*, base_url: str = "http://127.0.0.1:8003", timeout_seconds: float = 120) -> AppConfig:
    os.environ.pop("DEER_FLOW_EXTENSIONS_CONFIG_PATH", None)
    os.environ.pop("DEER_FLOW_CONFIG_PATH", None)
    set_memory_config(MemoryConfig(enabled=False))
    set_title_config(TitleConfig(enabled=False))
    config = AppConfig.model_validate(
        {
            "models": [
                {
                    "name": "r02-scripted",
                    "display_name": "r02-scripted",
                    "use": "langchain_openai:ChatOpenAI",
                    "model": "r02-scripted",
                    "supports_thinking": False,
                    "supports_vision": False,
                }
            ],
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "legal_rag": {"enabled": True, "base_url": base_url, "timeout_seconds": timeout_seconds},
        }
    )
    set_app_config(config)
    return config


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
    unsupported = [str(item.get("claim_text") or "") for item in claims if item.get("verdict") == "unsupported"]
    text = "依据已支持主张：" + "；".join(supported) if supported else "没有得到可支持的法律主张。"
    for item in unsupported:
        assert item not in text
    return text


class OfficialPathScriptedModel(BaseChatModel):
    """Follows published legal prompt rules while using the official tool set."""

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
        return "official-path-scripted-legal"

    def bind_tools(self, tools, **kwargs):
        return self


def _run_scene(user_text: str, *, client_factory, monkeypatch) -> list:
    _install_config()
    monkeypatch.setattr(legal_aug_mod, "LegalRAGClient", client_factory)
    monkeypatch.setattr("deerflow.agents.lead_agent.agent.create_chat_model", lambda **kwargs: OfficialPathScriptedModel())
    agent = make_lead_agent(
        {
            "configurable": {
                "model_name": "r02-scripted",
                "thinking_enabled": False,
                "is_plan_mode": False,
                "subagent_enabled": False,
            }
        }
    )
    result = asyncio.run(
        agent.ainvoke(
            {"messages": [HumanMessage(content=user_text)]},
            context={"thread_id": "r02-official-test"},
        )
    )
    return list(result["messages"])


def _tool_payloads(messages: list) -> list[dict]:
    payloads = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                payloads.append(json.loads(str(message.content)))
            except json.JSONDecodeError:
                payloads.append({"parse_error": True, "raw": str(message.content)})
    return payloads


def _legal_tool_calls(messages: list) -> int:
    count = 0
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") == "legal_augmentation":
                count += 1
    return count


def _final_text(messages: list) -> str:
    return str(messages[-1].content)


def test_official_factory_exposes_full_prompt_and_legal_tool():
    _install_config()
    prompt = apply_prompt_template()
    names = [tool.name for tool in get_available_tools(include_mcp=False, model_name="r02-scripted")]
    assert "<legal_augmentation>" in prompt
    assert "Never include unsupported claims" in prompt
    assert "Do not supply statutes" in prompt
    assert "legal_augmentation" in names


def test_non_legal_scene_does_not_call_legal_tool(monkeypatch):
    class _BoomClient:
        def __init__(self, config):
            raise AssertionError("non-legal scene must not construct the legal client")

    messages = _run_scene("请帮我改一句普通写作", client_factory=_BoomClient, monkeypatch=monkeypatch)
    assert _legal_tool_calls(messages) == 0
    assert _tool_payloads(messages) == []


def test_simple_and_relational_call_only_legal_tool(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def augment(self, request):
            if "关联" in request.question:
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
            return _result()

        async def aclose(self):
            return None

    simple = _run_scene("试用期解除劳动合同的依据", client_factory=_FakeClient, monkeypatch=monkeypatch)
    relational = _run_scene("关联公司关系下的解除依据", client_factory=_FakeClient, monkeypatch=monkeypatch)
    assert _legal_tool_calls(simple) == 1
    assert _legal_tool_calls(relational) == 1
    assert _tool_payloads(simple)[0]["analysis"]["strategy"] == "hybrid_traditional"
    assert _tool_payloads(relational)[0]["analysis"]["strategy"] == "combined"


def test_timeout_scene_does_not_invent_statute(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            raise LegalRAGClientError("timeout", "legal rag request timed out")

        async def aclose(self):
            return None

    messages = _run_scene("劳动合同法第39条是什么？", client_factory=_FakeClient, monkeypatch=monkeypatch)
    text = _final_text(messages)
    assert _tool_payloads(messages)[0]["error_type"] == "timeout"
    assert "不可用" in text
    assert not re.search(r"第.{0,8}条.{0,40}(解除|过失|严重违反|经济补偿)", text)


def test_insufficient_scene_limits_conclusion(monkeypatch):
    class _FakeClient:
        def __init__(self, config):
            pass

        async def augment(self, request):
            return _result(evidence={"mode": "insufficient", "reason": "no_hit"})

        async def aclose(self):
            return None

    text = _final_text(_run_scene("证据不足问题", client_factory=_FakeClient, monkeypatch=monkeypatch))
    assert "证据不足" in text


def test_unsupported_claim_not_paraphrased_into_final(monkeypatch):
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
    final = _final_text(messages)
    assert UNSUPPORTED_TEXT not in final
    assert not any(marker in final for marker in UNSUPPORTED_MARKERS)
    assert "用人单位可依法解除" in final
