from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config
from deerflow.skills.creation_policy import SkillCreationSignals, evaluate_skill_creation

_DEFAULT_MAX_AUTO_CREATE_ATTEMPTS = 2


@tool("evaluate_skill_creation", parse_docstring=True)
def evaluate_skill_creation_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    has_usable_skill: bool,
    normal_tools_can_complete: bool,
    normal_tools_result_stable: bool,
    is_one_off_request: bool,
    is_ambiguous_request: bool,
    user_explicitly_requests_reuse: bool = False,
    likely_to_repeat: bool = False,
    has_stable_workflow: bool = False,
    has_clear_inputs_outputs: bool = False,
    has_basic_test_plan: bool = False,
    normal_tools_failed_or_unstable: bool = False,
    normal_tools_too_costly_or_error_prone: bool = False,
    skill_would_improve_reliability: bool = False,
) -> Command:
    """评估当前是否允许在运行时自动创建新 skill。

    在读取 `runtime-skill-builder` 或安装运行时生成的 `.skill` 包之前，
    应先调用此工具。该工具会执行已经测试过的 `creation_policy.py` 规则，
    并将最新判定结果写入线程状态。

    Args:
        has_usable_skill: 当前是否已有启用中的 skill 足以覆盖该任务。
        normal_tools_can_complete: 普通工具链是否可以直接完成该任务。
        normal_tools_result_stable: 普通工具链的结果是否稳定且可接受。
        is_one_off_request: 当前请求是否明显属于一次性或临时性需求。
        is_ambiguous_request: 当前请求是否仍然存在歧义或关键信息不足。
        user_explicitly_requests_reuse: 用户是否明确表达希望后续复用该流程。
        likely_to_repeat: 该流程后续是否大概率会重复出现。
        has_stable_workflow: 该流程是否具备稳定步骤。
        has_clear_inputs_outputs: 该流程是否具备清晰输入和输出。
        has_basic_test_plan: 是否能够为该流程定义最基本的校验方案。
        normal_tools_failed_or_unstable: 普通工具链是否已经失败过，或结果明显不稳定。
        normal_tools_too_costly_or_error_prone: 普通工具链是否成本过高或容易出错。
        skill_would_improve_reliability: skill 化后是否能明显提升可靠性或成功率。
    """
    thread_state = runtime.state or {}
    current_skill_state = dict(thread_state.get("skill_creation") or {})
    attempts = int(current_skill_state.get("auto_create_attempts") or 0)

    signals = SkillCreationSignals(
        auto_create_enabled=get_app_config().skills.auto_create_enabled,
        has_usable_skill=has_usable_skill,
        normal_tools_can_complete=normal_tools_can_complete,
        normal_tools_result_stable=normal_tools_result_stable,
        is_one_off_request=is_one_off_request,
        is_ambiguous_request=is_ambiguous_request,
        user_explicitly_requests_reuse=user_explicitly_requests_reuse,
        likely_to_repeat=likely_to_repeat,
        has_stable_workflow=has_stable_workflow,
        has_clear_inputs_outputs=has_clear_inputs_outputs,
        has_basic_test_plan=has_basic_test_plan,
        normal_tools_failed_or_unstable=normal_tools_failed_or_unstable,
        normal_tools_too_costly_or_error_prone=normal_tools_too_costly_or_error_prone,
        skill_would_improve_reliability=skill_would_improve_reliability,
        prior_auto_create_attempts=attempts,
        max_auto_create_attempts=_DEFAULT_MAX_AUTO_CREATE_ATTEMPTS,
    )
    decision = evaluate_skill_creation(signals)

    decision_text = (
        f"{'ALLOW' if decision.allowed else 'DENY'}: {decision.reason.value} "
        f"(deposition_score={decision.deposition_score}, benefit_score={decision.benefit_score})"
    )

    updated_skill_state = {
        "auto_create_attempts": attempts,
        "installed_skill_names": list(current_skill_state.get("installed_skill_names") or []),
        "last_failure": current_skill_state.get("last_failure"),
        "last_policy_allowed": decision.allowed,
        "last_policy_reason": decision.reason.value,
    }

    return Command(
        update={
            "skill_creation": updated_skill_state,
            "messages": [
                ToolMessage(
                    content=decision_text,
                    tool_call_id=runtime.tool_call_id,
                    name="evaluate_skill_creation",
                )
            ],
        }
    )
