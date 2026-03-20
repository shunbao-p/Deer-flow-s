import importlib
from types import SimpleNamespace

from deerflow.skills.updater import SkillUpdateResult

tool_module = importlib.import_module("deerflow.tools.builtins.update_custom_skill_tool")


def _make_runtime(thread_id: str | None = "thread-1") -> SimpleNamespace:
    context = {}
    if thread_id is not None:
        context["thread_id"] = thread_id
    return SimpleNamespace(context=context, state={"thread_data": {}}, config={})


def test_update_custom_skill_tool_updates_from_thread_virtual_path(monkeypatch, tmp_path):
    draft_dir = tmp_path / "weather-helper"
    draft_dir.mkdir()

    monkeypatch.setattr(
        tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: draft_dir),
    )
    monkeypatch.setattr(
        tool_module,
        "update_custom_skill_from_directory",
        lambda skill_name, source_dir: SkillUpdateResult(
            skill_name=skill_name,
            message=f"Skill '{skill_name}' updated successfully",
        ),
    )

    result = tool_module.update_custom_skill_tool.func(
        runtime=_make_runtime(),
        skill_name="weather-helper",
        path="/mnt/user-data/workspace/runtime-skills/weather-helper",
    )

    assert result == "Skill 'weather-helper' updated successfully"


def test_update_custom_skill_tool_requires_thread_id():
    result = tool_module.update_custom_skill_tool.func(
        runtime=_make_runtime(thread_id=None),
        skill_name="weather-helper",
        path="/mnt/user-data/workspace/runtime-skills/weather-helper",
    )

    assert result == "Error: Thread ID is not available in runtime context"


def test_update_custom_skill_tool_rejects_non_thread_virtual_path():
    result = tool_module.update_custom_skill_tool.func(
        runtime=_make_runtime(),
        skill_name="weather-helper",
        path="/tmp/weather-helper",
    )

    assert result == "Error: Path must start with /mnt/user-data"
