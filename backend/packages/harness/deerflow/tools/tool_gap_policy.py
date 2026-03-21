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
    if signals.has_usable_skill:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.EXISTING_SKILL_AVAILABLE,
        )

    if signals.request_is_one_off:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.ONE_OFF_REQUEST,
        )

    if signals.request_is_ambiguous:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.AMBIGUOUS_REQUEST,
        )

    if signals.task_requires_external_capability and signals.expected_reuse:
        return ToolGapDecision(
            outcome=ToolGapOutcome.TOOL_GAP,
            reason=ToolGapReason.FORMAL_TOOL_REUSE_PREFERRED,
        )

    if signals.normal_tools_sufficient:
        return ToolGapDecision(
            outcome=ToolGapOutcome.NO_TOOL_GAP,
            reason=ToolGapReason.NORMAL_TOOLS_SUFFICIENT,
        )

    if signals.task_requires_external_capability:
        return ToolGapDecision(
            outcome=ToolGapOutcome.TOOL_GAP,
            reason=ToolGapReason.REQUIRES_EXTERNAL_CAPABILITY,
        )

    return ToolGapDecision(
        outcome=ToolGapOutcome.SKILL_GAP,
        reason=ToolGapReason.BETTER_FIT_FOR_SKILL,
    )
