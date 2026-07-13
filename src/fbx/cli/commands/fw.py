"""`fbx fw` — port forwarding, DMZ, incoming ports, and UPnP IGD."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import fw as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Firewall: port forwarding, DMZ, UPnP IGD.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="fw")


# -- reads -----------------------------------------------------------------


@app.command()
def redirs(ctx: typer.Context) -> None:
    """List static port-forwarding rules."""
    data = fetch(ctx, api.redirs)
    ui.emit(data, ctx.obj, table=_redirs_table)


@app.command()
def dmz(ctx: typer.Context) -> None:
    """Show the DMZ target host."""
    data = fetch(ctx, api.dmz)
    ui.emit(data, ctx.obj, table=_dmz_table)


@app.command()
def incoming(ctx: typer.Context) -> None:
    """List the incoming-port policy for the box's built-in services."""
    data = fetch(ctx, api.incoming)
    ui.emit(data, ctx.obj, table=_incoming_table)


@app.command()
def upnp(ctx: typer.Context) -> None:
    """Show the UPnP IGD (automatic port mapping) service state."""
    data = fetch(ctx, api.upnpigd_config)
    ui.emit(data, ctx.obj, table=_upnp_table)


@app.command("upnp-redirs")
def upnp_redirs(ctx: typer.Context) -> None:
    """List dynamic port mappings created by LAN clients via UPnP."""
    data = fetch(ctx, api.upnpigd_redirs)
    ui.emit(data, ctx.obj, table=_upnp_redirs_table)


# -- writes ----------------------------------------------------------------


@app.command("redir-add")
def redir_add(
    ctx: typer.Context,
    lan_ip: str = typer.Argument(..., help="Destination LAN IPv4."),
    lan_port: int = typer.Argument(..., help="Destination LAN port."),
    wan_port: int = typer.Option(..., "--wan-port", help="WAN port (start of range)."),
    wan_port_end: int | None = typer.Option(
        None, "--wan-port-end", help="WAN port range end (defaults to --wan-port)."
    ),
    proto: str = typer.Option("tcp", "--proto", help="Protocol: tcp or udp."),
    src_ip: str = typer.Option("0.0.0.0", "--src-ip", help="Allowed source IP (0.0.0.0 = any)."),
    comment: str = typer.Option("", "--comment", "-c", help="Rule description."),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Create it enabled."),
) -> None:
    """Add a static port-forwarding rule."""
    fields = {
        "enabled": enabled,
        "comment": comment,
        "lan_ip": lan_ip,
        "lan_port": lan_port,
        "wan_port_start": wan_port,
        "wan_port_end": wan_port if wan_port_end is None else wan_port_end,
        "ip_proto": proto,
        "src_ip": src_ip,
    }
    data = fetch(ctx, api.create_redir, fields)
    ui.emit_write(data, ctx.obj, message=f"forwarded WAN {wan_port} → {lan_ip}:{lan_port}")


@app.command("redir-edit")
def redir_edit(
    ctx: typer.Context,
    redir_id: str = typer.Argument(..., help="Rule id (see `fbx fw redirs`)."),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Toggle the rule."),
    comment: str | None = typer.Option(None, "--comment", "-c", help="New description."),
    lan_ip: str | None = typer.Option(None, "--lan-ip", help="New destination IP."),
    lan_port: int | None = typer.Option(None, "--lan-port", help="New destination port."),
    wan_port: int | None = typer.Option(None, "--wan-port", help="New WAN start port."),
    wan_port_end: int | None = typer.Option(None, "--wan-port-end", help="New WAN end port."),
    proto: str | None = typer.Option(None, "--proto", help="New protocol."),
    src_ip: str | None = typer.Option(None, "--src-ip", help="New allowed source IP."),
) -> None:
    """Edit a static port-forwarding rule."""
    fields: dict = {}
    for key, value in (
        ("enabled", enabled),
        ("comment", comment),
        ("lan_ip", lan_ip),
        ("lan_port", lan_port),
        ("wan_port_start", wan_port),
        ("wan_port_end", wan_port_end),
        ("ip_proto", proto),
        ("src_ip", src_ip),
    ):
        if value is not None:
            fields[key] = value
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_redir, redir_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated port-forward rule {redir_id}")


@app.command("redir-rm")
def redir_rm(
    ctx: typer.Context,
    redir_id: str = typer.Argument(..., help="Rule id (see `fbx fw redirs`)."),
) -> None:
    """Delete a static port-forwarding rule."""
    data = fetch(ctx, api.delete_redir, redir_id)
    ui.emit_write(data, ctx.obj, message=f"deleted port-forward rule {redir_id}")


@app.command("dmz-set")
def dmz_set(
    ctx: typer.Context,
    ip: str = typer.Argument(..., help="LAN IPv4 to expose as the DMZ host."),
) -> None:
    """Point the DMZ at a LAN host (all unsolicited inbound traffic goes there)."""
    data = fetch(ctx, api.set_dmz, {"enabled": True, "ip": ip})
    ui.emit_write(data, ctx.obj, message=f"DMZ → {ip}")


@app.command("dmz-off")
def dmz_off(ctx: typer.Context) -> None:
    """Disable the DMZ."""
    data = fetch(ctx, api.set_dmz, {"enabled": False})
    ui.emit_write(data, ctx.obj, message="DMZ disabled")


@app.command("incoming-set")
def incoming_set(
    ctx: typer.Context,
    port_id: str = typer.Argument(..., help="Service id (see `fbx fw incoming`)."),
    in_port: int | None = typer.Option(None, "--in-port", help="New WAN port for the service."),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Allow inbound."),
) -> None:
    """Reconfigure a built-in service's incoming port."""
    fields: dict = {}
    if in_port is not None:
        fields["in_port"] = in_port
    if enabled is not None:
        fields["enabled"] = enabled
    if not fields:
        ui.error("nothing to change: pass --in-port and/or --enabled/--disabled.")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_incoming, port_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated incoming port {port_id}")


@app.command("upnp-set")
def upnp_set(
    ctx: typer.Context,
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Toggle UPnP IGD."),
    version: int | None = typer.Option(None, "--version", help="IGD protocol version."),
) -> None:
    """Enable/disable UPnP IGD or set its advertised version."""
    fields: dict = {}
    if enabled is not None:
        fields["enabled"] = enabled
    if version is not None:
        fields["version"] = version
    if not fields:
        ui.error("nothing to change: pass --enabled/--disabled and/or --version.")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_upnpigd_config, fields)
    ui.emit_write(data, ctx.obj, message="updated UPnP IGD config")


@app.command("upnp-rm")
def upnp_rm(
    ctx: typer.Context,
    redir_id: str = typer.Argument(..., help="Mapping id (see `fbx fw upnp-redirs`)."),
) -> None:
    """Tear down a UPnP mapping a LAN client created."""
    data = fetch(ctx, api.delete_upnpigd_redir, redir_id)
    ui.emit_write(data, ctx.obj, message=f"deleted UPnP mapping {redir_id}")


# -- tables ----------------------------------------------------------------


def _redirs_table(items: list) -> Table:
    t = Table(box=None, title=f"Port forwarding — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("On")
    t.add_column("Proto")
    t.add_column("WAN port")
    t.add_column("→ LAN")
    t.add_column("Source")
    t.add_column("Comment")
    for r in items:
        ws, we = r.get("wan_port_start"), r.get("wan_port_end")
        wan = str(ws) if ws == we else f"{ws}–{we}"
        t.add_row(
            str(r.get("id", "")),
            fmt.yesno(r.get("enabled")),
            fmt.safe(r.get("ip_proto")),
            wan,
            fmt.safe(f"{r.get('lan_ip', '')}:{r.get('lan_port', '')}"),
            fmt.safe(r.get("src_ip")),
            fmt.safe(r.get("comment")),
        )
    return t


def _dmz_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="DMZ")
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Enabled", fmt.yesno(d.get("enabled")))
    if d.get("ip"):
        t.add_row("Host IP", fmt.safe(d.get("ip")))
    return t


def _incoming_table(items: list) -> Table:
    t = Table(box=None, title=f"Incoming ports — {len(items)}")
    t.add_column("Service")
    t.add_column("Proto")
    t.add_column("On")
    t.add_column("Active")
    t.add_column("Port", justify="right")
    t.add_column("Range")
    t.add_column("Fixed")
    for e in items:
        lo, hi = e.get("min_port"), e.get("max_port")
        t.add_row(
            fmt.safe(e.get("id")),
            fmt.safe(e.get("type")),
            fmt.yesno(e.get("enabled")),
            fmt.yesno(e.get("active")),
            str(e.get("in_port", "")),
            f"{lo}–{hi}" if lo is not None and hi is not None else "",
            fmt.yesno(e.get("readonly")),
        )
    return t


def _upnp_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="UPnP IGD")
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Enabled", fmt.yesno(d.get("enabled")))
    if d.get("version") is not None:
        t.add_row("Version", str(d.get("version")))
    return t


def _upnp_redirs_table(items: list) -> Table:
    t = Table(box=None, title=f"UPnP mappings — {len(items)}")
    t.add_column("ID")
    t.add_column("On")
    t.add_column("Proto")
    t.add_column("WAN port", justify="right")
    t.add_column("→ LAN")
    t.add_column("Description")
    for r in items:
        t.add_row(
            fmt.safe(r.get("id")),
            fmt.yesno(r.get("enabled")),
            fmt.safe(r.get("proto")),
            str(r.get("ext_port", "")),
            fmt.safe(f"{r.get('int_ip', '')}:{r.get('int_port', '')}"),
            fmt.safe(r.get("desc")),
        )
    return t
