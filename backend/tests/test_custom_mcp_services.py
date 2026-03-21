import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.mcp.custom_server_installer import (
    CustomMcpServerAlreadyExistsError,
    InvalidCustomMcpServerError,
    install_custom_mcp_server,
)
from deerflow.mcp.registrar import (
    CustomMcpServerAlreadyRegisteredError,
    CustomMcpServerNotInstalledError,
    build_custom_mcp_server_config,
    register_custom_mcp_server,
)
from deerflow.mcp.validator import (
    CustomMcpServerConfigNotFoundError,
    CustomMcpValidationError,
    validate_custom_mcp_server,
)


def _create_runtime_server_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "server.py").write_text("print('server')\n", encoding="utf-8")
    (root / "tool_impl.py").write_text("def run_tool(text: str) -> str:\n    return text\n", encoding="utf-8")
    (root / "requirements.txt").write_text("mcp>=1.0.0\n", encoding="utf-8")
    return root


def test_install_custom_mcp_server_copies_project(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    source = _create_runtime_server_project(workspace_root / "runtime-tools" / "weather-tool")
    install_root = tmp_path / "custom-mcp-servers"

    result = install_custom_mcp_server(
        source,
        "weather-tool",
        install_root=install_root,
        workspace_root=workspace_root,
    )

    assert result.tool_name == "weather-tool"
    assert (install_root / "weather-tool" / "server.py").is_file()
    assert (install_root / "weather-tool" / "tool_impl.py").is_file()


def test_install_custom_mcp_server_rejects_path_outside_workspace(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source = _create_runtime_server_project(tmp_path / "outside-project")

    with pytest.raises(InvalidCustomMcpServerError, match="thread workspace"):
        install_custom_mcp_server(
            source,
            "weather-tool",
            install_root=tmp_path / "custom-mcp-servers",
            workspace_root=workspace_root,
        )


def test_install_custom_mcp_server_rejects_existing_target(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    source = _create_runtime_server_project(workspace_root / "runtime-tools" / "weather-tool")
    install_root = tmp_path / "custom-mcp-servers"
    (install_root / "weather-tool").mkdir(parents=True)

    with pytest.raises(CustomMcpServerAlreadyExistsError, match="already exists"):
        install_custom_mcp_server(
            source,
            "weather-tool",
            install_root=install_root,
            workspace_root=workspace_root,
        )


def test_build_custom_mcp_server_config_uses_container_path():
    config = build_custom_mcp_server_config(
        "weather-tool",
        "Weather runtime tool",
        container_root="/app/custom-mcp-servers",
    )

    assert config.command == "python"
    assert config.args == ["/app/custom-mcp-servers/weather-tool/server.py"]
    assert config.description == "Weather runtime tool"


def test_register_custom_mcp_server_writes_extensions_config(tmp_path: Path, monkeypatch):
    install_root = tmp_path / "custom-mcp-servers"
    _create_runtime_server_project(install_root / "weather-tool")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text('{"mcpServers": {}, "skills": {"custom:demo": {"enabled": true}}}', encoding="utf-8")

    reload_calls: list[str] = []
    reset_calls: list[bool] = []
    monkeypatch.setattr(
        "deerflow.mcp.registrar.reload_extensions_config",
        lambda path=None: reload_calls.append(str(path)),
    )
    monkeypatch.setattr(
        "deerflow.mcp.registrar.reset_mcp_tools_cache",
        lambda: reset_calls.append(True),
    )

    result = register_custom_mcp_server(
        "weather-tool",
        "Weather runtime tool",
        config_path=config_path,
        install_root=install_root,
        container_root="/app/custom-mcp-servers",
    )

    saved = ExtensionsConfig.from_file(str(config_path))
    assert result.tool_name == "weather-tool"
    assert "weather-tool" in saved.mcp_servers
    assert saved.mcp_servers["weather-tool"].args == ["/app/custom-mcp-servers/weather-tool/server.py"]
    assert saved.skills["custom:demo"].enabled is True
    assert reload_calls == [str(config_path)]
    assert reset_calls == [True]


def test_register_custom_mcp_server_rejects_missing_install_dir(tmp_path: Path):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")

    with pytest.raises(CustomMcpServerNotInstalledError, match="not installed"):
        register_custom_mcp_server(
            "weather-tool",
            config_path=config_path,
            install_root=tmp_path / "custom-mcp-servers",
        )


def test_register_custom_mcp_server_rejects_duplicate_entry(tmp_path: Path):
    install_root = tmp_path / "custom-mcp-servers"
    _create_runtime_server_project(install_root / "weather-tool")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        (
            '{"mcpServers": {"weather-tool": {"enabled": true, "type": "stdio", '
            '"command": "python", "args": ["/app/custom-mcp-servers/weather-tool/server.py"]}}, "skills": {}}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(CustomMcpServerAlreadyRegisteredError, match="already registered"):
        register_custom_mcp_server(
            "weather-tool",
            config_path=config_path,
            install_root=install_root,
        )


def test_validate_custom_mcp_server_success(tmp_path: Path, monkeypatch):
    server_path = tmp_path / "custom-mcp-servers" / "weather-tool" / "server.py"
    server_path.parent.mkdir(parents=True)
    server_path.write_text("print('server')\n", encoding="utf-8")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "weather-tool": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "python",
                        "args": [server_path.as_posix()],
                    }
                },
                "skills": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "deerflow.mcp.validator._load_mcp_tools_sync",
        lambda extensions_config: [SimpleNamespace(name="weather-tool_run_tool")],
    )

    result = validate_custom_mcp_server("weather-tool", config_path=config_path)

    assert result.tool_name == "weather-tool"
    assert result.discovered_tools == ["weather-tool_run_tool"]


def test_validate_custom_mcp_server_uses_isolated_server_config(tmp_path: Path, monkeypatch):
    server_path = tmp_path / "custom-mcp-servers" / "weather-tool" / "server.py"
    server_path.parent.mkdir(parents=True)
    server_path.write_text("print('server')\n", encoding="utf-8")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "weather-tool": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "python",
                        "args": [server_path.as_posix()],
                    },
                    "broken-server": {
                        "enabled": True,
                        "type": "stdio",
                        "command": None,
                        "args": [],
                    },
                },
                "skills": {},
            }
        ),
        encoding="utf-8",
    )

    def _fake_load(extensions_config):
        assert set(extensions_config.mcp_servers.keys()) == {"weather-tool"}
        return [SimpleNamespace(name="weather-tool_run_tool")]

    monkeypatch.setattr("deerflow.mcp.validator._load_mcp_tools_sync", _fake_load)

    result = validate_custom_mcp_server("weather-tool", config_path=config_path)

    assert result.discovered_tools == ["weather-tool_run_tool"]


def test_validate_custom_mcp_server_rejects_missing_server_config(tmp_path: Path):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")

    with pytest.raises(CustomMcpServerConfigNotFoundError, match="not present"):
        validate_custom_mcp_server("weather-tool", config_path=config_path)


def test_validate_custom_mcp_server_rejects_missing_discovered_tools(tmp_path: Path, monkeypatch):
    server_path = tmp_path / "custom-mcp-servers" / "weather-tool" / "server.py"
    server_path.parent.mkdir(parents=True)
    server_path.write_text("print('server')\n", encoding="utf-8")
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "weather-tool": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "python",
                        "args": [server_path.as_posix()],
                    }
                },
                "skills": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "deerflow.mcp.validator._load_mcp_tools_sync",
        lambda extensions_config: [SimpleNamespace(name="other-tool_run_tool")],
    )

    with pytest.raises(CustomMcpValidationError, match="did not expose any discoverable tools"):
        validate_custom_mcp_server("weather-tool", config_path=config_path)
