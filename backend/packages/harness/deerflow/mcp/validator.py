"""Minimal validation for registered custom MCP servers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig
from deerflow.mcp.client import build_server_params
from deerflow.mcp.tools import get_mcp_tools_for_extensions_config


@dataclass(frozen=True)
class CustomMcpValidationResult:
    tool_name: str
    discovered_tools: list[str]
    message: str


class CustomMcpValidationError(Exception):
    """Base exception for custom MCP validation failures."""


class CustomMcpServerConfigNotFoundError(KeyError, CustomMcpValidationError):
    """Raised when the target MCP server is not present in config."""


def _validate_stdio_paths(tool_name: str, config: McpServerConfig) -> None:
    if config.type != "stdio":
        return
    if not config.args:
        raise CustomMcpValidationError(
            f"Custom MCP server '{tool_name}' must define args for stdio transport."
        )
    server_path = Path(config.args[0])
    if not server_path.exists():
        raise CustomMcpValidationError(
            f"Custom MCP server '{tool_name}' entry points to a missing path: {server_path}"
        )


def _load_mcp_tools_sync(extensions_config: ExtensionsConfig):
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, get_mcp_tools_for_extensions_config(extensions_config))
                return future.result()
        return loop.run_until_complete(get_mcp_tools_for_extensions_config(extensions_config))
    except RuntimeError:
        import asyncio

        return asyncio.run(get_mcp_tools_for_extensions_config(extensions_config))


def validate_custom_mcp_server(
    tool_name: str,
    *,
    config_path: str | Path | None = None,
) -> CustomMcpValidationResult:
    """Validate that a registered custom MCP server can be built and discovered."""
    extensions_config = ExtensionsConfig.from_file(str(config_path) if config_path else None)
    server_config = extensions_config.mcp_servers.get(tool_name)
    if server_config is None:
        raise CustomMcpServerConfigNotFoundError(
            f"Custom MCP server '{tool_name}' is not present in extensions_config.json"
        )

    build_server_params(tool_name, server_config)
    _validate_stdio_paths(tool_name, server_config)

    isolated_config = ExtensionsConfig(
        mcp_servers={tool_name: server_config},
        skills={},
    )

    discovered_tools = [
        getattr(tool, "name", "")
        for tool in _load_mcp_tools_sync(isolated_config)
        if getattr(tool, "name", "").startswith(f"{tool_name}_")
    ]
    if not discovered_tools:
        raise CustomMcpValidationError(
            f"Custom MCP server '{tool_name}' did not expose any discoverable tools."
        )

    return CustomMcpValidationResult(
        tool_name=tool_name,
        discovered_tools=discovered_tools,
        message=f"Custom MCP server '{tool_name}' validated successfully",
    )
