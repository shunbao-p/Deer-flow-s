"""Install runtime-generated MCP server projects into the shared host directory."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deerflow.config.custom_mcp_config import get_custom_mcp_install_path

_REQUIRED_FILES = ("server.py", "tool_impl.py", "requirements.txt")
_VALID_TOOL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class CustomMcpInstallResult:
    tool_name: str
    install_dir: Path
    message: str


class CustomMcpInstallError(Exception):
    """Base exception for custom MCP installation failures."""


class CustomMcpSourceNotFoundError(FileNotFoundError, CustomMcpInstallError):
    """Raised when the source project path does not exist."""


class InvalidCustomMcpServerError(ValueError, CustomMcpInstallError):
    """Raised when the source directory fails validation."""


class CustomMcpServerAlreadyExistsError(ValueError, CustomMcpInstallError):
    """Raised when the target tool directory already exists."""


def _validate_tool_name(tool_name: str) -> None:
    if not _VALID_TOOL_NAME.fullmatch(tool_name):
        raise InvalidCustomMcpServerError(
            "Tool name must contain only lowercase letters, numbers, hyphens, or underscores, "
            "and must start with a letter or number."
        )


def _ensure_within_workspace(path: Path, workspace_root: Path | None) -> None:
    if workspace_root is None:
        return
    try:
        path.resolve().relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise InvalidCustomMcpServerError(
            f"Source path must stay within the thread workspace: {workspace_root}"
        ) from exc


def _validate_source_project(source_dir: Path) -> None:
    if not source_dir.exists():
        raise CustomMcpSourceNotFoundError(f"Custom MCP server source not found: {source_dir}")
    if not source_dir.is_dir():
        raise InvalidCustomMcpServerError(f"Custom MCP server source is not a directory: {source_dir}")

    missing = [name for name in _REQUIRED_FILES if not (source_dir / name).is_file()]
    if missing:
        raise InvalidCustomMcpServerError(
            "Custom MCP server source is missing required files: " + ", ".join(sorted(missing))
        )


def install_custom_mcp_server(
    source_path: str | Path,
    tool_name: str,
    *,
    install_root: Path | None = None,
    workspace_root: Path | None = None,
) -> CustomMcpInstallResult:
    """Validate and install a runtime-generated MCP server into the host directory."""
    _validate_tool_name(tool_name)

    source_dir = Path(source_path)
    _ensure_within_workspace(source_dir, workspace_root)
    _validate_source_project(source_dir)

    resolved_install_root = (install_root or get_custom_mcp_install_path()).resolve()
    resolved_install_root.mkdir(parents=True, exist_ok=True)
    target_dir = resolved_install_root / tool_name
    if target_dir.exists():
        raise CustomMcpServerAlreadyExistsError(
            f"Custom MCP server '{tool_name}' already exists. Use a different name."
        )

    with tempfile.TemporaryDirectory(dir=resolved_install_root) as temp_dir:
        staging_dir = Path(temp_dir) / tool_name
        shutil.copytree(source_dir, staging_dir)
        shutil.move(str(staging_dir), str(target_dir))

    return CustomMcpInstallResult(
        tool_name=tool_name,
        install_dir=target_dir,
        message=f"Custom MCP server '{tool_name}' installed successfully",
    )
