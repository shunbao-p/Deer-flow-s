from __future__ import annotations

import logging

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.client import DeerFlowClient
from deerflow.skills.loader import load_skills

logger = logging.getLogger(__name__)


@tool("enable_skill", parse_docstring=True)
def enable_skill_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    skill_name: str,
) -> str:
    """恢复启用一个已有 custom skill。

    只允许作用于 `skills/custom`，不会创建新 skill。

    Args:
        skill_name: 需要恢复启用的 custom skill 名称。
    """
    del runtime

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
                f"Error: Only custom skills can be enabled via this tool. "
                f"'{skill_name}' is a {public_match.category} skill."
            )
        return f"Error: Skill '{skill_name}' not found"
    if skill.enabled:
        return f"Skill '{skill_name}' is already enabled"

    try:
        DeerFlowClient(thinking_enabled=False).update_skill(skill_name, enabled=True, category="custom")
        return f"Skill '{skill_name}' enabled successfully"
    except Exception as exc:
        logger.exception("Unexpected failure in enable_skill tool for skill %s", skill_name)
        return f"Error: Failed to enable skill: {exc}"
