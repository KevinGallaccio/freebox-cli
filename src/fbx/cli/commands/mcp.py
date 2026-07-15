"""`fbx mcp` — run and wire up the MCP server.

`serve` is what an MCP client launches (stdio); `tools` shows the surface a
given filter set would expose; `install` prints the wiring instructions for
common clients. Only `serve` needs the optional `mcp` dependency.
"""

from __future__ import annotations

import shutil

import typer

from ...mcp import registry
from .. import ui

app = typer.Typer(help="MCP server: let a coding agent drive the box.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="mcp")


def _parse_filters(
    toolsets: str | None, exclude: str | None
) -> tuple[set[str] | None, set[str] | None]:
    """Turn the comma-separated CLI options into sets, validating toolset names."""
    chosen: set[str] | None = None
    if toolsets:
        chosen = {t.strip() for t in toolsets.split(",") if t.strip()}
        unknown = chosen - set(registry.TOOLSETS)
        if unknown:
            ui.error(
                f"unknown toolset(s): {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(registry.TOOLSETS)}"
            )
            raise typer.Exit(1)
    excluded = {e.strip() for e in exclude.split(",") if e.strip()} if exclude else None
    return chosen, excluded


@app.command()
def serve(
    ctx: typer.Context,
    toolsets: str | None = typer.Option(
        None, "--toolsets", help="Comma-separated toolsets to expose (default: all)."
    ),
    read_only: bool = typer.Option(
        False, "--read-only", help="Expose only read tools (no writes at all)."
    ),
    exclude: str | None = typer.Option(
        None, "--exclude", help="Comma-separated tool or toolset names to drop."
    ),
) -> None:
    """Run the MCP server on stdio (an MCP client launches this, not a human).

    Requires the `mcp` extra: `uv tool install 'freebox-cli[mcp]'` (or `pip install
    'freebox-cli[mcp]'`).
    """
    state: ui.CliState = ctx.obj
    chosen, excluded = _parse_filters(toolsets, exclude)
    try:
        from ...mcp import server as mcp_server
    except ImportError as exc:
        ui.error(
            "the MCP server needs the optional `mcp` dependency. Install with "
            "the extra: `uv tool install 'freebox-cli[mcp]'` or "
            "`pip install 'freebox-cli[mcp]'`."
        )
        raise typer.Exit(1) from exc
    mcp_server.serve(
        profile=state.profile,
        host=state.host,
        toolsets=chosen,
        read_only=read_only,
        exclude=excluded,
    )


@app.command()
def tools(
    ctx: typer.Context,
    toolsets: str | None = typer.Option(
        None, "--toolsets", help="Comma-separated toolsets to include (default: all)."
    ),
    read_only: bool = typer.Option(False, "--read-only", help="Only read tools."),
    exclude: str | None = typer.Option(
        None, "--exclude", help="Comma-separated tool or toolset names to drop."
    ),
) -> None:
    """List the tools the server would expose with these filters."""
    chosen, excluded = _parse_filters(toolsets, exclude)
    specs = registry.select(toolsets=chosen, read_only=read_only, exclude=excluded)
    data = [
        {
            "name": s.name,
            "toolset": s.toolset,
            "readonly": s.readonly,
            "destructive": s.destructive,
            "description": s.description,
        }
        for s in specs
    ]
    ui.emit(data, ctx.obj, table=_tools_table)
    ui.info(f"{len(specs)} tools across {len({s.toolset for s in specs})} toolsets", ctx.obj)


def _tools_table(data: list) -> object:
    from rich.table import Table

    from ..fmt import safe

    table = Table(box=None, header_style="bold")
    table.add_column("tool")
    table.add_column("toolset")
    table.add_column("access")
    table.add_column("description", overflow="fold")
    for t in data:
        if t["readonly"]:
            access = "read"
        else:
            access = "write [red]destructive[/]" if t["destructive"] else "write"
        table.add_row(safe(t["name"]), safe(t["toolset"]), access, safe(t["description"]))
    return table


@app.command()
def install(ctx: typer.Context) -> None:
    """Show how to hook the fbx MCP server into MCP clients."""
    state: ui.CliState = ctx.obj
    fbx_path = shutil.which("fbx") or "fbx"
    claude_cmd = f"claude mcp add fbx -- {fbx_path} mcp serve"
    desktop_json = {
        "mcpServers": {"fbx": {"command": fbx_path, "args": ["mcp", "serve"]}}
    }
    if state.as_json:
        ui.emit_json(
            {
                "claude_code": claude_cmd,
                "claude_desktop": desktop_json,
                "command": [fbx_path, "mcp", "serve"],
            }
        )
        return
    ui.info("[bold]Claude Code[/] — run:", state)
    ui.info(f"  {claude_cmd}", state)
    ui.info("", state)
    ui.info(
        "[bold]Claude Code (as a plugin, with the fbx skill included)[/] — in claude, run:",
        state,
    )
    ui.info("  /plugin marketplace add KevinGallaccio/freebox-cli", state)
    ui.info("  /plugin install fbx@fbx", state)
    ui.info("", state)
    ui.info("[bold]Claude Desktop / any MCP client[/] — add to the MCP config:", state)
    import json as _json

    ui.info(f"  {_json.dumps(desktop_json)}", state)
    ui.info("", state)
    ui.info(
        "Optional flags for `serve`: --read-only, --toolsets vm,wifi,…, --exclude raw",
        state,
    )
