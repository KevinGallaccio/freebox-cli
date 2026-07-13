"""`fbx connection` — WAN status, config, IPv6, logs, FTTH optics."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import connection as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="WAN connection status and configuration.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="connection")


@app.command()
def status(ctx: typer.Context) -> None:
    """Show WAN state, addresses, and live throughput."""
    data = fetch(ctx, api.status)
    ui.emit(data, ctx.obj, table=_status_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show WAN/remote-access configuration."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


@app.command()
def ipv6(ctx: typer.Context) -> None:
    """Show IPv6 configuration and delegated prefixes."""
    data = fetch(ctx, api.ipv6_config)
    ui.emit(data, ctx.obj, table=_ipv6_table)


@app.command()
def logs(ctx: typer.Context) -> None:
    """Show the WAN link/connection event history."""
    data = fetch(ctx, api.logs)
    ui.emit(data, ctx.obj, table=_logs_table)


@app.command()
def ftth(ctx: typer.Context) -> None:
    """Show FTTH/SFP optical-module health (fiber boxes)."""
    data = fetch(ctx, api.ftth)
    ui.emit(data, ctx.obj, table=_ftth_table)


# -- writes ----------------------------------------------------------------


@app.command("config-set")
def config_set(
    ctx: typer.Context,
    ping: bool | None = typer.Option(None, "--ping/--no-ping", help="Respond to WAN ping."),
    wol: bool | None = typer.Option(None, "--wol/--no-wol", help="Wake-on-LAN proxy."),
    remote_access: bool | None = typer.Option(
        None, "--remote-access/--no-remote-access", help="HTTP remote admin."
    ),
    api_remote_access: bool | None = typer.Option(
        None, "--api-remote-access/--no-api-remote-access", help="Remote API access."
    ),
    adblock: bool | None = typer.Option(None, "--adblock/--no-adblock", help="Ad blocker."),
) -> None:
    """Update WAN / remote-access configuration."""
    fields: dict = {}
    for key, value in (
        ("ping", ping),
        ("wol", wol),
        ("remote_access", remote_access),
        ("api_remote_access", api_remote_access),
        ("adblock", adblock),
    ):
        if value is not None:
            fields[key] = value
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_config, fields)
    ui.emit_write(data, ctx.obj, message="updated connection config")


@app.command("ipv6-set")
def ipv6_set(
    ctx: typer.Context,
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable IPv6."),
    firewall: bool | None = typer.Option(
        None, "--firewall/--no-firewall", help="IPv6 firewall."
    ),
) -> None:
    """Update IPv6 configuration."""
    fields: dict = {}
    if enabled is not None:
        fields["ipv6_enabled"] = enabled
    if firewall is not None:
        fields["ipv6_firewall"] = firewall
    if not fields:
        ui.error("nothing to change: pass --enabled/--disabled and/or --firewall.")
        raise typer.Exit(1)
    data = fetch(ctx, api.set_ipv6_config, fields)
    ui.emit_write(data, ctx.obj, message="updated IPv6 config")


def _kv_table(title: str) -> Table:
    t = Table(show_header=False, box=None, title=title)
    t.add_column(style="bold")
    t.add_column()
    return t


def _status_table(d: dict) -> Table:
    t = _kv_table("Connection")
    state = d.get("state")
    state_style = "green" if state == "up" else "red"
    rows = [
        ("State", f"[{state_style}]{fmt.safe(state)}[/]" if state else None),
        ("Media", fmt.safe(d.get("media"))),
        ("Type", fmt.safe(d.get("type"))),
        ("IPv4", fmt.safe(d.get("ipv4"))),
        ("IPv6", fmt.safe(d.get("ipv6"))),
        ("Rate ↓ / ↑", _pair(fmt.human_rate(d.get("rate_down")), fmt.human_rate(d.get("rate_up")))),
        (
            "Bandwidth ↓ / ↑",
            _pair(fmt.human_bits(d.get("bandwidth_down")), fmt.human_bits(d.get("bandwidth_up"))),
        ),
        (
            "Total ↓ / ↑",
            _pair(fmt.human_bytes(d.get("bytes_down")), fmt.human_bytes(d.get("bytes_up"))),
        ),
    ]
    port_range = d.get("ipv4_port_range")
    if isinstance(port_range, list) and len(port_range) == 2:
        rows.append(("IPv4 port range", f"{port_range[0]}–{port_range[1]}"))
    for label, value in rows:
        if value:
            t.add_row(label, str(value))
    return t


def _pair(a: str, b: str) -> str:
    return f"{a} / {b}" if (a or b) else ""


def _config_table(d: dict) -> Table:
    t = _kv_table("Connection config")
    rows = [
        ("Remote access", fmt.onoff(d.get("remote_access"))),
        ("API remote access", fmt.onoff(d.get("api_remote_access"))),
        ("API domain", fmt.safe(d.get("api_domain"))),
        ("HTTPS port", d.get("https_port")),
        ("Wake-on-LAN proxy", fmt.onoff(d.get("wol"))),
        ("Respond to ping", fmt.onoff(d.get("ping"))),
        ("Ad blocker", fmt.onoff(d.get("adblock"))),
        ("SIP ALG", fmt.safe(d.get("sip_alg"))),
        ("Guest network allowed", fmt.yesno(not d.get("disable_guest", False))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, str(value))
    return t


def _ipv6_table(d: dict) -> Table:
    t = _kv_table("IPv6")
    rows = [
        ("Enabled", fmt.yesno(d.get("ipv6_enabled"))),
        ("Link-local", fmt.safe(d.get("ipv6ll"))),
        ("Firewall", fmt.onoff(d.get("ipv6_firewall"))),
        ("Prefix firewall", fmt.onoff(d.get("ipv6_prefix_firewall"))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, str(value))
    delegations = d.get("delegations") or []
    for i, deleg in enumerate(delegations):
        prefix = deleg.get("prefix") or ""
        next_hop = deleg.get("next_hop") or ""
        label = "Delegations" if i == 0 else ""
        t.add_row(label, fmt.safe(f"{prefix}{f' via {next_hop}' if next_hop else ''}"))
    return t


def _logs_table(entries: list) -> Table:
    t = Table(box=None, title="Connection log")
    t.add_column("Date")
    t.add_column("Type")
    t.add_column("State")
    t.add_column("Details")
    for e in entries:
        details = ""
        if e.get("type") == "link":
            bw = _pair(fmt.human_bits(e.get("bw_down")), fmt.human_bits(e.get("bw_up")))
            details = " ".join(x for x in [fmt.safe(e.get("link")), bw] if x)
        elif e.get("type") == "conn":
            details = fmt.safe(e.get("conn"))
        state = e.get("state") or ""
        style = "green" if state == "up" else "red"
        t.add_row(
            fmt.epoch(e.get("date")),
            fmt.safe(e.get("type")),
            f"[{style}]{fmt.safe(state)}[/]" if state else "",
            details,
        )
    return t


def _ftth_table(d: dict) -> Table:
    t = _kv_table("FTTH / SFP")
    link = d.get("link")
    optical_power = _pair(fmt.centi_dbm(d.get("sfp_pwr_rx")), fmt.centi_dbm(d.get("sfp_pwr_tx")))
    rows = [
        ("Optical link", "[green]up[/]" if link else ("[red]down[/]" if link is False else None)),
        ("Link type", fmt.safe(d.get("link_type"))),
        ("SFP present", fmt.yesno(d.get("sfp_present"))),
        ("SFP model", fmt.safe(_pair2(d.get("sfp_vendor"), d.get("sfp_model")))),
        ("SFP serial", fmt.safe(d.get("sfp_serial"))),
        ("Power RX / TX", optical_power),
        ("SFP power OK", fmt.yesno(d.get("sfp_alim_ok"))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, str(value))
    return t


def _pair2(a: object, b: object) -> str:
    return " ".join(str(x) for x in [a, b] if x)
