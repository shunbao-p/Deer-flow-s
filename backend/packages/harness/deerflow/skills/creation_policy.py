"""运行时自动创建 skill 的纯决策逻辑。

本模块将“是否应该创建新 skill”的规则从 prompt 和运行时粘合代码中抽离，
以便能够被稳定测试并在不同入口间复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SkillCreationDecisionReason(str, Enum):
    """用于 skill 创建决策的稳定原因码。"""

    AUTO_CREATE_DISABLED = "auto_create_disabled"
    EXISTING_SKILL_AVAILABLE = "existing_skill_available"
    THREAD_LIMIT_REACHED = "thread_limit_reached"
    NORMAL_TOOLS_SUFFICIENT = "normal_tools_sufficient"
    ONE_OFF_REQUEST = "one_off_request"
    AMBIGUOUS_REQUEST = "ambiguous_request"
    INSUFFICIENT_DEPOSITION = "insufficient_deposition"
    INSUFFICIENT_BENEFIT = "insufficient_benefit"
    ALLOW_AUTO_CREATE = "allow_auto_create"


@dataclass(frozen=True)
class SkillCreationSignals:
    """在判断是否允许自动创建前收集的信号。"""

    auto_create_enabled: bool = True
    has_usable_skill: bool = False
    normal_tools_can_complete: bool = False
    normal_tools_result_stable: bool = False
    is_one_off_request: bool = False
    is_ambiguous_request: bool = False
    user_explicitly_requests_reuse: bool = False
    likely_to_repeat: bool = False
    has_stable_workflow: bool = False
    has_clear_inputs_outputs: bool = False
    has_basic_test_plan: bool = False
    normal_tools_failed_or_unstable: bool = False
    normal_tools_too_costly_or_error_prone: bool = False
    skill_would_improve_reliability: bool = False
    prior_auto_create_attempts: int = 0
    max_auto_create_attempts: int | None = None


@dataclass(frozen=True)
class SkillCreationDecision:
    """运行时自动创建 skill 的决策结果。"""

    allowed: bool
    reason: SkillCreationDecisionReason
    deposition_established: bool
    deposition_score: int
    benefit_established: bool
    benefit_score: int


def _evaluate_deposition(signals: SkillCreationSignals) -> tuple[bool, int]:
    """返回该任务是否值得沉淀为可复用工作流。"""
    repeatable = signals.user_explicitly_requests_reuse or signals.likely_to_repeat
    score = sum(
        [
            bool(repeatable),
            signals.has_stable_workflow,
            signals.has_clear_inputs_outputs,
            signals.has_basic_test_plan,
        ]
    )
    established = repeatable and signals.has_stable_workflow and signals.has_clear_inputs_outputs
    return established, score


def _evaluate_benefit(signals: SkillCreationSignals) -> tuple[bool, int]:
    """返回相对普通工具而言，创建 skill 是否具有足够收益。"""
    score = sum(
        [
            signals.normal_tools_failed_or_unstable,
            signals.normal_tools_too_costly_or_error_prone,
            signals.skill_would_improve_reliability,
        ]
    )
    established = score >= 1
    return established, score


def evaluate_skill_creation(signals: SkillCreationSignals) -> SkillCreationDecision:
    """判断是否允许在运行时自动创建 skill。

    决策顺序刻意保持保守：
    1. 先尊重硬性停止条件和当前已有能力。
    2. 过滤掉本应留在普通执行路径中的任务。
    3. 只有当可沉淀性和收益性都成立时，才允许自动创建。
    """

    deposition_established, deposition_score = _evaluate_deposition(signals)
    benefit_established, benefit_score = _evaluate_benefit(signals)

    if not signals.auto_create_enabled:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.AUTO_CREATE_DISABLED,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if signals.has_usable_skill:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.EXISTING_SKILL_AVAILABLE,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if (
        signals.max_auto_create_attempts is not None
        and signals.prior_auto_create_attempts >= signals.max_auto_create_attempts
    ):
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.THREAD_LIMIT_REACHED,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if signals.normal_tools_can_complete and signals.normal_tools_result_stable:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.NORMAL_TOOLS_SUFFICIENT,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if signals.is_one_off_request:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.ONE_OFF_REQUEST,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if signals.is_ambiguous_request:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.AMBIGUOUS_REQUEST,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if not deposition_established:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.INSUFFICIENT_DEPOSITION,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    if not benefit_established:
        return SkillCreationDecision(
            allowed=False,
            reason=SkillCreationDecisionReason.INSUFFICIENT_BENEFIT,
            deposition_established=deposition_established,
            deposition_score=deposition_score,
            benefit_established=benefit_established,
            benefit_score=benefit_score,
        )

    return SkillCreationDecision(
        allowed=True,
        reason=SkillCreationDecisionReason.ALLOW_AUTO_CREATE,
        deposition_established=deposition_established,
        deposition_score=deposition_score,
        benefit_established=benefit_established,
        benefit_score=benefit_score,
    )
