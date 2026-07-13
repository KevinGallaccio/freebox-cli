"""`fbx lan` — the LAN device browser and the box's LAN identity."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import lan as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="LAN devices and configuration.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="lan")
    # Wake-on-LAN is a headline verb; expose it at the top level as `fbx wol`.
    root.command("wol")(wol)


def wol(
    ctx: typer.Context,
    mac: str = typer.Argument(..., help="MAC address of the host to wake."),
    interface: str = typer.Option(
        api.DEFAULT_INTERFACE, "--interface", "-i", help="Browser interface."
    ),
    password: str = typer.Option("", "--password", help="WoL SecureOn password (rare)."),
) -> None:
    """Send a Wake-on-LAN magic packet to a host."""
    data = fetch(ctx, api.wake, mac, interface=interface, password=password)
    ui.emit_write(data, ctx.obj, message=f"sent wake-on-LAN packet to {mac}")


@app.command()
def devices(
    ctx: typer.Context,
    interface: str = typer.Option(
        api.DEFAULT_INTERFACE,
        "--interface",
        "-i",
        help="Browser interface (see `fbx lan interfaces`).",
    ),
    all_: bool = typer.Option(
        False, "--all", "-a", help="Include inactive devices (table view only)."
    ),
) -> None:
    """List devices seen on the LAN (active ones by default)."""
    data = fetch(ctx, api.devices, interface)
    ui.emit(data, ctx.obj, table=lambda hosts: _devices_table(hosts, interface, all_))


@app.command()
def interfaces(ctx: typer.Context) -> None:
    """List browsable LAN interfaces and their host counts."""
    data = fetch(ctx, api.interfaces)
    ui.emit(data, ctx.obj, table=_interfaces_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the box's LAN identity and router/bridge mode."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


@app.command()
def rename(
    ctx: typer.Context,
    host_id: str = typer.Argument(..., help="Host id, e.g. ether-02:00:00:00:00:05."),
    name: str = typer.Argument(..., help="New display name for the device."),
    interface: str = typer.Option(
        api.DEFAULT_INTERFACE, "--interface", "-i", help="Browser interface."
    ),
) -> None:
    """Set a LAN device's display name."""
    data = fetch(ctx, api.update_host, host_id, {"primary_name": name}, interface=interface)
    ui.emit_write(data, ctx.obj, message=f"renamed {host_id} to {name!r}")


@app.command("set-type")
def set_type(
    ctx: typer.Context,
    host_id: str = typer.Argument(..., help="Host id, e.g. ether-02:00:00:00:00:05."),
    host_type: str = typer.Argument(..., help="Device type (e.g. workstation, smartphone)."),
    interface: str = typer.Option(
        api.DEFAULT_INTERFACE, "--interface", "-i", help="Browser interface."
    ),
) -> None:
    """Set a LAN device's type (the icon/category shown in Freebox OS)."""
    data = fetch(ctx, api.update_host, host_id, {"host_type": host_type}, interface=interface)
    ui.emit_write(data, ctx.obj, message=f"set {host_id} type to {host_type}")


@app.command("config-set")
def config_set(
    ctx: typer.Context,
    mode: str | None = typer.Option(None, "--mode", help="LAN mode: router or bridge."),
    ip: str | None = typer.Option(None, "--ip", help="The box's own LAN IPv4."),
    name: str | None = typer.Option(None, "--name", help="Box display name."),
    name_dns: str | None = typer.Option(None, "--name-dns", help="DNS host name."),
    name_mdns: str | None = typer.Option(None, "--name-mdns", help="mDNS/Bonjour name."),
    name_netbios: str | None = typer.Option(None, "--name-netbios", help="NetBIOS name."),
) -> None:
    """Update the box's LAN configuration (mode, IP, names)."""
    fields: dict = {}
    for key, value in (
        ("mode", mode),
        ("ip", ip),
        ("name", name),
        ("name_dns", name_dns),
        ("name_mdns", name_mdns),
        ("name_netbios", name_netbios),
    ):
        if value is not None:
            fields[key] = value
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_config, fields)
    ui.emit_write(data, ctx.obj, message="updated LAN config")


def _devices_table(hosts: list, interface: str, show_all: bool) -> Table:
    shown = hosts if show_all else [h for h in hosts if h.get("active")]
    title = f"Devices on {fmt.safe(interface)} — {len(shown)} shown"
    if not show_all and len(shown) < len(hosts):
        title += f" ({len(hosts) - len(shown)} inactive hidden; --all to include)"
    t = Table(box=None, title=title)
    t.add_column("Name")
    t.add_column("IP")
    t.add_column("MAC")
    t.add_column("Type")
    t.add_column("Access")
    t.add_column("Last seen")

    def sort_key(h: dict):
        return (not h.get("active", False), str(h.get("primary_name") or "").lower())

    for h in sorted(shown, key=sort_key):
        name = fmt.safe(h.get("primary_name") or h.get("default_name") or "?")
        if not h.get("active"):
            name = f"[dim]{name}[/]"
        t.add_row(
            name,
            fmt.safe(_host_ip(h)),
            fmt.safe((h.get("l2ident") or {}).get("id", "")),
            fmt.safe(h.get("host_type")),
            fmt.safe(_host_access(h)),
            fmt.epoch(h.get("last_activity")),
        )
    return t


def _host_ip(h: dict) -> str:
    """Pick a display address: the active IPv4, else the first address."""
    conns = h.get("l3connectivities") or []
    v4 = [c for c in conns if c.get("af") == "ipv4"]
    for pool in (v4, conns):
        for c in pool:
            if c.get("active") and c.get("addr"):
                return str(c["addr"])
    return str(v4[0].get("addr")) if v4 and v4[0].get("addr") else ""


def _host_access(h: dict) -> str:
    ap = h.get("access_point") or {}
    kind = ap.get("connectivity_type")
    if kind == "wifi":
        wifi = ap.get("wifi_information") or {}
        parts = ["wifi", str(wifi.get("band") or "")]
        if fmt.is_num(wifi.get("signal")):
            parts.append(f"{wifi['signal']} dBm")
        return " ".join(p for p in parts if p)
    if kind == "ethernet":
        eth = ap.get("ethernet_information") or {}
        speed = eth.get("speed")
        return f"ethernet {speed} Mb/s" if speed else "ethernet"
    return str(kind or "")


def _interfaces_table(items: list) -> Table:
    t = Table(box=None, title="LAN interfaces")
    t.add_column("Interface")
    t.add_column("Hosts", justify="right")
    for i in items:
        t.add_row(fmt.safe(i.get("name") or "?"), str(i.get("host_count", "")))
    return t


def _config_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="LAN config")
    t.add_column(style="bold")
    t.add_column()
    rows = [
        ("Name", d.get("name")),
        ("Mode", d.get("mode")),
        ("IP", d.get("ip")),
        ("DNS name", d.get("name_dns")),
        ("mDNS name", d.get("name_mdns")),
        ("NetBIOS name", d.get("name_netbios")),
    ]
    for label, value in rows:
        if value:
            t.add_row(label, fmt.safe(value))
    return t
