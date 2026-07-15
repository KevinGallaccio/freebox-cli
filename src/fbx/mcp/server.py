"""Wire the registry into the MCP protocol over stdio.

The only module that imports the `mcp` SDK (the optional `fbx[mcp]` extra).
`list_tools` renders the selected `ToolSpec`s with their safety annotations;
`call_tool` dispatches through the runtime on a worker thread (the core is
synchronous httpx). stdout carries the protocol, so nothing here may print —
diagnostics go to stderr via logging.
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any

import anyio.to_thread

from .. import __version__
from .registry import ToolSpec, input_schema, select
from .runtime import FbxRuntime

log = logging.getLogger("fbx.mcp")

INSTRUCTIONS = (
    "Tools for one Freebox (the user's own router/NAS/hypervisor, already "
    "paired). Results are the box's raw JSON. Ids (Wi-Fi APs, VMs, LAN hosts, "
    "port forwards) are only valid freshly listed — discover, then act. For "
    "config-object writes, read the current object first and send only the "
    "fields you mean to change. Tools marked destructive interrupt service or "
    "delete data irreversibly — get explicit user confirmation first."
)


def build_server(runtime: FbxRuntime, specs: list[ToolSpec]) -> Any:
    """An MCP `Server` exposing exactly `specs`, dispatching through `runtime`."""
    from mcp import types
    from mcp.server.lowlevel import Server

    tools_by_name = {spec.name: spec for spec in specs}
    server = Server("fbx", version=__version__, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=input_schema(spec),
                annotations=types.ToolAnnotations(
                    readOnlyHint=spec.readonly,
                    destructiveHint=(spec.destructive if not spec.readonly else False),
                    openWorldHint=spec.open_world,
                ),
            )
            for spec in specs
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        spec = tools_by_name.get(name)
        if spec is None:
            raise ValueError(f"unknown tool: {name}")
        result = await anyio.to_thread.run_sync(
            functools.partial(runtime.call, spec, arguments or {})
        )
        if result is None:
            result = {"success": True}  # the box's bodiless "done" answer
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, default=str),
            )
        ]

    return server


async def _run_stdio(server: Any) -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def serve(
    *,
    profile: str = "default",
    host: str | None = None,
    toolsets: set[str] | None = None,
    read_only: bool = False,
    exclude: set[str] | None = None,
) -> None:
    """Run the stdio MCP server until the client disconnects (blocking)."""
    runtime = FbxRuntime(profile=profile, host=host)
    specs = select(toolsets=toolsets, read_only=read_only, exclude=exclude)
    log.debug("serving %d tools", len(specs))
    server = build_server(runtime, specs)
    try:
        anyio.run(_run_stdio, server)
    finally:
        runtime.close()
