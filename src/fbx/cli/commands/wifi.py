"""`fbx wifi` — radios, SSIDs, and associated clients."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import wifi as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Wi-Fi radios, networks, and clients.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="wifi")


@app.command()
def status(ctx: typer.Context) -> None:
    """Show the global Wi-Fi state and detected radios."""
    data = fetch(ctx, api.state)
    ui.emit(data, ctx.obj, table=_status_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the global Wi-Fi configuration."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


@app.command()
def ap(ctx: typer.Context) -> None:
    """List access points (one per radio) with channel and state."""
    data = fetch(ctx, api.aps)
    ui.emit(data, ctx.obj, table=_ap_table)


@app.command()
def bss(ctx: typer.Context) -> None:
    """List broadcast SSIDs with security settings (keys not shown; use --json)."""
    data = fetch(ctx, api.bss)
    ui.emit(data, ctx.obj, table=_bss_table)


@app.command()
def key(ctx: typer.Context) -> None:
    """Print the Wi-Fi passphrase(s).

    Bare value on stdout — `fbx wifi key | pbcopy` grabs it cleanly. With
    several distinct SSIDs, prints one `ssid<TAB>key` line each. This is also
    where to look when an MCP result shows the key `[redacted by fbx…]`.
    """
    data = fetch(ctx, api.bss)
    pairs: list[tuple[str, str]] = []
    for b in data or []:
        cfg = b.get("config") or {}
        ssid, k = cfg.get("ssid"), cfg.get("key")
        if k and (ssid, k) not in pairs:
            pairs.append((ssid, k))
    state: ui.CliState = ctx.obj
    if state.as_json:
        ui.emit_json([{"ssid": s, "key": k} for s, k in pairs])
    elif len(pairs) == 1:
        ui.emit_raw(pairs[0][1] + "\n")
    else:
        ui.emit_raw("".join(f"{s}\t{k}\n" for s, k in pairs))


@app.command()
def neighbors(
    ctx: typer.Context,
    ap_id: int = typer.Argument(..., help="AP id (see `fbx wifi ap` — ids shift)."),
    scan: bool = typer.Option(
        False, "--scan", help="Refresh the survey first (waits for the radio)."
    ),
    wait: float = typer.Option(
        3.0, "--wait", help="Seconds to let a --scan settle before reading."
    ),
) -> None:
    """List neighboring Wi-Fi networks one radio can hear (channel survey)."""
    import time

    def op(client):
        if scan:
            api.neighbors_scan(client, ap_id)
            time.sleep(wait)
        return api.neighbors(client, ap_id)

    data = fetch(ctx, op)
    ui.emit(data, ctx.obj, table=_neighbors_table)


@app.command()
def stations(
    ctx: typer.Context,
    ap_id: int | None = typer.Option(None, "--ap", help="Only clients of this AP id."),
) -> None:
    """List associated Wi-Fi clients across all access points."""
    if ap_id is not None:
        data = fetch(ctx, api.ap_stations, ap_id)
    else:
        data = fetch(ctx, api.stations)
    ui.emit(data, ctx.obj, table=_stations_table)


@app.command("mac-filter")
def mac_filter(ctx: typer.Context) -> None:
    """List MAC access-control entries."""
    data = fetch(ctx, api.mac_filters)
    ui.emit(data, ctx.obj, table=_mac_filter_table)


@app.command()
def planning(ctx: typer.Context) -> None:
    """Show the scheduled Wi-Fi on/off planning."""
    data = fetch(ctx, api.planning)
    ui.emit(data, ctx.obj, table=_planning_table)


# -- writes ----------------------------------------------------------------


@app.command("config-set")
def config_set(
    ctx: typer.Context,
    enabled: bool | None = typer.Option(
        None, "--enabled/--disabled", help="Turn Wi-Fi on or off globally."
    ),
    mac_filter_state: str | None = typer.Option(
        None, "--mac-filter", help="MAC filter mode: disabled, whitelist, or blacklist."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the disable confirmation."),
) -> None:
    """Update the global Wi-Fi configuration."""
    fields: dict = {}
    if enabled is not None:
        fields["enabled"] = enabled
    if mac_filter_state is not None:
        fields["mac_filter_state"] = mac_filter_state
    if not fields:
        ui.error("nothing to change: pass --enabled/--disabled and/or --mac-filter.")
        raise typer.Exit(1)
    if enabled is False:
        ui.confirm(
            "Disable Wi-Fi globally? If this machine is on Wi-Fi you will lose "
            "access to the box. Continue?",
            yes=yes,
        )
    data = fetch(ctx, api.set_config, fields)
    ui.emit_write(data, ctx.obj, message="updated Wi-Fi config")


@app.command("ap-set")
def ap_set(
    ctx: typer.Context,
    ap_id: int = typer.Argument(..., help="Access-point id (see `fbx wifi ap`)."),
    channel: int | None = typer.Option(None, "--channel", help="Primary channel (0 = auto)."),
    channel_width: str | None = typer.Option(
        None, "--channel-width", help="Channel width: 20, 40, 80, 160, 320."
    ),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Toggle the radio."),
) -> None:
    """Change a Wi-Fi radio's channel, width, or enable state."""
    config: dict = {}
    if channel is not None:
        config["primary_channel"] = channel
    if channel_width is not None:
        config["channel_width"] = channel_width
    if enabled is not None:
        config["enabled"] = enabled
    if not config:
        ui.error("nothing to change: pass --channel, --channel-width, and/or --enabled.")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_ap, ap_id, config)
    ui.emit_write(data, ctx.obj, message=f"updated AP {ap_id}")


@app.command("bss-set")
def bss_set(
    ctx: typer.Context,
    bss_id: str = typer.Argument(..., help="BSS id / BSSID (see `fbx wifi bss --json`)."),
    ssid: str | None = typer.Option(None, "--ssid", help="Network name."),
    key: str | None = typer.Option(None, "--key", help="Pre-shared key (password)."),
    encryption: str | None = typer.Option(
        None, "--encryption", help="e.g. wpa2_psk_ccmp, wpa3_psk_ccmp."
    ),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Broadcast or not."),
    hide: bool | None = typer.Option(None, "--hide/--show", help="Hide the SSID."),
) -> None:
    """Change an SSID's name, key, encryption, or visibility."""
    config: dict = {}
    for cfg_key, value in (
        ("ssid", ssid),
        ("key", key),
        ("encryption", encryption),
        ("enabled", enabled),
        ("hide_ssid", hide),
    ):
        if value is not None:
            config[cfg_key] = value
    if not config:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_bss, bss_id, config)
    ui.emit_write(data, ctx.obj, message=f"updated BSS {bss_id}")


@app.command("mac-filter-add")
def mac_filter_add(
    ctx: typer.Context,
    mac: str = typer.Argument(..., help="MAC address to filter."),
    filter_type: str = typer.Option(
        "blacklist", "--type", help="whitelist or blacklist."
    ),
    comment: str = typer.Option("", "--comment", "-c", help="Note."),
) -> None:
    """Add a MAC to the Wi-Fi access-control list."""
    data = fetch(ctx, api.create_mac_filter, mac=mac, type=filter_type, comment=comment)
    ui.emit_write(data, ctx.obj, message=f"added {mac} to the {filter_type}")


@app.command("mac-filter-edit")
def mac_filter_edit(
    ctx: typer.Context,
    filter_id: str = typer.Argument(
        ..., help="Filter id, e.g. 02:..-blacklist (see `fbx wifi mac-filter --json`)."
    ),
    filter_type: str | None = typer.Option(None, "--type", help="whitelist or blacklist."),
    comment: str | None = typer.Option(None, "--comment", "-c", help="New note."),
) -> None:
    """Edit a MAC-filter entry."""
    fields: dict = {}
    if filter_type is not None:
        fields["type"] = filter_type
    if comment is not None:
        fields["comment"] = comment
    if not fields:
        ui.error("nothing to change: pass --type and/or --comment.")
        raise typer.Exit(1)
    data = fetch(ctx, api.update_mac_filter, filter_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated MAC filter {filter_id}")


@app.command("mac-filter-rm")
def mac_filter_rm(
    ctx: typer.Context,
    filter_id: str = typer.Argument(
        ..., help="Filter id, e.g. 02:..-blacklist (see `fbx wifi mac-filter --json`)."
    ),
) -> None:
    """Remove a MAC-filter entry."""
    data = fetch(ctx, api.delete_mac_filter, filter_id)
    ui.emit_write(data, ctx.obj, message=f"removed MAC filter {filter_id}")


@app.command("planning-set")
def planning_set(
    ctx: typer.Context,
    enabled: bool = typer.Option(
        ..., "--enabled/--disabled", help="Enable/disable time-based Wi-Fi planning."
    ),
) -> None:
    """Enable or disable the scheduled Wi-Fi planning."""
    data = fetch(ctx, api.set_planning, {"use_planning": enabled})
    ui.emit_write(data, ctx.obj, message=f"Wi-Fi planning {'enabled' if enabled else 'disabled'}")


@app.command("temp-disable")
def temp_disable(
    ctx: typer.Context,
    duration: int = typer.Option(..., "--duration", help="Seconds to disable Wi-Fi for."),
    keep: str | None = typer.Option(
        None, "--keep", help="Band to leave up (e.g. 2d4g) so you keep a link."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Temporarily disable Wi-Fi for a fixed duration."""
    if keep is None:
        ui.confirm(
            f"Disable ALL Wi-Fi for {duration}s? If this machine is on Wi-Fi you "
            "will lose access (pass --keep <band> to keep one up). Continue?",
            yes=yes,
        )
    data = fetch(ctx, api.temp_disable, duration=duration, keep=keep)
    ui.emit_write(data, ctx.obj, message=f"Wi-Fi disabled for {duration}s")


@app.command("wps-set")
def wps_set(
    ctx: typer.Context,
    enabled: bool = typer.Option(..., "--enabled/--disabled", help="Toggle WPS globally."),
) -> None:
    """Enable or disable WPS."""
    data = fetch(ctx, api.set_wps, enabled)
    ui.emit_write(data, ctx.obj, message=f"WPS {'enabled' if enabled else 'disabled'}")


@app.command("wps-start")
def wps_start(
    ctx: typer.Context,
    bssid: str = typer.Argument(..., help="BSSID to start a WPS pairing session on."),
) -> None:
    """Start a WPS pairing session on a BSS."""
    data = fetch(ctx, api.wps_start, bssid)
    ui.emit_write(data, ctx.obj, message=f"started WPS session on {bssid}")


@app.command("wps-stop")
def wps_stop(ctx: typer.Context) -> None:
    """Clear all active WPS pairing sessions."""
    data = fetch(ctx, api.wps_stop)
    ui.emit_write(data, ctx.obj, message="cleared WPS sessions")


def _status_table(d: dict) -> Table:
    t = Table(box=None, title=f"Wi-Fi — {fmt.safe(d.get('state', '?'))}")
    t.add_column("PHY", justify="right")
    t.add_column("Band")
    t.add_column("Detected")
    for phy in d.get("expected_phys") or []:
        t.add_row(
            str(phy.get("phy_id", "")),
            fmt.safe(phy.get("band")),
            fmt.yesno(phy.get("detected")),
        )
    return t


def _config_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Wi-Fi config")
    t.add_column(style="bold")
    t.add_column()
    rows = [
        ("Enabled", fmt.yesno(d.get("enabled"))),
        ("Power saving", fmt.onoff(d.get("power_saving"))),
        ("MAC filter", d.get("mac_filter_state")),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, fmt.safe(value))
    return t


def _ap_table(items: list) -> Table:
    t = Table(box=None, title="Access points")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Band")
    t.add_column("Channel")
    t.add_column("Width")
    t.add_column("State")
    t.add_column("DFS")
    for a in items:
        cfg = a.get("config") or {}
        st = a.get("status") or {}
        channel = st.get("primary_channel", cfg.get("primary_channel"))
        state = str(st.get("state") or "")
        t.add_row(
            str(a.get("id", "")),
            fmt.safe(a.get("name")),
            fmt.safe(cfg.get("band")),
            str(channel if channel is not None else ""),
            fmt.safe(st.get("channel_width") or cfg.get("channel_width")),
            f"[green]{state}[/]" if state == "active" else fmt.safe(state),
            fmt.yesno(cfg.get("dfs_enabled")),
        )
    return t


def _neighbors_table(items: list) -> Table:
    t = Table(box=None, title="Neighboring networks")
    t.add_column("SSID")
    t.add_column("BSSID")
    t.add_column("Band")
    t.add_column("Channel", justify="right")
    t.add_column("Width")
    t.add_column("Signal", justify="right")
    for n in sorted(items, key=lambda x: x.get("signal", 0), reverse=True):
        signal = n.get("signal")
        t.add_row(
            fmt.safe(n.get("ssid")) or "[dim](hidden)[/]",
            fmt.safe(n.get("bssid")),
            fmt.safe(n.get("band")),
            str(n.get("channel", "")),
            fmt.safe(str(n.get("channel_width", ""))),
            f"{signal} dBm" if signal is not None else "",
        )
    return t


def _bss_table(items: list) -> Table:
    t = Table(box=None, title="Wi-Fi networks (BSS)")
    t.add_column("SSID")
    t.add_column("Band")
    t.add_column("Encryption")
    t.add_column("Hidden")
    t.add_column("State")
    t.add_column("Clients", justify="right")
    for b in items:
        cfg = b.get("config") or {}
        st = b.get("status") or {}
        state = str(st.get("state") or "")
        t.add_row(
            fmt.safe(cfg.get("ssid")),
            fmt.safe(str(st.get("band") or "").lower()),  # bss reports '6G'; normalize
            fmt.safe(cfg.get("encryption")),
            fmt.yesno(cfg.get("hide_ssid")),
            f"[green]{state}[/]" if state == "active" else fmt.safe(state),
            str(st.get("sta_count", "")),
        )
    return t


def _mac_filter_table(items: list) -> Table:
    t = Table(box=None, title=f"Wi-Fi MAC filter — {len(items)}")
    t.add_column("MAC")
    t.add_column("Type")
    t.add_column("Host")
    t.add_column("Comment")
    for f in items:
        t.add_row(
            fmt.safe(f.get("mac")),
            fmt.safe(f.get("type")),
            fmt.safe(f.get("hostname")),
            fmt.safe(f.get("comment")),
        )
    return t


def _planning_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Wi-Fi planning")
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Use planning", fmt.yesno(d.get("use_planning")))
    if d.get("resolution") is not None:
        t.add_row("Resolution", f"{d.get('resolution')} slots/day")
    mapping = d.get("mapping") or []
    if mapping:
        on = sum(1 for slot in mapping if slot in (True, "on"))
        t.add_row("Slots on", f"{on}/{len(mapping)}")
    return t


def _stations_table(items: list) -> Table:
    t = Table(box=None, title=f"Wi-Fi clients — {len(items)}")
    t.add_column("Name")
    t.add_column("MAC")
    t.add_column("AP")
    t.add_column("Band")
    t.add_column("Auth")
    t.add_column("Signal")
    t.add_column("Rate ↓ / ↑")
    t.add_column("Connected")
    for s in items:
        host = s.get("host") or {}
        name = s.get("hostname") or host.get("primary_name") or ""
        ap_info = s.get("_fbx_ap") or {}
        signal = s.get("signal")
        rx = s.get("rx_rate")
        tx = s.get("tx_rate")
        rate = ""
        if rx is not None or tx is not None:
            rate = f"{fmt.human_rate(rx)} / {fmt.human_rate(tx)}"
        t.add_row(
            fmt.safe(name),
            fmt.safe(s.get("mac")),
            fmt.safe(ap_info.get("name") or ap_info.get("id", "")),
            fmt.safe(ap_info.get("band") or s.get("band")),
            fmt.safe(s.get("wpa_alg")),
            f"{signal} dBm" if fmt.is_num(signal) else "",
            rate,
            fmt.duration(s.get("conn_duration")),
        )
    return t
