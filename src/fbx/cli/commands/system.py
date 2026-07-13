"""`fbx system` — box system status and control."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import system as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Box system status and control.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="system")


@app.command()
def info(ctx: typer.Context) -> None:
    """Show firmware, model, uptime, temperatures, and fans."""
    data = fetch(ctx, api.info)
    ui.emit(data, ctx.obj, table=_system_table)


@app.command()
def standby(ctx: typer.Context) -> None:
    """Show the box's standby planning state."""
    data = fetch(ctx, api.standby_status)
    ui.emit(data, ctx.obj, table=_standby_table)


# -- writes ----------------------------------------------------------------


@app.command()
def reboot(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Reboot the box (drops all connectivity for ~1 minute)."""
    ui.confirm("Reboot the box now? All connectivity will drop briefly. Continue?", yes=yes)
    data = fetch(ctx, api.reboot)
    ui.emit_write(data, ctx.obj, message="reboot requested")


@app.command()
def shutdown(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Shut the box down (it will NOT come back until powered on at the box)."""
    ui.confirm(
        "Shut the box DOWN now? It will stay off until you power it on physically. Continue?",
        yes=yes,
    )
    data = fetch(ctx, api.shutdown)
    ui.emit_write(data, ctx.obj, message="shutdown requested")


@app.command("standby-set")
def standby_set(
    ctx: typer.Context,
    enabled: bool | None = typer.Option(
        None, "--enabled/--disabled", help="Enable time-based standby planning."
    ),
    mode: str | None = typer.Option(None, "--mode", help="Planning mode: wifi_off or suspend."),
) -> None:
    """Update the box's standby planning."""
    fields: dict = {}
    if enabled is not None:
        fields["use_planning"] = enabled
    if mode is not None:
        fields["planning_mode"] = mode
    if not fields:
        ui.error("nothing to change: pass --enabled/--disabled and/or --mode.")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_standby, fields)
    ui.emit_write(data, ctx.obj, message="updated standby planning")


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


def _standby_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Standby")
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Use planning", fmt.yesno(d.get("use_planning")))
    if d.get("planning_mode"):
        t.add_row("Mode", fmt.safe(d.get("planning_mode")))
    modes = d.get("available_planning_modes") or []
    if modes:
        t.add_row("Available modes", ", ".join(fmt.safe(m) for m in modes))
    return t
