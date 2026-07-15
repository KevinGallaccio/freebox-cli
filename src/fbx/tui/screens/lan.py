"""LAN: who's on the network — rename hosts, wake them, browse inactives."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from ...cli import fmt
from ...core.api import lan
from ..support import BoxCallError
from ..widgets import Field, FormModal, cursor_key, refill
from ._base import BoxScreen


def _ipv4(host: dict) -> str:
    for c in host.get("l3connectivities") or []:
        if c.get("af") == "ipv4" and c.get("active") and c.get("addr"):
            return str(c["addr"])
    return ""


class LanScreen(BoxScreen):
    POLL_INTERVAL = 5.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("a", "toggle_all", "All/active"),
        Binding("n", "rename", "Rename"),
        Binding("w", "wake", "Wake (WoL)"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._show_all = False
        self._by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="hosts", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._show_all = self.app.prefs.get("screens.lan.show") == "all"
        self.query_one("#hosts", DataTable).add_columns(
            "", "Name", "IPv4", "MAC", "Type", "Last seen"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        hosts = await self.box(lan.devices)
        if not self._show_all:
            hosts = [h for h in hosts if h.get("active")]
        hosts.sort(key=lambda h: (not h.get("active"), str(h.get("primary_name") or "").lower()))
        self._by_id = {str(h.get("id")): h for h in hosts}
        rows = []
        for h in hosts:
            dot = Text("●", style="green") if h.get("active") else Text("○", style="dim")
            rows.append(
                (
                    dot,
                    str(h.get("primary_name") or h.get("default_name") or "?"),
                    _ipv4(h),
                    str((h.get("l2ident") or {}).get("id") or ""),
                    str(h.get("host_type") or ""),
                    fmt.epoch(h.get("last_activity")),
                )
            )
        refill(self.query_one("#hosts", DataTable), rows, list(self._by_id))
        self.sub_title = f"{len(hosts)} host(s) — {'all known' if self._show_all else 'active'}"

    def action_toggle_all(self) -> None:
        self._show_all = not self._show_all
        self.app.prefs.set("screens.lan.show", "all" if self._show_all else "active")
        self.run_refresh()

    @work
    async def action_rename(self) -> None:
        host_id = cursor_key(self.query_one("#hosts", DataTable))
        if host_id is None:
            return
        current = self._by_id.get(host_id, {})
        values = await self.app.push_screen_wait(
            FormModal(
                "Rename device",
                [Field("name", "Name", default=str(current.get("primary_name") or ""))],
                submit_label="Rename",
            )
        )
        if not values or not values["name"]:
            return
        try:
            await self.box(lan.update_host, host_id, {"primary_name": values["name"]})
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_wake(self) -> None:
        host_id = cursor_key(self.query_one("#hosts", DataTable))
        if host_id is None:
            return
        host = self._by_id.get(host_id, {})
        mac = (host.get("l2ident") or {}).get("id")
        if not mac:
            self.notify("No MAC for this host.", severity="warning")
            return
        try:
            await self.box(lan.wake, mac)
        except BoxCallError:
            return
        self.notify(f"Wake-on-LAN sent to {mac}.")
