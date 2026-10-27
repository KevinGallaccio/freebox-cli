"""Wire the registry into the MCP protocol over stdio.

The only module that imports the `mcp` SDK (the optional `freebox-cli[mcp]` extra).
`_tools` renders the selected `ToolSpec`s with their safety annotations;
`_dispatch` runs a call through the runtime on a worker thread (the core is
synchronous httpx). stdout carries the protocol, so nothing here may print —
diagnostics go to stderr via logging.

The low-level `Server` changed shape between mcp 1.x and 2.x: 1.x registers
handlers with `@server.list_tools()` / `@server.call_tool()` decorators, 2.x
takes them as `on_list_tools=` / `on_call_tool=` constructor arguments and
dropped the decorators. `build_server` supports both so a `uvx` install picks
up whichever the resolver gives it.
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
    "Tools for one Freebox (the user's own router/NAS/hypervisor). Results are "
    "the box's raw JSON. Ids (Wi-Fi APs, VMs, LAN hosts, port forwards) are "
    "only valid freshly listed — discover, then act. For config-object writes, "
    "read the current object first and send only the fields you mean to "
    "change. Tools marked destructive interrupt service or delete data "
    "irreversibly — get explicit user confirmation first. If the box is not "
    "paired yet, fbx_auth_enroll runs the one-time pairing with the user's "
    "help (a physical button press on the box)."
)


def _tools(specs: list[ToolSpec]) -> list[Any]:
    """The `tools/list` payload: every spec with its safety annotations."""
    from mcp import types

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


async def _dispatch(
    runtime: FbxRuntime, tools_by_name: dict[str, ToolSpec], name: str, arguments: dict | None
) -> tuple[list[Any], bool]:
    """Run one call. Returns `(content, is_error)` — failures are tool results
    the model can read ("unknown tool", "not paired"), never protocol errors."""
    from mcp import types

    spec = tools_by_name.get(name)
    if spec is None:
        return [types.TextContent(type="text", text=f"unknown tool: {name}")], True
    try:
        result = await anyio.to_thread.run_sync(
            functools.partial(runtime.call, spec, arguments or {})
        )
    except Exception as exc:  # noqa: BLE001 — every failure must reach the model
        log.debug("tool %s failed", name, exc_info=True)
        return [types.TextContent(type="text", text=str(exc))], True
    if result is None:
        result = {"success": True}  # the box's bodiless "done" answer
    text = json.dumps(result, ensure_ascii=False, default=str)
    return [types.TextContent(type="text", text=text)], False


def build_server(runtime: FbxRuntime, specs: list[ToolSpec]) -> Any:
    """An MCP `Server` exposing exactly `specs`, dispatching through `runtime`."""
    from mcp import types
    from mcp.server.lowlevel import Server

    tools_by_name = {spec.name: spec for spec in specs}

    if hasattr(Server, "list_tools"):
        # mcp 1.x: decorator registration. Every 1.x wrapper turns a raised
        # exception into an `isError` result (returning a CallToolResult
        # directly only works from ~1.10), so failures go back out as a raise.
        server = Server("fbx", version=__version__, instructions=INSTRUCTIONS)

        @server.list_tools()
        async def list_tools() -> list[types.Tool]:
            return _tools(specs)

        @server.call_tool()
        async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
            content, is_error = await _dispatch(runtime, tools_by_name, name, arguments)
            if is_error:
                raise RuntimeError(content[0].text)
            return content

        return server

    # mcp 2.x: handlers are constructor arguments taking (ctx, params). A raise
    # here would become a JSON-RPC error, so `_dispatch` never raises.
    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=_tools(specs))

    async def on_call_tool(ctx: Any, params: Any) -> types.CallToolResult:
        content, is_error = await _dispatch(
            runtime, tools_by_name, params.name, params.arguments
        )
        return types.CallToolResult(content=content, isError=is_error)

    return Server(
        "fbx",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


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
