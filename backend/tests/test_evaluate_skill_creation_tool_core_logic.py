import importlib
from types import SimpleNamespace

from deerflow.config.app_config import AppConfig

evaluate_tool_module = importlib.import_module("deerflow.tools.builtins.evaluate_skill_creation_tool")


def _make_runtime(*, state: dict | None = None, tool_call_id: str = "tc-1") -> SimpleNamespace:
    return SimpleNamespace(
        state=state or {},
        tool_call_id=tool_call_id,
        context={"thread_id": "thread-1"},
    )


def _make_app_config(*, auto_create_enabled: bool) -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "skills": {
                "container_path": "/mnt/skills",
                "auto_create_enabled": auto_create_enabled,
            },
        }
    )


def test_evaluate_skill_creation_tool_allows_high_value_workflow(monkeypatch):
    monkeypatch.setattr(
        evaluate_tool_module,
        "get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = evaluate_tool_module.evaluate_skill_creation_tool.func(
        runtime=_make_runtime(),
        has_usable_skill=False,
        normal_tools_can_complete=False,
        normal_tools_result_stable=False,
        is_one_off_request=False,
        is_ambiguous_request=False,
        likely_to_repeat=True,
        has_stable_workflow=True,
        has_clear_inputs_outputs=True,
        has_basic_test_plan=True,
        normal_tools_failed_or_unstable=True,
        skill_would_improve_reliability=True,
    )

    assert result.update["skill_creation"]["last_policy_allowed"] is True
    assert result.update["skill_creation"]["last_policy_reason"] == "allow_auto_create"
    assert result.update["messages"][0].content.startswith("ALLOW:")


def test_evaluate_skill_creation_tool_denies_when_disabled(monkeypatch):
    monkeypatch.setattr(
        evaluate_tool_module,
        "get_app_config",
        lambda: _make_app_config(auto_create_enabled=False),
    )

    result = evaluate_tool_module.evaluate_skill_creation_tool.func(
        runtime=_make_runtime(),
        has_usable_skill=False,
        normal_tools_can_complete=False,
        normal_tools_result_stable=False,
        is_one_off_request=False,
        is_ambiguous_request=False,
    )

    assert result.update["skill_creation"]["last_policy_allowed"] is False
    assert result.update["skill_creation"]["last_policy_reason"] == "auto_create_disabled"
    assert result.update["messages"][0].content.startswith("DENY:")


def test_evaluate_skill_creation_tool_uses_thread_attempts(monkeypatch):
    monkeypatch.setattr(
        evaluate_tool_module,
        "get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = evaluate_tool_module.evaluate_skill_creation_tool.func(
        runtime=_make_runtime(
            state={
                "skill_creation": {
                    "auto_create_attempts": 2,
                    "installed_skill_names": [],
                    "last_failure": "Error: Invalid skill archive",
                }
            }
        ),
        has_usable_skill=False,
        normal_tools_can_complete=False,
        normal_tools_result_stable=False,
        is_one_off_request=False,
        is_ambiguous_request=False,
        likely_to_repeat=True,
        has_stable_workflow=True,
        has_clear_inputs_outputs=True,
        normal_tools_failed_or_unstable=True,
    )

    assert result.update["skill_creation"]["last_policy_allowed"] is False
    assert result.update["skill_creation"]["last_policy_reason"] == "thread_limit_reached"
