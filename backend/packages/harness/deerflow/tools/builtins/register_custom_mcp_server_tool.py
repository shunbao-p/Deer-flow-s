import logging
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.mcp.registrar import (
    CustomMcpRegistrationError,
    register_custom_mcp_server,
    unregister_custom_mcp_server,
)
from deerflow.mcp.validator import CustomMcpValidationError, validate_custom_mcp_server
from deerflow.tools.builtins.install_custom_mcp_server_tool import _validate_runtime_tool_gap_state

logger = logging.getLogger(__name__)


@tool("register_custom_mcp_server", parse_docstring=True)
def register_custom_mcp_server_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    tool_name: str,
    description: str = "",
    source: Literal["manual", "runtime_auto_create"] = "manual",
) -> str:
    """Register an installed custom MCP server and validate that DeerFlow can discover its tools.

    Args:
        tool_name: Installed MCP server name.
        description: Human-readable description for extensions_config.json.
        source: Use `runtime_auto_create` only for the runtime tool evolution flow.
    """
    if source == "runtime_auto_create":
        error = _validate_runtime_tool_gap_state(runtime, tool_name)
        if error is not None:
            return f"Error: {error}"

    try:
        register_result = register_custom_mcp_server(tool_name, description)
        validation_result = validate_custom_mcp_server(tool_name)
        discovered = ", ".join(validation_result.discovered_tools)
        return f"{register_result.message}. Discovered tools: {discovered}"
    except CustomMcpValidationError as exc:
        unregister_custom_mcp_server(tool_name)
        return f"Error: Validation failed after registration and the config entry was rolled back: {exc}"
    except CustomMcpRegistrationError as exc:
        return f"Error: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Unexpected failure in register_custom_mcp_server tool")
        return f"Error: Failed to register custom MCP server: {exc}"
