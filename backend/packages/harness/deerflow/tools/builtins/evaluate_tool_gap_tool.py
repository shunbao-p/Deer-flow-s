from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.tools.tool_gap_policy import ToolGapOutcome, ToolGapReason, ToolGapSignals, evaluate_tool_gap


@tool("evaluate_tool_gap", parse_docstring=True)
def evaluate_tool_gap_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    task_summary: str,
    task_requires_external_capability: bool,
    normal_tools_sufficient: bool,
    expected_reuse: bool,
    tool_name: str = "",
    has_usable_skill: bool = False,
    request_is_one_off: bool = False,
    request_is_ambiguous: bool = False,
) -> Command:
    """评估当前缺口是否应进入 runtime MCP tool 创建分支。

    Args:
        task_summary: 当前任务的简要摘要。
        task_requires_external_capability: 任务是否明确需要当前 DeerFlow 不具备的外部执行能力。
        normal_tools_sufficient: 现有普通工具链是否已足够完成任务。
        expected_reuse: 该能力是否预期后续仍会复用，且应沉淀成正式可注册的稳定执行能力。
        tool_name: 计划生成的 tool / MCP server 名称。
        has_usable_skill: 当前是否已有可用 skill 足以完成任务。
        request_is_one_off: 当前请求是否明显只是一次性需求。
        request_is_ambiguous: 当前请求是否仍然含糊不清。
    """
    decision = evaluate_tool_gap(
        ToolGapSignals(
            has_usable_skill=has_usable_skill,
            normal_tools_sufficient=normal_tools_sufficient,
            task_requires_external_capability=task_requires_external_capability,
            request_is_one_off=request_is_one_off,
            request_is_ambiguous=request_is_ambiguous,
            expected_reuse=expected_reuse,
        )
    )

    if decision.outcome == ToolGapOutcome.TOOL_GAP:
        if decision.reason == ToolGapReason.FORMAL_TOOL_REUSE_PREFERRED:
            content = "TOOL_GAP: Ad hoc tools are not enough for a durable reusable execution capability; proceed to runtime tool builder."
        else:
            content = "TOOL_GAP: Existing tools are insufficient; proceed to runtime tool builder."
    elif decision.outcome == ToolGapOutcome.SKILL_GAP:
        content = "SKILL_GAP: This looks like missing workflow knowledge; prefer runtime skill creation instead."
    else:
        content = "NO_TOOL_GAP: Existing skills or tools are sufficient; do not create a new tool."

    return Command(
        update={
            "tool_gap": {
                "last_decision": decision.outcome.value,
                "last_reason": decision.reason.value,
                "checked_task_summary": task_summary,
                "checked_tool_name": tool_name.strip() or None,
            },
            "messages": [
                ToolMessage(
                    content=f"{content} (reason={decision.reason.value})",
                    tool_call_id=runtime.tool_call_id,
                    name="evaluate_tool_gap",
                )
            ],
        }
    )
