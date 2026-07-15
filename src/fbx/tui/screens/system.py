"""System: identity, sensors, and the power controls."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from ...cli import fmt
from ...core.api import system
from ..support import BoxCallError
from ._base import BoxScreen


class SystemScreen(BoxScreen):
    POLL_INTERVAL = 2.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("b", "reboot", "Reboot"),
        Binding("x", "poweroff", "Power off"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("…", id="system-info", classes="panel")
        yield Footer()

    async def refresh_data(self) -> None:
        info = await self.box(system.info)
        self.query_one("#system-info", Static).update(_render(info))

    @work
    async def action_reboot(self) -> None:
        if not await self.confirm(
            "Reboot the Freebox?\n\nThe whole network (including this app's "
            "connection) drops for a couple of minutes.",
            confirm_label="Reboot",
        ):
            return
        try:
            await self.box(system.reboot)
        except BoxCallError:
            return
        self.notify("Reboot requested — the box is going down.", severity="warning")

    @work
    async def action_poweroff(self) -> None:
        if not await self.confirm(
            "Power off the Freebox?\n\nIt stays down until someone presses the "
            "physical button — this app cannot turn it back on.",
            confirm_label="Power off",
        ):
            return
        try:
            await self.box(system.shutdown)
        except BoxCallError:
            return
        self.notify("Shutdown requested.", severity="warning")


def _render(d: dict) -> str:
    model = d.get("model_info") or {}
    lines = [
        f"[b]{fmt.safe(model.get('pretty_name') or d.get('board_name') or 'Freebox')}[/b]",
        f"firmware {fmt.safe(d.get('firmware_version'))} · MAC {fmt.safe(d.get('mac'))}",
        f"up {fmt.safe(d.get('uptime'))}",
    ]
    sensors = d.get("sensors") or []
    if sensors:
        lines.append(
            "temp   " + "   ".join(f"{fmt.safe(s.get('name'))} {s.get('value')}°C" for s in sensors)
        )
    fans = d.get("fans") or []
    if fans:
        lines.append(
            "fans   " + "   ".join(f"{fmt.safe(f.get('name'))} {f.get('value')} rpm" for f in fans)
        )
    return "\n".join(lines)
