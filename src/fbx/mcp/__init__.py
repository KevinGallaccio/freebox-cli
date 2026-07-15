"""The fbx MCP server — a second thin adapter over `core.api`.

Same rule as the CLI: no logic lives here. The registry declares which core
functions are exposed as tools (`registry.py`), the runtime owns the one
client and the error mapping (`runtime.py`), and the server wires the registry
into the MCP protocol over stdio (`server.py`). The `mcp` SDK is an optional
dependency (`fbx[mcp]`) imported only by `server.py`, so everything else —
including `fbx mcp tools` — works without it.
"""
