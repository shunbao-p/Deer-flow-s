import importlib
from types import SimpleNamespace

from deerflow.mcp.custom_server_installer import CustomMcpInstallResult
from deerflow.mcp.registrar import CustomMcpRegisterResult
from deerflow.mcp.validator import CustomMcpValidationError, CustomMcpValidationResult

install_tool_module = importlib.import_module("deerflow.tools.builtins.install_custom_mcp_server_tool")
register_tool_module = importlib.import_module("deerflow.tools.builtins.register_custom_mcp_server_tool")


def _make_runtime(
    thread_id: str | None = "thread-1",
    *,
    tool_gap_state: dict | None = None,
) -> SimpleNamespace:
    context = {}
    if thread_id is not None:
        context["thread_id"] = thread_id
    state = {}
    if tool_gap_state is not None:
        state["tool_gap"] = tool_gap_state
    return SimpleNamespace(context=context, state=state, config={})


def test_install_custom_mcp_server_tool_installs_from_thread_virtual_path(monkeypatch, tmp_path):
    project_dir = tmp_path / "weather-tool"
    project_dir.mkdir()

    monkeypatch.setattr(
        install_tool_module,
        "get_paths",
        lambda: SimpleNamespace(
            resolve_virtual_path=lambda thread_id, path: project_dir,
            sandbox_work_dir=lambda thread_id: tmp_path,
        ),
    )
    monkeypatch.setattr(
        install_tool_module,
        "install_custom_mcp_server",
        lambda path, tool_name, workspace_root: CustomMcpInstallResult(
            tool_name=tool_name,
            install_dir=tmp_path / "installed" / tool_name,
            message=f"Custom MCP server '{tool_name}' installed successfully",
        ),
    )

    result = install_tool_module.install_custom_mcp_server_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/workspace/runtime-tools/weather-tool",
        tool_name="weather-tool",
    )

    assert result == "Custom MCP server 'weather-tool' installed successfully"


def test_install_custom_mcp_server_tool_requires_tool_gap_for_runtime_auto_create():
    result = install_tool_module.install_custom_mcp_server_tool.func(
        runtime=_make_runtime(tool_gap_state={"last_decision": "skill_gap"}),
        path="/mnt/user-data/workspace/runtime-tools/weather-tool",
        tool_name="weather-tool",
        source="runtime_auto_create",
    )

    assert "requires a TOOL_GAP result" in result


def test_register_custom_mcp_server_tool_registers_and_validates(monkeypatch):
    monkeypatch.setattr(
        register_tool_module,
        "register_custom_mcp_server",
        lambda tool_name, description="": CustomMcpRegisterResult(
            tool_name=tool_name,
            config_path=None,
            message=f"Custom MCP server '{tool_name}' registered successfully",
        ),
    )
    monkeypatch.setattr(
        register_tool_module,
        "validate_custom_mcp_server",
        lambda tool_name: CustomMcpValidationResult(
            tool_name=tool_name,
            discovered_tools=[f"{tool_name}_run_tool"],
            message="ok",
        ),
    )

    result = register_tool_module.register_custom_mcp_server_tool.func(
        runtime=_make_runtime(tool_gap_state={"last_decision": "tool_gap", "checked_tool_name": "weather-tool"}),
        tool_name="weather-tool",
        description="Weather runtime tool",
        source="runtime_auto_create",
    )

    assert "registered successfully" in result
    assert "weather-tool_run_tool" in result


def test_register_custom_mcp_server_tool_rolls_back_on_validation_failure(monkeypatch):
    rollback_calls: list[str] = []

    monkeypatch.setattr(
        register_tool_module,
        "register_custom_mcp_server",
        lambda tool_name, description="": CustomMcpRegisterResult(
            tool_name=tool_name,
            config_path=None,
            message=f"Custom MCP server '{tool_name}' registered successfully",
        ),
    )
    monkeypatch.setattr(
        register_tool_module,
        "validate_custom_mcp_server",
        lambda tool_name: (_ for _ in ()).throw(CustomMcpValidationError("tool discovery failed")),
    )
    monkeypatch.setattr(
        register_tool_module,
        "unregister_custom_mcp_server",
        lambda tool_name: rollback_calls.append(tool_name),
    )

    result = register_tool_module.register_custom_mcp_server_tool.func(
        runtime=_make_runtime(tool_gap_state={"last_decision": "tool_gap", "checked_tool_name": "weather-tool"}),
        tool_name="weather-tool",
        source="runtime_auto_create",
    )

    assert "rolled back" in result
    assert rollback_calls == ["weather-tool"]
