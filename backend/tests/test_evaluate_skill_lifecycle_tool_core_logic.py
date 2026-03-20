import importlib
from types import SimpleNamespace

from deerflow.skills.lifecycle_policy import LifecycleCheckOutcome

tool_module = importlib.import_module("deerflow.tools.builtins.evaluate_skill_lifecycle_tool")


def _make_runtime(*, state: dict | None = None, tool_call_id: str = "tc-1") -> SimpleNamespace:
    return SimpleNamespace(
        state=state or {},
        tool_call_id=tool_call_id,
        context={"thread_id": "thread-1"},
    )


def _fake_result(outcome: LifecycleCheckOutcome, *, primary_name: str | None = None, primary_path: str | None = None):
    profile = None
    match = None
    if primary_name is not None:
        profile = SimpleNamespace(name=primary_name, skill_path=primary_path, enabled=True)
        match = SimpleNamespace(profile=profile)
    return SimpleNamespace(
        outcome=outcome,
        primary_match=match,
        similar_matches=tuple([match] if match is not None else []),
        disable_recommendations=("weather-quick",) if outcome == LifecycleCheckOutcome.MULTIPLE_SIMILAR_SKILLS_EXIST else (),
        reason="test-reason",
    )


def test_evaluate_skill_lifecycle_tool_records_no_match(monkeypatch):
    monkeypatch.setattr(
        tool_module,
        "get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills")),
    )
    monkeypatch.setattr(
        tool_module,
        "evaluate_custom_skill_candidate",
        lambda **kwargs: _fake_result(LifecycleCheckOutcome.NO_MATCH),
    )

    result = tool_module.evaluate_skill_lifecycle_tool.func(
        runtime=_make_runtime(),
        name="weather-reporter",
        description="Generate a weather report.",
    )

    assert result.update["skill_lifecycle"]["last_check_outcome"] == "no_match"
    assert result.update["skill_lifecycle"]["checked_candidate_name"] == "weather-reporter"
    assert result.update["messages"][0].content.startswith("NO_MATCH:")


def test_evaluate_skill_lifecycle_tool_reports_primary_match_path(monkeypatch):
    monkeypatch.setattr(
        tool_module,
        "get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills")),
    )
    monkeypatch.setattr(
        tool_module,
        "evaluate_custom_skill_candidate",
        lambda **kwargs: _fake_result(
            LifecycleCheckOutcome.SIMILAR_SKILL_EXISTS,
            primary_name="weather-helper",
            primary_path="weather-helper",
        ),
    )

    result = tool_module.evaluate_skill_lifecycle_tool.func(
        runtime=_make_runtime(),
        name="weather-reporter",
        description="Generate a weather report.",
    )

    assert result.update["skill_lifecycle"]["primary_skill_name"] == "weather-helper"
    assert result.update["skill_lifecycle"]["primary_skill_path"] == "/mnt/skills/custom/weather-helper/SKILL.md"
    assert "Prefer reusing or updating this skill in place" in result.update["messages"][0].content


def test_evaluate_skill_lifecycle_tool_mentions_enable_for_disabled_primary(monkeypatch):
    monkeypatch.setattr(
        tool_module,
        "get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills")),
    )

    def _disabled_result(**kwargs):
        profile = SimpleNamespace(name="weather-helper", skill_path="weather-helper", enabled=False)
        match = SimpleNamespace(profile=profile)
        return SimpleNamespace(
            outcome=LifecycleCheckOutcome.SIMILAR_SKILL_EXISTS,
            primary_match=match,
            similar_matches=(match,),
            disable_recommendations=(),
            reason="test-reason",
        )

    monkeypatch.setattr(tool_module, "evaluate_custom_skill_candidate", _disabled_result)

    result = tool_module.evaluate_skill_lifecycle_tool.func(
        runtime=_make_runtime(),
        name="weather-reporter",
        description="Generate a weather report.",
    )

    assert result.update["skill_lifecycle"]["primary_skill_enabled"] is False
    assert "`enable_skill`" in result.update["messages"][0].content
