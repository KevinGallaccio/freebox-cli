"""`fbx dhcp` — DHCP server config, leases, static reservations."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import dhcp as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="DHCP server: leases and configuration.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="dhcp")


@app.command()
def leases(ctx: typer.Context) -> None:
    """List currently active DHCP leases."""
    data = fetch(ctx, api.dynamic_leases)
    ui.emit(data, ctx.obj, table=_leases_table)


@app.command()
def static(ctx: typer.Context) -> None:
    """List configured static (reserved) leases."""
    data = fetch(ctx, api.static_leases)
    ui.emit(data, ctx.obj, table=_static_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the DHCP server configuration."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


@app.command("static-add")
def static_add(
    ctx: typer.Context,
    mac: str = typer.Argument(..., help="Device MAC to reserve for."),
    ip: str = typer.Argument(..., help="IPv4 to pin to that MAC."),
    comment: str | None = typer.Option(None, "--comment", "-c", help="Reservation note."),
) -> None:
    """Add a static (reserved) DHCP lease."""
    data = fetch(ctx, api.create_static_lease, mac=mac, ip=ip, comment=comment)
    ui.emit_write(data, ctx.obj, message=f"reserved {ip} for {mac}")


@app.command("static-edit")
def static_edit(
    ctx: typer.Context,
    lease_id: str = typer.Argument(..., help="Lease id (the reserved MAC)."),
    ip: str | None = typer.Option(None, "--ip", help="New reserved IPv4."),
    comment: str | None = typer.Option(None, "--comment", "-c", help="New note."),
) -> None:
    """Edit a static DHCP lease (its IP and/or comment)."""
    fields: dict = {}
    if ip is not None:
        fields["ip"] = ip
    if comment is not None:
        fields["comment"] = comment
    if not fields:
        ui.error("nothing to change: pass --ip and/or --comment.")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_static_lease, lease_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated static lease {lease_id}")


@app.command("static-rm")
def static_rm(
    ctx: typer.Context,
    lease_id: str = typer.Argument(..., help="Lease id (the reserved MAC)."),
) -> None:
    """Delete a static DHCP lease."""
    data = fetch(ctx, api.delete_static_lease, lease_id)
    ui.emit_write(data, ctx.obj, message=f"deleted static lease {lease_id}")


@app.command("config-set")
def config_set(
    ctx: typer.Context,
    enabled: bool | None = typer.Option(
        None, "--enabled/--disabled", help="Enable/disable the DHCP server."
    ),
    gateway: str | None = typer.Option(None, "--gateway", help="Gateway IPv4."),
    netmask: str | None = typer.Option(None, "--netmask", help="Subnet mask."),
    ip_range_start: str | None = typer.Option(None, "--range-start", help="Pool start IPv4."),
    ip_range_end: str | None = typer.Option(None, "--range-end", help="Pool end IPv4."),
    dns: list[str] | None = typer.Option(
        None, "--dns", help="DNS server (repeatable; replaces the list)."
    ),
) -> None:
    """Update the DHCP server configuration."""
    fields: dict = {}
    if enabled is not None:
        fields["enabled"] = enabled
    if gateway is not None:
        fields["gateway"] = gateway
    if netmask is not None:
        fields["netmask"] = netmask
    if ip_range_start is not None:
        fields["ip_range_start"] = ip_range_start
    if ip_range_end is not None:
        fields["ip_range_end"] = ip_range_end
    if dns is not None:
        fields["dns"] = dns
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_config, fields)
    ui.emit_write(data, ctx.obj, message="updated DHCP config")


def _leases_table(items: list) -> Table:
    t = Table(box=None, title=f"DHCP leases — {len(items)}")
    t.add_column("Hostname")
    t.add_column("IP")
    t.add_column("MAC")
    t.add_column("Assigned")
    t.add_column("Remaining")
    t.add_column("Static")
    for lease in sorted(items, key=_ip_sort_key):
        t.add_row(
            fmt.safe(lease.get("hostname")),
            fmt.safe(lease.get("ip")),
            fmt.safe(lease.get("mac")),
            fmt.epoch(lease.get("assign_time")),
            fmt.duration(lease.get("lease_remaining")),
            fmt.yesno(lease.get("is_static")),
        )
    return t


def _ip_sort_key(lease: dict):
    ip = str(lease.get("ip") or "")
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return (0, tuple(int(p) for p in parts))
    return (1, ip)


def _static_table(items: list) -> Table:
    t = Table(box=None, title=f"DHCP static leases — {len(items)}")
    t.add_column("Hostname")
    t.add_column("IP")
    t.add_column("MAC")
    t.add_column("Comment")
    t.add_column("Active")
    for lease in sorted(items, key=_ip_sort_key):
        host = lease.get("host") or {}
        t.add_row(
            fmt.safe(lease.get("hostname")),
            fmt.safe(lease.get("ip")),
            fmt.safe(lease.get("mac")),
            fmt.safe(lease.get("comment")),
            fmt.yesno(host.get("active")) if host else "",
        )
    return t


def _config_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="DHCP config")
    t.add_column(style="bold")
    t.add_column()
    ip_start, ip_end = d.get("ip_range_start"), d.get("ip_range_end")
    dns = [str(s) for s in (d.get("dns") or []) if s]
    rows = [
        ("Enabled", fmt.yesno(d.get("enabled"))),
        ("Range", f"{ip_start} – {ip_end}" if ip_start and ip_end else None),
        ("Netmask", d.get("netmask")),
        ("Gateway", d.get("gateway")),
        ("DNS", ", ".join(dns) if dns else None),
        ("Sticky assign", fmt.yesno(d.get("sticky_assign"))),
        ("Always broadcast", fmt.yesno(d.get("always_broadcast"))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, fmt.safe(value))
    return t
