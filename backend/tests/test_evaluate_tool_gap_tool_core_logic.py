import importlib
from types import SimpleNamespace

tool_module = importlib.import_module("deerflow.tools.builtins.evaluate_tool_gap_tool")


def _make_runtime(*, state: dict | None = None, tool_call_id: str = "tc-1") -> SimpleNamespace:
    return SimpleNamespace(
        state=state or {},
        tool_call_id=tool_call_id,
        context={"thread_id": "thread-1"},
    )


def test_evaluate_tool_gap_tool_records_tool_gap_state():
    result = tool_module.evaluate_tool_gap_tool.func(
        runtime=_make_runtime(),
        task_summary="Need a weather API execution capability",
        task_requires_external_capability=True,
        normal_tools_sufficient=False,
        expected_reuse=True,
        tool_name="weather-tool",
    )

    assert result.update["tool_gap"]["last_decision"] == "tool_gap"
    assert result.update["tool_gap"]["checked_tool_name"] == "weather-tool"
    assert result.update["messages"][0].content.startswith("TOOL_GAP:")


def test_evaluate_tool_gap_tool_returns_skill_gap_when_external_capability_not_needed():
    result = tool_module.evaluate_tool_gap_tool.func(
        runtime=_make_runtime(),
        task_summary="Need a reusable workflow but current tools are enough",
        task_requires_external_capability=False,
        normal_tools_sufficient=False,
        expected_reuse=True,
    )

    assert result.update["tool_gap"]["last_decision"] == "skill_gap"
    assert result.update["messages"][0].content.startswith("SKILL_GAP:")


def test_evaluate_tool_gap_tool_allows_formal_tool_gap_for_reusable_capability():
    result = tool_module.evaluate_tool_gap_tool.func(
        runtime=_make_runtime(),
        task_summary="Need a durable registered host probing capability for later messages",
        task_requires_external_capability=True,
        normal_tools_sufficient=True,
        expected_reuse=True,
        tool_name="host-probe-tool",
    )

    assert result.update["tool_gap"]["last_decision"] == "tool_gap"
    assert result.update["tool_gap"]["last_reason"] == "formal_tool_reuse_preferred"
    assert result.update["messages"][0].content.startswith("TOOL_GAP:")


def test_evaluate_tool_gap_tool_denies_when_existing_tools_are_sufficient():
    result = tool_module.evaluate_tool_gap_tool.func(
        runtime=_make_runtime(),
        task_summary="Current tooling already covers the task",
        task_requires_external_capability=False,
        normal_tools_sufficient=True,
        expected_reuse=False,
    )

    assert result.update["tool_gap"]["last_decision"] == "no_tool_gap"
    assert result.update["messages"][0].content.startswith("NO_TOOL_GAP:")
