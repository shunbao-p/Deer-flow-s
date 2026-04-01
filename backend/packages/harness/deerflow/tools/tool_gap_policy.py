"""Pure rule-based policy for deciding whether the missing capability is a tool."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolGapOutcome(str, Enum):
    NO_TOOL_GAP = "no_tool_gap"
    SKILL_GAP = "skill_gap"
    TOOL_GAP = "tool_gap"


class ToolGapReason(str, Enum):
    EXISTING_SKILL_AVAILABLE = "existing_skill_available"
    NORMAL_TOOLS_SUFFICIENT = "normal_tools_sufficient"
    ONE_OFF_REQUEST = "one_off_request"
    AMBIGUOUS_REQUEST = "ambiguous_request"
    FORMAL_TOOL_REUSE_PREFERRED = "formal_tool_reuse_preferred"
    REQUIRES_EXTERNAL_CAPABILITY = "requires_external_capability"
    BETTER_FIT_FOR_SKILL = "better_fit_for_skill"


@dataclass(frozen=True)
class ToolGapSignals:
    has_usable_skill: bool = False
    normal_tools_sufficient: bool = False
    task_requires_external_capability: bool = False
    request_is_one_off: bool = False
    request_is_ambiguous: bool = False
    expected_reuse: bool = False


@dataclass(frozen=True)
class ToolGapDecision:
    outcome: ToolGapOutcome
    reason: ToolGapReason


def evaluate_tool_gap(signals: ToolGapSignals) -> ToolGapDecision:
    """Classify whether the missing capability is best handled as a tool gap.

    Important distinction:
    - "normal_tools_sufficient" means the task can be completed acceptably with
      the current toolbox for the current request.
    - But if the task still needs a durable, registered, formally reusable
      execution capability and the current solution would only be ad hoc
      bash/python glue, a tool gap should still be allowed.
    """
    # 如果当前已经有可用 skill 可以覆盖任务，就不应再进入 tool 创建分支。
    if signals.has_usable_skill:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.EXISTING_SKILL_AVAILABLE,
        )

    # 一次性请求不值得沉淀为新的 MCP tool，直接按当前能力完成即可。
    if signals.request_is_one_off:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.ONE_OFF_REQUEST,
        )

    # 需求仍然含糊时，不能贸然判断为缺 tool，应先澄清需求。
    if signals.request_is_ambiguous:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.AMBIGUOUS_REQUEST,
        )

    # 如果任务明确缺少外部执行能力，且该能力预期会重复复用，则优先判定为正式 tool 缺口。
    if signals.task_requires_external_capability and signals.expected_reuse:
        return ToolGapDecision(
            outcome=ToolGapOutcome.TOOL_GAP,
            reason=ToolGapReason.FORMAL_TOOL_REUSE_PREFERRED,
        )

    # 如果现有普通工具链已经足够完成任务，则不需要再创建新的 tool。
    if signals.normal_tools_sufficient:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.NORMAL_TOOLS_SUFFICIENT,
        )

    # 如果虽然不一定强调长期复用，但任务本身就是缺少外部执行能力，仍可判定为 tool 缺口。
    if signals.task_requires_external_capability:
        return ToolGapDecision(
            outcome=ToolGapOutcome.TOOL_GAP,
            reason=ToolGapReason.REQUIRES_EXTERNAL_CAPABILITY,
        )

    # 其余情况说明更像是流程知识缺失，而不是执行能力缺失，应归到 skill gap。
    return ToolGapDecision(
        outcome=ToolGapOutcome.SKILL_GAP,
        reason=ToolGapReason.BETTER_FIT_FOR_SKILL,
    )
