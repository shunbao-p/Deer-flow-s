from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config
from deerflow.skills.lifecycle_manager import evaluate_custom_skill_candidate


def _to_container_skill_file_path(relative_path: str | None, container_base_path: str) -> str | None:
    if not relative_path:
        return None
    return f"{container_base_path}/custom/{relative_path}/SKILL.md"


@tool("evaluate_skill_lifecycle", parse_docstring=True)
def evaluate_skill_lifecycle_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    name: str,
    description: str,
    workflow: str = "",
    input_output: str = "",
) -> Command:
    """在创建前检查 `skills/custom` 是否已有同名或相近 skill。

    只用于 custom skill 生命周期治理。若发现同名或相近 skill，
    应优先复用或原地修改，而不是继续创建新的近似 skill。

    Args:
        name: 计划创建或调整的 skill 名称。
        description: 候选 skill 的用途描述。
        workflow: 候选 skill 的简要 workflow 文本，可包含步骤列表。
        input_output: 候选 skill 的输入输出或触发场景摘要。
    """
    config = get_app_config()
    result = evaluate_custom_skill_candidate(
        name=name,
        description=description,
        workflow=workflow,
        input_output=input_output,
    )

    primary = result.primary_match.profile if result.primary_match is not None else None
    primary_path = _to_container_skill_file_path(
        primary.skill_path if primary is not None else None,
        config.skills.container_path,
    )
    matched_names = [match.profile.name for match in result.similar_matches]

    if result.outcome == "no_match":
        content = (
            "NO_MATCH: no similar custom skill found. "
            "If runtime skill creation is still needed, continue with `evaluate_skill_creation`."
        )
    elif primary is not None:
        extra = ""
        if result.disable_recommendations:
            extra = f" Disable candidates: {', '.join(result.disable_recommendations)}."
        if primary.enabled:
            reuse_hint = "Prefer reusing or updating this skill in place instead of creating a new near-duplicate."
        else:
            reuse_hint = (
                "The best matching custom skill is currently disabled. Prefer re-enabling it via "
                "`enable_skill` or updating it in place instead of creating a new near-duplicate."
            )
        content = (
            f"{result.outcome.value.upper()}: primary custom skill '{primary.name}'"
            f"{f' at {primary_path}' if primary_path else ''}. "
            f"{reuse_hint}"
            f"{extra}"
        )
    else:
        content = f"{result.outcome.value.upper()}: {result.reason}"

    return Command(
        update={
            "skill_lifecycle": {
                "last_check_outcome": result.outcome.value,
                "last_reason": result.reason,
                "checked_candidate_name": name,
                "primary_skill_name": primary.name if primary is not None else None,
                "primary_skill_path": primary_path,
                "primary_skill_enabled": primary.enabled if primary is not None else None,
                "matched_skill_names": matched_names,
                "disable_recommendations": list(result.disable_recommendations),
            },
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id,
                    name="evaluate_skill_lifecycle",
                )
            ],
        }
    )
