---
name: runtime-tool-builder
description: Create, test, install, and register a minimal Python stdio MCP server during agent runtime when the task needs a missing execution capability and evaluate_tool_gap has already confirmed a TOOL_GAP. Use only after existing skills and current tools are not enough.
---

# Runtime Tool Builder

Use this skill only after the lead agent has already confirmed that the current gap is a real tool gap.
Before using this skill, the agent should have already called `evaluate_tool_gap` and received `TOOL_GAP`.

## Hard Guardrails

Never use this skill when any of the following is true:

- An existing skill already covers the task well enough
- Existing normal tools or current MCP tools are already sufficient
- The request is one-off, temporary, ambiguous, or still missing key requirements
- The task only needs a better workflow description rather than a new execution capability

Your goal is not to build a general platform. Your goal is to build the smallest MCP server that adds the missing execution capability safely.

## Scope

First version supports only:

- Python
- `stdio`
- one MCP server
- one tool

Do not improvise:

- Node
- HTTP
- SSE
- multiple tools

## Working Location

Create the draft MCP server inside the current thread workspace, not directly inside `custom-mcp-servers`.

Recommended layout:

```text
/mnt/user-data/workspace/runtime-tools/<tool-name>/
  server.py
  tool_impl.py
  requirements.txt
  README.md
```

## Step 1: Reconfirm Preconditions

Before writing anything, verify all of these:

1. Existing skills are not sufficient.
2. Existing normal tools and current MCP tools are not sufficient.
3. `evaluate_tool_gap` already returned `TOOL_GAP`.
4. The task really needs a missing execution capability, not just a reusable workflow.
5. The requested capability is stable enough to wrap as one minimal tool.

If any item fails, stop and do not create a tool.

## Step 2: Copy the Fixed Template Shape

Use this exact minimal file set:

- `server.py`
- `tool_impl.py`
- `requirements.txt`
- `README.md`

Preferred canonical template location for developers:

```text
tool-templates/python-mcp-server/
```

At runtime, reproduce the same structure in the thread workspace.

Keep `server.py` as close as possible to this fixed shape:

```python
from mcp.server.fastmcp import FastMCP

from tool_impl import run_tool as run_tool_impl

mcp = FastMCP("runtime-python-mcp-template")


@mcp.tool()
def run_tool(input_text: str) -> str:
    return run_tool_impl(input_text)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Default `tool_impl.py` shape:

```python
def run_tool(input_text: str) -> str:
    return f"Template tool received: {input_text}"
```

Default `requirements.txt`:

```text
mcp>=1.0.0
```

## Step 3: Customize Only the Business Logic

Prefer to modify only:

- `tool_impl.py`
- `README.md`

Only change `requirements.txt` when the capability truly needs extra runtime dependencies.
Avoid changing `server.py` unless the fixed wrapper is definitely insufficient.

Rules for the first version:

- keep a single function named `run_tool`
- keep one string input unless the task absolutely requires more structure
- keep the return value simple and deterministic

## Step 4: Minimal Validation Before Installation

Before installing anything, run at minimum:

```bash
python -m py_compile /mnt/user-data/workspace/runtime-tools/<tool-name>/server.py /mnt/user-data/workspace/runtime-tools/<tool-name>/tool_impl.py
python -c "from pathlib import Path; import sys; sys.path.insert(0, '/mnt/user-data/workspace/runtime-tools/<tool-name>'); from tool_impl import run_tool; print(run_tool('ping'))"
```

Confirm at minimum:

- `server.py` parses
- `tool_impl.py` parses
- `run_tool('ping')` returns a sensible result

If validation fails, fix the draft before installing.

## Step 5: Install the MCP Server Project

After validation succeeds, call:

```python
install_custom_mcp_server(
    path="/mnt/user-data/workspace/runtime-tools/<tool-name>",
    tool_name="<tool-name>",
    source="runtime_auto_create",
)
```

Rules:

- Install only through `install_custom_mcp_server`
- Never write directly into `custom-mcp-servers`
- If installation fails, read the error, fix the workspace draft, and retry only when the fix is concrete

## Step 6: Register and Validate It

After installation succeeds, call:

```python
register_custom_mcp_server(
    tool_name="<tool-name>",
    description="Runtime-generated MCP server for <tool-name>",
    source="runtime_auto_create",
)
```

Rules:

- Register only through `register_custom_mcp_server`
- Never edit `extensions_config.json` directly
- This step must finish successfully before you tell the user the tool is available

## Step 7: After Registration

After successful registration:

1. Tell the user the new tool was created, installed, and registered.
2. State that it will be available in later messages in the same thread.
3. Do not assume the current turn has already rebound the new tool schema.
4. Keep the product semantics consistent: current turn installs, next message uses.

## Quality Bar

The generated MCP server should be:

- minimal
- understandable
- focused on one missing execution capability
- safer than ad hoc bash glue for repeated use

If you cannot meet that bar, do not create a tool.
