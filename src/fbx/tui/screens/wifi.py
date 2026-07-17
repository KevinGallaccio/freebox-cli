"""Wi-Fi: radios, networks, clients, MAC filter, and the switches.

Radio *configuration* (channels, widths, Wi-Fi generations) is deliberately
read-only here — those are operator decisions made in the CLI with full
context (`fbx wifi ap-set`), and this box's 2.4 GHz tuning is intentional.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ...core.api import wifi
from .. import fmt
from ..i18n import _, _p
from ..support import BoxCallError
from ..widgets import Field, FormModal, TextModal, cursor_key, refill
from ._base import BoxScreen


class WifiScreen(BoxScreen):
    POLL_INTERVAL = 5.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("k", "reveal_key", "Show key"),
        Binding("s", "survey", "Neighbor survey"),
        Binding("t", "temp_disable", "Temp-disable…"),
        Binding("W", "toggle_wifi", "Wi-Fi on/off"),
        Binding("P", "toggle_wps", "WPS on/off"),
        Binding("a", "add_filter", "Add MAC filter"),
        Binding("d", "delete_filter", "Delete filter"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._config: dict = {}
        self._wps: dict = {}
        self._filter_by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("…", id="wifi-summary", classes="panel")
        with TabbedContent():
            with TabPane(_("Radios"), id="tab-radios"):
                yield DataTable(id="aps", cursor_type="row")
                yield Static("", id="neighbors-title", classes="pane-title")
                yield DataTable(id="neighbors", cursor_type="row")
            with TabPane(_("Networks"), id="tab-bss"):
                yield DataTable(id="bss", cursor_type="row")
            with TabPane(_("Clients"), id="tab-stations"):
                yield DataTable(id="stations", cursor_type="row")
            with TabPane(_("MAC filter"), id="tab-filter"):
                yield DataTable(id="filters", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#aps", DataTable).add_columns(
            "Id", _("Radio"), _("Band"), _("Channel"), _("Width"), _("State")
        )
        self.query_one("#neighbors", DataTable).add_columns(
            "SSID", "BSSID", _("Band"), _("Channel"), _("Signal")
        )
        self.query_one("#bss", DataTable).add_columns(
            "SSID", "BSSID", _("Enabled"), _("Security")
        )
        self.query_one("#stations", DataTable).add_columns(
            _("Name"), "MAC", _("AP"), _("Band"), _("Signal"), _("Rate ↓/↑"), _("Connected")
        )
        self.query_one("#filters", DataTable).add_columns("MAC", _("Type"), _("Comment"))
        super().on_mount()

    async def refresh_data(self) -> None:
        self._config = await self.box(wifi.config)
        self._wps = await self.box(wifi.wps_config)
        self.query_one("#wifi-summary", Static).update(
            f"Wi-Fi {fmt.onoff(self._config.get('enabled'))} · "
            f"{_('MAC filter')} "
            f"{fmt.safe(_p('mac-filter', str(self._config.get('mac_filter_state') or '')))} · "
            f"WPS {fmt.onoff(self._wps.get('enabled'))}"
        )

        aps = await self.box(wifi.aps)
        rows = []
        for a in aps:
            cfg, st = a.get("config") or {}, a.get("status") or {}
            rows.append(
                (
                    str(a.get("id", "")),
                    str(a.get("name") or ""),
                    str(cfg.get("band") or ""),
                    str(st.get("primary_channel") or cfg.get("primary_channel") or ""),
                    str(st.get("channel_width") or cfg.get("channel_width") or ""),
                    _p("ap-state", str(st.get("state") or "")),
                )
            )
        refill(
            self.query_one("#aps", DataTable), rows, [str(a.get("id")) for a in aps]
        )

        active = self.query_one(TabbedContent).active
        if active == "tab-bss":
            networks = await self.box(wifi.bss)
            rows = []
            for b in networks:
                cfg = b.get("config") or {}
                rows.append(
                    (
                        str(cfg.get("ssid") or ""),
                        str(b.get("id") or ""),
                        "●" if cfg.get("enabled") else "○",
                        str(cfg.get("encryption") or ""),
                    )
                )
            refill(self.query_one("#bss", DataTable), rows)
        elif active == "tab-stations":
            stations = await self.box(wifi.stations)
            rows = []
            for s in stations:
                host = s.get("host") or {}
                ap_info = s.get("_fbx_ap") or {}
                rate = f"{fmt.human_rate(s.get('rx_rate'))}/{fmt.human_rate(s.get('tx_rate'))}"
                rows.append(
                    (
                        str(s.get("hostname") or host.get("primary_name") or ""),
                        str(s.get("mac") or ""),
                        str(ap_info.get("name") or ap_info.get("id") or ""),
                        str(ap_info.get("band") or ""),
                        f"{s.get('signal')} dBm" if s.get("signal") is not None else "",
                        rate,
                        fmt.duration(s.get("conn_duration")),
                    )
                )
            refill(self.query_one("#stations", DataTable), rows)
        elif active == "tab-filter":
            filters = await self.box(wifi.mac_filters)
            self._filter_by_id = {str(f.get("id")): f for f in filters}
            refill(
                self.query_one("#filters", DataTable),
                [
                    (
                        str(f.get("mac") or ""),
                        str(f.get("type") or ""),
                        str(f.get("comment") or ""),
                    )
                    for f in filters
                ],
                list(self._filter_by_id),
            )

    # -- actions --------------------------------------------------------------

    @work
    async def action_reveal_key(self) -> None:
        try:
            networks = await self.box(wifi.bss)
        except BoxCallError:
            return
        pairs: list[tuple[str, str]] = []
        for b in networks:
            cfg = b.get("config") or {}
            ssid, key = cfg.get("ssid"), cfg.get("key")
            if key and (ssid, key) not in pairs:
                pairs.append((ssid, key))
        if not pairs:
            self.notify(_("No Wi-Fi key to show."), severity="warning")
            return
        body = "\n".join(f"{ssid}\n  {key}" for ssid, key in pairs)
        await self.app.push_screen_wait(TextModal(_("Wi-Fi passphrase"), body))

    @work
    async def action_survey(self) -> None:
        ap_id = cursor_key(self.query_one("#aps", DataTable))
        if ap_id is None:
            return
        self.notify(_("Scanning neighbors from AP {ap}…").format(ap=ap_id))
        try:
            await self.box(wifi.neighbors_scan, int(ap_id))
            neighbors = await self.box(wifi.neighbors, int(ap_id))
        except BoxCallError:
            return
        self.query_one("#neighbors-title", Static).update(
            _("What AP {ap} hears — {n} network(s)").format(ap=ap_id, n=len(neighbors))
        )
        rows = []
        for n in sorted(neighbors, key=lambda x: x.get("signal", -999), reverse=True):
            rows.append(
                (
                    Text(str(n.get("ssid") or _("(hidden)"))),
                    str(n.get("bssid") or ""),
                    str(n.get("band") or ""),
                    str(n.get("channel") or ""),
                    f"{n.get('signal')} dBm" if n.get("signal") is not None else "",
                )
            )
        refill(self.query_one("#neighbors", DataTable), rows)

    @work
    async def action_temp_disable(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                _("Temporarily disable Wi-Fi"),
                [
                    Field("minutes", _("Minutes"), default="5"),
                    Field("keep", _("Band to keep up (optional)"), placeholder="2d4g"),
                ],
                submit_label=_("Disable"),
            )
        )
        if not values or not values["minutes"]:
            return
        try:
            minutes = int(values["minutes"])
        except ValueError:
            self.notify(_("Minutes must be a number."), severity="error")
            return
        keep = values["keep"] or None
        kept = _(" (keeping {band})").format(band=keep) if keep else ""
        if not await self.confirm(
            _(
                "Disable Wi-Fi for {minutes} min{kept}? If this machine is on Wi-Fi "
                "you WILL lose it until the timer ends."
            ).format(minutes=minutes, kept=kept),
            confirm_label=_("Disable Wi-Fi"),
        ):
            return
        try:
            await self.box(wifi.temp_disable, duration=minutes * 60, keep=keep)
        except BoxCallError:
            return
        self.notify(
            _("Wi-Fi disabled for {minutes} min{kept}.").format(minutes=minutes, kept=kept),
            severity="warning",
        )
        self.run_refresh()

    @work
    async def action_toggle_wifi(self) -> None:
        enabled = bool(self._config.get("enabled"))
        if enabled and not await self.confirm(
            _("Turn Wi-Fi OFF globally? If this machine is on Wi-Fi you will lose it."),
            confirm_label=_("Turn off"),
        ):
            return
        try:
            await self.box(wifi.set_config, {"enabled": not enabled})
        except BoxCallError:
            return
        self.notify(_("Wi-Fi disabled.") if enabled else _("Wi-Fi enabled."))
        self.run_refresh()

    @work
    async def action_toggle_wps(self) -> None:
        enabled = bool(self._wps.get("enabled"))
        try:
            await self.box(wifi.set_wps, not enabled)
        except BoxCallError:
            return
        self.notify(_("WPS disabled.") if enabled else _("WPS enabled."))
        self.run_refresh()

    @work
    async def action_add_filter(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                _("New MAC filter entry"),
                [
                    Field("mac", _("MAC address"), placeholder="aa:bb:cc:dd:ee:ff"),
                    Field(
                        "type",
                        _("Type"),
                        default="blacklist",
                        placeholder="blacklist | whitelist",
                    ),
                    Field("comment", _("Comment (optional)")),
                ],
                submit_label=_("Add"),
            )
        )
        if not values or not values["mac"]:
            return
        try:
            await self.box(
                wifi.create_mac_filter,
                mac=values["mac"],
                type=values["type"] or "blacklist",
                comment=values["comment"],
            )
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_delete_filter(self) -> None:
        filter_id = cursor_key(self.query_one("#filters", DataTable))
        if filter_id is None:
            return
        entry = self._filter_by_id.get(filter_id, {})
        if not await self.confirm(
            _("Delete the {type} entry for {mac}?").format(
                type=_p("mac-filter", str(entry.get("type"))), mac=entry.get("mac")
            ),
            confirm_label=_("Delete"),
        ):
            return
        try:
            await self.box(wifi.delete_mac_filter, filter_id)
        except BoxCallError:
            return
        self.run_refresh()
