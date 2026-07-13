"""`fbx system` — box status and control."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core import client as core_client
from .. import ui

app = typer.Typer(help="Box system status and control.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="system")


@app.command()
def info(ctx: typer.Context) -> None:
    """Show firmware, model, uptime, temperatures, and fans."""
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host)
        with fbx:
            result = fbx.get("system/")
    ui.emit(result, state, table=_system_table)


def _system_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="System")
    t.add_column(style="bold")
    t.add_column()
    model = d.get("model_info", {}) or {}
    rows = [
        ("Model", model.get("pretty_name") or d.get("board_name")),
        ("Firmware", d.get("firmware_version")),
        ("MAC", d.get("mac")),
        ("Serial", d.get("serial")),
        ("Uptime", d.get("uptime")),
        ("Disk status", d.get("disk_status")),
    ]
    for label, value in rows:
        if value:
            t.add_row(label, str(value))

    sensors = d.get("sensors") or []
    if sensors:
        temps = ", ".join(f"{s.get('name', '?')} {s.get('value')}°C" for s in sensors)
        t.add_row("Temperatures", temps)
    fans = d.get("fans") or []
    if fans:
        speeds = ", ".join(f"{f.get('name', '?')} {f.get('value')} rpm" for f in fans)
        t.add_row("Fans", speeds)
    return t
