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
    """Evaluate whether runtime auto-creation of a new skill is allowed.

    Call this before reading `runtime-skill-builder` or installing a runtime-generated
    `.skill` package. The tool applies the tested `creation_policy.py` rules and stores
    the latest decision in thread state.

    Args:
        has_usable_skill: Whether an existing enabled skill already covers the task.
        normal_tools_can_complete: Whether normal tools can complete the task directly.
        normal_tools_result_stable: Whether the normal-tool result is stable and acceptable.
        is_one_off_request: Whether the request is clearly one-off or temporary.
        is_ambiguous_request: Whether the request is still ambiguous or underspecified.
        user_explicitly_requests_reuse: Whether the user explicitly wants this workflow reused later.
        likely_to_repeat: Whether the workflow is likely to recur.
        has_stable_workflow: Whether the workflow has stable steps.
        has_clear_inputs_outputs: Whether the workflow has clear inputs and outputs.
        has_basic_test_plan: Whether a basic validation path can be defined.
        normal_tools_failed_or_unstable: Whether normal tools already fail or produce unstable results.
        normal_tools_too_costly_or_error_prone: Whether the normal-tool path is too costly or error-prone.
        skill_would_improve_reliability: Whether a skill would clearly improve reliability or success rate.
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
