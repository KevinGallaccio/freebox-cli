"""DHCP: server config, active leases, static reservations."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ...core.api import dhcp
from .. import fmt
from ..i18n import _
from ..support import BoxCallError
from ..widgets import Field, FormModal, cursor_key, refill
from ._base import BoxScreen


class DhcpScreen(BoxScreen):
    POLL_INTERVAL = 10.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("a", "add_static", "Reserve IP"),
        Binding("e", "edit_static", "Edit"),
        Binding("d", "delete_static", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._static_by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("…", id="dhcp-config", classes="panel")
        with TabbedContent():
            with TabPane(_("Static reservations"), id="tab-static"):
                yield DataTable(id="static-leases", cursor_type="row")
            with TabPane(_("Active leases"), id="tab-dynamic"):
                yield DataTable(id="dynamic-leases", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#static-leases", DataTable).add_columns(
            _("Hostname"), "IP", "MAC", _("Comment")
        )
        self.query_one("#dynamic-leases", DataTable).add_columns(
            _("Hostname"), "IP", "MAC", _("Assigned"), _("Remaining"), _("Static")
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        config = await self.box(dhcp.config)
        dns = ", ".join(config.get("dns") or [])
        self.query_one("#dhcp-config", Static).update(
            f"DHCP {fmt.onoff(config.get('enabled'))} · "
            f"{_('range')} {fmt.safe(config.get('ip_range_start'))} – "
            f"{fmt.safe(config.get('ip_range_end'))} · DNS {fmt.safe(dns)}"
        )

        static = await self.box(dhcp.static_leases)
        self._static_by_id = {str(lease.get("id")): lease for lease in static}
        refill(
            self.query_one("#static-leases", DataTable),
            [
                (
                    str(lease.get("hostname") or ""),
                    str(lease.get("ip") or ""),
                    str(lease.get("mac") or ""),
                    str(lease.get("comment") or ""),
                )
                for lease in static
            ],
            list(self._static_by_id),
        )

        dynamic = await self.box(dhcp.dynamic_leases)
        refill(
            self.query_one("#dynamic-leases", DataTable),
            [
                (
                    str(lease.get("hostname") or ""),
                    str(lease.get("ip") or ""),
                    str(lease.get("mac") or ""),
                    fmt.epoch(lease.get("assign_time")),
                    fmt.duration(lease.get("lease_remaining")),
                    _("yes") if lease.get("is_static") else "",
                )
                for lease in dynamic
            ],
        )

    @work
    async def action_add_static(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                _("Reserve an IP"),
                [
                    Field("mac", _("MAC address"), placeholder="aa:bb:cc:dd:ee:ff"),
                    Field("ip", _("IPv4 address"), placeholder="192.168.1.x"),
                    Field("comment", _("Comment (optional)")),
                ],
                submit_label=_("Reserve"),
            )
        )
        if not values or not values["mac"] or not values["ip"]:
            return
        try:
            await self.box(
                dhcp.create_static_lease,
                mac=values["mac"],
                ip=values["ip"],
                comment=values["comment"] or None,
            )
        except BoxCallError:
            return
        self.notify(_("Reserved {ip} for {mac}.").format(ip=values["ip"], mac=values["mac"]))
        self.run_refresh()

    @work
    async def action_edit_static(self) -> None:
        lease_id = cursor_key(self.query_one("#static-leases", DataTable))
        if lease_id is None:
            return
        current = self._static_by_id.get(lease_id, {})
        values = await self.app.push_screen_wait(
            FormModal(
                _("Edit reservation"),
                [
                    Field("ip", _("IPv4 address"), default=str(current.get("ip") or "")),
                    Field("comment", _("Comment"), default=str(current.get("comment") or "")),
                ],
            )
        )
        if not values or not values["ip"]:
            return
        try:
            await self.box(
                dhcp.update_static_lease,
                lease_id,
                {"ip": values["ip"], "comment": values["comment"]},
            )
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_delete_static(self) -> None:
        lease_id = cursor_key(self.query_one("#static-leases", DataTable))
        if lease_id is None:
            return
        lease = self._static_by_id.get(lease_id, {})
        if not await self.confirm(
            _("Delete the reservation of {ip} for {mac}?").format(
                ip=lease.get("ip"), mac=lease.get("mac")
            ),
            confirm_label=_("Delete"),
        ):
            return
        try:
            await self.box(dhcp.delete_static_lease, lease_id)
        except BoxCallError:
            return
        self.run_refresh()
