from mcp.server.fastmcp import FastMCP

from tool_impl import run_tool as run_tool_impl

mcp = FastMCP("runtime-python-mcp-template")


@mcp.tool()
def run_tool(input_text: str) -> str:
    """Run the runtime-generated tool implementation."""
    return run_tool_impl(input_text)


if __name__ == "__main__":
    mcp.run(transport="stdio")
