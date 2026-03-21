"""Configuration helpers for runtime-installed custom MCP servers."""

import os
from pathlib import Path

_DEFAULT_CONTAINER_PATH = "/app/custom-mcp-servers"
_HOST_PATH_ENV = "DEER_FLOW_CUSTOM_MCP_SERVERS_HOST_PATH"
_CONTAINER_PATH_ENV = "DEER_FLOW_CUSTOM_MCP_SERVERS_PATH"


def get_custom_mcp_host_path() -> Path:
    """Return the host filesystem path for persistent custom MCP servers."""
    configured = os.getenv(_HOST_PATH_ENV)
    if configured:
        return Path(configured)

    cwd = Path.cwd()
    candidate = cwd / "custom-mcp-servers"
    if candidate.exists() or (cwd / "backend").exists():
        return candidate

    return cwd.parent / "custom-mcp-servers"


def get_custom_mcp_container_path() -> str:
    """Return the container-visible root path for custom MCP servers."""
    configured = os.getenv(_CONTAINER_PATH_ENV)
    if configured:
        return configured
    return _DEFAULT_CONTAINER_PATH


def get_custom_mcp_install_path() -> Path:
    """Return the filesystem path the current DeerFlow process should write to.

    In Docker, DeerFlow writes into the container-visible mount path
    (for example `/app/custom-mcp-servers`). Outside Docker, fall back to the
    host-side repo-relative directory.
    """
    configured_container_path = os.getenv(_CONTAINER_PATH_ENV)
    if configured_container_path:
        return Path(configured_container_path)
    return get_custom_mcp_host_path()
