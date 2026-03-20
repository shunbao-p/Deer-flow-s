from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.client import DeerFlowClient
from deerflow.skills.loader import load_skills

logger = logging.getLogger(__name__)

_DISABLE_KEYWORDS = (
    "disable",
    "stop using",
    "don't use",
    "do not use",
    "先不要",
    "不要这个",
    "停用",
    "禁用",
    "暂时不用",
)


def _message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        parts = [part.get("text", "") if isinstance(part, dict) else str(part) for part in content]
        return " ".join(parts)
    return str(content)


def _has_recent_user_disable_request(runtime: ToolRuntime[ContextT, ThreadState], skill_name: str) -> bool:
    state = runtime.state or {}
    messages = state.get("messages") or []
    skill_name_lower = skill_name.lower()
    generic_refs = ("this skill", "该skill", "这个skill", "这个技能", "该技能")

    for message in reversed(messages[-6:]):
        if getattr(message, "type", None) != "human":
            continue
        text = _message_text(message)
        text_lower = text.lower()
        if not any(keyword in text_lower or keyword in text for keyword in _DISABLE_KEYWORDS):
            continue
        if skill_name_lower in text_lower or any(ref in text_lower or ref in text for ref in generic_refs):
            return True
    return False


@tool("disable_skill", parse_docstring=True)
def disable_skill_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    skill_name: str,
    reason: Literal["user_requested", "duplicate_cleanup"] = "user_requested",
) -> str:
    """停用一个已有 custom skill。

    第一阶段只允许停用 `skills/custom` 中的 skill。
    该操作不会删除文件，只会把其 enabled 状态写为 false。

    Args:
        skill_name: 需要停用的 custom skill 名称。
        reason: 停用原因。`user_requested` 需要最近用户消息明确要求停用；
            `duplicate_cleanup` 需要当前线程生命周期检查已将该 skill 标记为弱 skill。
    """
    skill = next(
        (
            item
            for item in load_skills(enabled_only=False)
            if item.name == skill_name and item.category == "custom"
        ),
        None,
    )
    if skill is None:
        public_match = next((item for item in load_skills(enabled_only=False) if item.name == skill_name), None)
        if public_match is not None:
            return (
                f"Error: Only custom skills can be disabled via this tool. "
                f"'{skill_name}' is a {public_match.category} skill."
            )
        return f"Error: Skill '{skill_name}' not found"
    if not skill.enabled:
        return f"Skill '{skill_name}' is already disabled"

    if reason == "duplicate_cleanup":
        lifecycle_state = (runtime.state or {}).get("skill_lifecycle") or {}
        disable_recommendations = set(lifecycle_state.get("disable_recommendations") or [])
        if skill_name not in disable_recommendations:
            return (
                f"Error: Skill '{skill_name}' is not listed in the current lifecycle duplicate-cleanup recommendations."
            )
    elif not _has_recent_user_disable_request(runtime, skill_name):
        return (
            f"Error: No recent explicit user request to disable skill '{skill_name}' was found in this thread."
        )

    try:
        DeerFlowClient(thinking_enabled=False).update_skill(skill_name, enabled=False, category="custom")
        return f"Skill '{skill_name}' disabled successfully"
    except Exception as exc:
        logger.exception("Unexpected failure in disable_skill tool for skill %s", skill_name)
        return f"Error: Failed to disable skill: {exc}"
