"""Storage: physical disks and partition usage."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

from ...core.api import storage
from .. import fmt
from ..i18n import _, _p
from ..widgets import refill
from ._base import BoxScreen


class StorageScreen(BoxScreen):
    POLL_INTERVAL = 10.0

    BINDINGS = [Binding("escape", "app.back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(_("Disks"), classes="pane-title")
            yield DataTable(id="disks", cursor_type="row")
            yield Static(_("Partitions"), classes="pane-title")
            yield DataTable(id="partitions", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#disks", DataTable).add_columns(
            "Id", _("Type"), _("Model"), _("Size"), _("Temp"), _("State")
        )
        self.query_one("#partitions", DataTable).add_columns(
            "Id", _("Label"), _("Used"), _("Total"), _("Use%"), _("Free")
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        disks = await self.box(storage.disks)
        refill(
            self.query_one("#disks", DataTable),
            [
                (
                    str(d.get("id", "")),
                    str(d.get("type") or ""),
                    str(d.get("model") or ""),
                    fmt.human_bytes(d.get("total_bytes")),
                    f"{d.get('temp')}°C" if d.get("temp") is not None else "",
                    _p("disk-state", str(d.get("state") or "")),
                )
                for d in disks
            ],
        )
        partitions = await self.box(storage.partitions)
        rows = []
        for p in partitions:
            used, total = p.get("used_bytes"), p.get("total_bytes")
            pct = f"{round(100 * used / total)}%" if used and total else ""
            rows.append(
                (
                    str(p.get("id", "")),
                    str(p.get("label") or ""),
                    fmt.human_bytes(used),
                    fmt.human_bytes(total),
                    pct,
                    fmt.human_bytes(p.get("free_bytes")),
                )
            )
        refill(self.query_one("#partitions", DataTable), rows)
