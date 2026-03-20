from deerflow.skills.creation_policy import (
    SkillCreationDecisionReason,
    SkillCreationSignals,
    evaluate_skill_creation,
)


def _high_value_signals(**overrides) -> SkillCreationSignals:
    data = {
        "auto_create_enabled": True,
        "has_usable_skill": False,
        "normal_tools_can_complete": False,
        "normal_tools_result_stable": False,
        "is_one_off_request": False,
        "is_ambiguous_request": False,
        "likely_to_repeat": True,
        "has_stable_workflow": True,
        "has_clear_inputs_outputs": True,
        "has_basic_test_plan": True,
        "skill_would_improve_reliability": True,
    }
    data.update(overrides)
    return SkillCreationSignals(**data)


def test_existing_skill_blocks_auto_creation():
    decision = evaluate_skill_creation(_high_value_signals(has_usable_skill=True))

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.EXISTING_SKILL_AVAILABLE


def test_normal_tools_sufficient_blocks_auto_creation():
    decision = evaluate_skill_creation(
        _high_value_signals(
            normal_tools_can_complete=True,
            normal_tools_result_stable=True,
        )
    )

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.NORMAL_TOOLS_SUFFICIENT


def test_one_off_request_blocks_auto_creation():
    decision = evaluate_skill_creation(_high_value_signals(is_one_off_request=True))

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.ONE_OFF_REQUEST


def test_ambiguous_request_blocks_auto_creation():
    decision = evaluate_skill_creation(_high_value_signals(is_ambiguous_request=True))

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.AMBIGUOUS_REQUEST


def test_insufficient_deposition_blocks_auto_creation():
    decision = evaluate_skill_creation(
        _high_value_signals(
            likely_to_repeat=False,
            user_explicitly_requests_reuse=False,
            has_stable_workflow=False,
        )
    )

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.INSUFFICIENT_DEPOSITION
    assert decision.deposition_established is False


def test_insufficient_benefit_blocks_auto_creation():
    decision = evaluate_skill_creation(
        _high_value_signals(
            normal_tools_failed_or_unstable=False,
            normal_tools_too_costly_or_error_prone=False,
            skill_would_improve_reliability=False,
        )
    )

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.INSUFFICIENT_BENEFIT
    assert decision.benefit_established is False


def test_auto_creation_allowed_when_deposition_and_benefit_are_established():
    decision = evaluate_skill_creation(
        _high_value_signals(
            normal_tools_failed_or_unstable=True,
            skill_would_improve_reliability=True,
        )
    )

    assert decision.allowed is True
    assert decision.reason is SkillCreationDecisionReason.ALLOW_AUTO_CREATE
    assert decision.deposition_established is True
    assert decision.benefit_established is True


def test_auto_creation_can_be_disabled_globally():
    decision = evaluate_skill_creation(_high_value_signals(auto_create_enabled=False))

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.AUTO_CREATE_DISABLED


def test_thread_limit_blocks_auto_creation():
    decision = evaluate_skill_creation(
        _high_value_signals(
            prior_auto_create_attempts=1,
            max_auto_create_attempts=1,
        )
    )

    assert decision.allowed is False
    assert decision.reason is SkillCreationDecisionReason.THREAD_LIMIT_REACHED


def test_explicit_reuse_request_can_establish_repeatability():
    decision = evaluate_skill_creation(
        _high_value_signals(
            likely_to_repeat=False,
            user_explicitly_requests_reuse=True,
            normal_tools_failed_or_unstable=True,
        )
    )

    assert decision.allowed is True
    assert decision.reason is SkillCreationDecisionReason.ALLOW_AUTO_CREATE
    assert decision.deposition_score >= 3
