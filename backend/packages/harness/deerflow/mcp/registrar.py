"""Register installed custom MCP servers into extensions_config.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from deerflow.config.custom_mcp_config import get_custom_mcp_container_path, get_custom_mcp_install_path
from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig, reload_extensions_config
from deerflow.mcp.cache import reset_mcp_tools_cache


@dataclass(frozen=True)
class CustomMcpRegisterResult:
    tool_name: str
    config_path: Path
    message: str


class CustomMcpRegistrationError(Exception):
    """Base exception for registration failures."""


class CustomMcpServerNotInstalledError(FileNotFoundError, CustomMcpRegistrationError):
    """Raised when the custom MCP server directory does not exist."""


class CustomMcpServerAlreadyRegisteredError(ValueError, CustomMcpRegistrationError):
    """Raised when the server name already exists in the MCP config."""


def _write_extensions_config(config_path: Path, extensions_config: ExtensionsConfig) -> None:
    config_data = {
        "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
        "skills": {name: {"enabled": skill.enabled} for name, skill in extensions_config.skills.items()},
    }
    _atomic_write_json(config_path, config_data)
    reload_extensions_config(str(config_path))
    reset_mcp_tools_cache()


def build_custom_mcp_server_config(
    tool_name: str,
    description: str,
    *,
    container_root: str | None = None,
) -> McpServerConfig:
    """Build the standard stdio config for a runtime-generated MCP server."""
    resolved_root = (container_root or get_custom_mcp_container_path()).rstrip("/")
    server_path = f"{resolved_root}/{tool_name}/server.py"
    return McpServerConfig(
        enabled=True,
        type="stdio",
        command="python",
        args=[server_path],
        env={},
        description=description or f"Runtime-generated MCP server for {tool_name}",
    )


def _atomic_write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.flush()
        os.fsync(file.fileno())


def register_custom_mcp_server(
    tool_name: str,
    description: str = "",
    *,
    config_path: str | Path | None = None,
    install_root: Path | None = None,
    container_root: str | None = None,
) -> CustomMcpRegisterResult:
    """Write a standard stdio MCP server entry into extensions_config.json."""
    installed_dir = (install_root or get_custom_mcp_install_path()) / tool_name
    if not installed_dir.is_dir():
        raise CustomMcpServerNotInstalledError(
            f"Custom MCP server '{tool_name}' is not installed at {installed_dir}"
        )

    resolved_config_path = ExtensionsConfig.resolve_config_path(str(config_path) if config_path else None)
    if resolved_config_path is None:
        raise FileNotFoundError(
            "Cannot locate extensions_config.json. Set DEER_FLOW_EXTENSIONS_CONFIG_PATH or create the file first."
        )

    extensions_config = ExtensionsConfig.from_file(str(resolved_config_path))
    if tool_name in extensions_config.mcp_servers:
        raise CustomMcpServerAlreadyRegisteredError(
            f"Custom MCP server '{tool_name}' is already registered."
        )

    extensions_config.mcp_servers[tool_name] = build_custom_mcp_server_config(
        tool_name,
        description,
        container_root=container_root,
    )

    _write_extensions_config(resolved_config_path, extensions_config)

    return CustomMcpRegisterResult(
        tool_name=tool_name,
        config_path=resolved_config_path,
        message=f"Custom MCP server '{tool_name}' registered successfully",
    )


def unregister_custom_mcp_server(
    tool_name: str,
    *,
    config_path: str | Path | None = None,
) -> bool:
    """Remove a custom MCP server entry from extensions_config.json if present."""
    resolved_config_path = ExtensionsConfig.resolve_config_path(str(config_path) if config_path else None)
    if resolved_config_path is None:
        return False

    extensions_config = ExtensionsConfig.from_file(str(resolved_config_path))
    if tool_name not in extensions_config.mcp_servers:
        return False

    del extensions_config.mcp_servers[tool_name]
    _write_extensions_config(resolved_config_path, extensions_config)
    return True
