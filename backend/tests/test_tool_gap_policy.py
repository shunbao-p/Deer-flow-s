from deerflow.tools.tool_gap_policy import ToolGapOutcome, ToolGapReason, ToolGapSignals, evaluate_tool_gap


def test_tool_gap_policy_returns_no_gap_when_skill_exists():
    decision = evaluate_tool_gap(
        ToolGapSignals(
            has_usable_skill=True,
            task_requires_external_capability=True,
        )
    )

    assert decision.outcome == ToolGapOutcome.NO_TOOL_GAP
    assert decision.reason == ToolGapReason.EXISTING_SKILL_AVAILABLE


def test_tool_gap_policy_returns_tool_gap_for_external_capability():
    decision = evaluate_tool_gap(
        ToolGapSignals(
            has_usable_skill=False,
            normal_tools_sufficient=False,
            task_requires_external_capability=True,
            expected_reuse=True,
        )
    )

    assert decision.outcome == ToolGapOutcome.TOOL_GAP
    assert decision.reason == ToolGapReason.REQUIRES_EXTERNAL_CAPABILITY


def test_tool_gap_policy_prefers_formal_tool_when_reuse_needed_even_if_ad_hoc_tools_work():
    decision = evaluate_tool_gap(
        ToolGapSignals(
            has_usable_skill=False,
            normal_tools_sufficient=True,
            task_requires_external_capability=True,
            expected_reuse=True,
        )
    )

    assert decision.outcome == ToolGapOutcome.TOOL_GAP
    assert decision.reason == ToolGapReason.FORMAL_TOOL_REUSE_PREFERRED


def test_tool_gap_policy_returns_skill_gap_when_external_capability_not_needed():
    decision = evaluate_tool_gap(
        ToolGapSignals(
            has_usable_skill=False,
            normal_tools_sufficient=False,
            task_requires_external_capability=False,
        )
    )

    assert decision.outcome == ToolGapOutcome.SKILL_GAP
    assert decision.reason == ToolGapReason.BETTER_FIT_FOR_SKILL
