import importlib
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

tool_module = importlib.import_module("deerflow.tools.builtins.disable_skill_tool")


def _skill(name: str, *, category: str = "custom", enabled: bool = True):
    return SimpleNamespace(name=name, category=category, enabled=enabled)


def test_disable_skill_tool_disables_custom_skill(monkeypatch):
    calls: list[tuple[str, bool, str | None]] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def update_skill(self, skill_name: str, *, enabled: bool, category: str | None = None):
            calls.append((skill_name, enabled, category))
            return {"name": skill_name, "enabled": enabled}

    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper")])
    monkeypatch.setattr(tool_module, "DeerFlowClient", _FakeClient)

    runtime = SimpleNamespace(state={"messages": [HumanMessage(content="Please disable weather-helper for now.")]})

    result = tool_module.disable_skill_tool.func(runtime=runtime, skill_name="weather-helper")

    assert result == "Skill 'weather-helper' disabled successfully"
    assert calls == [("weather-helper", False, "custom")]


def test_disable_skill_tool_rejects_public_skill(monkeypatch):
    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("bootstrap", category="public")])

    runtime = SimpleNamespace(state={"messages": [HumanMessage(content="Please disable bootstrap.")]})
    result = tool_module.disable_skill_tool.func(runtime=runtime, skill_name="bootstrap")

    assert "Only custom skills can be disabled" in result


def test_disable_skill_tool_reports_already_disabled(monkeypatch):
    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper", enabled=False)])

    runtime = SimpleNamespace(state={"messages": [HumanMessage(content="Please disable weather-helper.")]})
    result = tool_module.disable_skill_tool.func(runtime=runtime, skill_name="weather-helper")

    assert result == "Skill 'weather-helper' is already disabled"


def test_disable_skill_tool_prefers_custom_when_public_has_same_name(monkeypatch):
    calls: list[tuple[str, bool, str | None]] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def update_skill(self, skill_name: str, *, enabled: bool, category: str | None = None):
            calls.append((skill_name, enabled, category))
            return {"name": skill_name, "enabled": enabled, "category": category}

    monkeypatch.setattr(
        tool_module,
        "load_skills",
        lambda enabled_only=False: [
            _skill("weather-helper", category="public"),
            _skill("weather-helper", category="custom"),
        ],
    )
    monkeypatch.setattr(tool_module, "DeerFlowClient", _FakeClient)

    runtime = SimpleNamespace(state={"messages": [HumanMessage(content="Please disable weather-helper.")]})
    result = tool_module.disable_skill_tool.func(runtime=runtime, skill_name="weather-helper")

    assert result == "Skill 'weather-helper' disabled successfully"
    assert calls == [("weather-helper", False, "custom")]


def test_disable_skill_tool_requires_recent_user_request(monkeypatch):
    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper")])

    runtime = SimpleNamespace(state={"messages": [HumanMessage(content="Summarize the weather workflow.")]})
    result = tool_module.disable_skill_tool.func(runtime=runtime, skill_name="weather-helper")

    assert "No recent explicit user request" in result


def test_disable_skill_tool_allows_duplicate_cleanup_with_lifecycle_recommendation(monkeypatch):
    calls: list[tuple[str, bool, str | None]] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def update_skill(self, skill_name: str, *, enabled: bool, category: str | None = None):
            calls.append((skill_name, enabled, category))
            return {"name": skill_name, "enabled": enabled, "category": category}

    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper")])
    monkeypatch.setattr(tool_module, "DeerFlowClient", _FakeClient)

    runtime = SimpleNamespace(
        state={
            "messages": [],
            "skill_lifecycle": {"disable_recommendations": ["weather-helper"]},
        }
    )
    result = tool_module.disable_skill_tool.func(
        runtime=runtime,
        skill_name="weather-helper",
        reason="duplicate_cleanup",
    )

    assert result == "Skill 'weather-helper' disabled successfully"
    assert calls == [("weather-helper", False, "custom")]
