# Python MCP Server Template

This is the minimal Python `stdio` MCP server template for DeerFlow runtime tool creation.

Files:

- `server.py`: Fixed MCP protocol layer using FastMCP
- `tool_impl.py`: Business logic entrypoint
- `requirements.txt`: Minimal runtime dependency

Minimal local checks:

```bash
python -m py_compile server.py tool_impl.py
python -c "from tool_impl import run_tool; print(run_tool('ping'))"
```
