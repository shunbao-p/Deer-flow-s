import logging
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.mcp.custom_server_installer import (
    CustomMcpInstallError,
    install_custom_mcp_server,
)
from deerflow.tools.tool_gap_policy import ToolGapOutcome

logger = logging.getLogger(__name__)


def _validate_runtime_tool_gap_state(runtime: ToolRuntime[ContextT, ThreadState], tool_name: str) -> str | None:
    tool_gap_state = dict((runtime.state or {}).get("tool_gap") or {})
    last_decision = tool_gap_state.get("last_decision")
    checked_tool_name = tool_gap_state.get("checked_tool_name")

    if last_decision != ToolGapOutcome.TOOL_GAP.value:
        return "Runtime tool creation requires a TOOL_GAP result from `evaluate_tool_gap` first."
    if checked_tool_name and checked_tool_name != tool_name:
        return (
            "Runtime tool install target does not match the most recent tool-gap-approved name. "
            f"Approved: {checked_tool_name}; attempted: {tool_name}."
        )
    return None


@tool("install_custom_mcp_server", parse_docstring=True)
def install_custom_mcp_server_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    tool_name: str,
    source: Literal["manual", "runtime_auto_create"] = "manual",
) -> str:
    """Install a runtime-generated MCP server project from the current thread workspace.

    Args:
        path: Absolute virtual path to the MCP server project directory under `/mnt/user-data/workspace`.
        tool_name: Final installed MCP server name.
        source: Use `runtime_auto_create` only for the runtime tool evolution flow.
    """
    thread_id = runtime.context.get("thread_id") if runtime is not None else None
    if not thread_id:
        return "Error: Thread ID is not available in runtime context"

    normalized_prefix = VIRTUAL_PATH_PREFIX.rstrip("/")
    if path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
        return f"Error: Path must start with {VIRTUAL_PATH_PREFIX}"

    if source == "runtime_auto_create":
        error = _validate_runtime_tool_gap_state(runtime, tool_name)
        if error is not None:
            return f"Error: {error}"

    try:
        resolved_path = get_paths().resolve_virtual_path(thread_id, path)
        workspace_root = get_paths().sandbox_work_dir(thread_id)
        result = install_custom_mcp_server(
            resolved_path,
            tool_name,
            workspace_root=workspace_root,
        )
        return result.message
    except CustomMcpInstallError as exc:
        return f"Error: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Unexpected failure in install_custom_mcp_server tool for thread %s", thread_id)
        return f"Error: Failed to install custom MCP server: {exc}"
