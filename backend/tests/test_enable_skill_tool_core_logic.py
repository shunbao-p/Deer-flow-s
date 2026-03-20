import importlib
from types import SimpleNamespace

tool_module = importlib.import_module("deerflow.tools.builtins.enable_skill_tool")


def _skill(name: str, *, category: str = "custom", enabled: bool = False):
    return SimpleNamespace(name=name, category=category, enabled=enabled)


def test_enable_skill_tool_enables_custom_skill(monkeypatch):
    calls: list[tuple[str, bool, str | None]] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def update_skill(self, skill_name: str, *, enabled: bool, category: str | None = None):
            calls.append((skill_name, enabled, category))
            return {"name": skill_name, "enabled": enabled}

    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper", enabled=False)])
    monkeypatch.setattr(tool_module, "DeerFlowClient", _FakeClient)

    result = tool_module.enable_skill_tool.func(runtime=SimpleNamespace(), skill_name="weather-helper")

    assert result == "Skill 'weather-helper' enabled successfully"
    assert calls == [("weather-helper", True, "custom")]


def test_enable_skill_tool_reports_already_enabled(monkeypatch):
    monkeypatch.setattr(tool_module, "load_skills", lambda enabled_only=False: [_skill("weather-helper", enabled=True)])

    result = tool_module.enable_skill_tool.func(runtime=SimpleNamespace(), skill_name="weather-helper")

    assert result == "Skill 'weather-helper' is already enabled"
