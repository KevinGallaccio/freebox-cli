"""Top: the live view — throughput sparklines, sensors, Wi-Fi clients.

The box has no push channel for rates or sensors (Phase 0 finding: the web
UI itself polls at ~1 Hz), so this screen does the same.
"""

from __future__ import annotations

from collections import deque

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Sparkline, Static

from ...core.api import connection, system, wifi
from .. import fmt
from ..i18n import _
from ..support import BoxCallError
from ..widgets import refill
from ._base import BoxScreen

_WINDOW = 60  # seconds of rate history


class TopScreen(BoxScreen):
    POLL_INTERVAL = 1.0

    BINDINGS = [Binding("escape", "app.back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._down: deque[float] = deque([0.0] * _WINDOW, maxlen=_WINDOW)
        self._up: deque[float] = deque([0.0] * _WINDOW, maxlen=_WINDOW)
        self._station_tick = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="top-rates"):
            with Vertical(classes="top-rate-pane"):
                yield Static(_("↓ down"), classes="pane-title")
                yield Static("…", id="top-down-label")
                yield Sparkline(list(self._down), id="top-down")
            with Vertical(classes="top-rate-pane"):
                yield Static(_("↑ up"), classes="pane-title")
                yield Static("…", id="top-up-label")
                yield Sparkline(list(self._up), id="top-up")
        yield Static("…", id="top-system", classes="panel")
        yield Static(_("Wi-Fi clients"), classes="pane-title")
        yield DataTable(id="top-stations", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#top-stations", DataTable).add_columns(
            _("Name"), _("Band"), _("Signal"), _("Rate ↓/↑")
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        status = await self.box(connection.status)
        down = float(status.get("rate_down") or 0)
        up = float(status.get("rate_up") or 0)
        self._down.append(down)
        self._up.append(up)
        self.query_one("#top-down", Sparkline).data = list(self._down)
        self.query_one("#top-up", Sparkline).data = list(self._up)
        peak = _("(peak {rate})")
        self.query_one("#top-down-label", Static).update(
            f"[b]{fmt.human_rate(down)}[/b]  "
            + peak.format(rate=fmt.human_rate(max(self._down)))
        )
        self.query_one("#top-up-label", Static).update(
            f"[b]{fmt.human_rate(up)}[/b]  "
            + peak.format(rate=fmt.human_rate(max(self._up)))
        )

        info = await self.box(system.info)
        temps = "   ".join(
            f"{s.get('name')} {s.get('value')}°C" for s in info.get("sensors") or []
        )
        fans = "   ".join(
            f"{f.get('name')} {f.get('value')} rpm" for f in info.get("fans") or []
        )
        self.query_one("#top-system", Static).update(
            f"{fmt.safe(temps)}\n{fmt.safe(fans)}\n"
            + _("up {uptime}").format(uptime=fmt.safe(info.get("uptime")))
        )

        # Stations move slowly; refresh them every 5th tick.
        self._station_tick += 1
        if self._station_tick % 5 == 1:
            try:
                stations = await self.box(wifi.stations)
            except BoxCallError:
                return
            stations.sort(key=lambda s: s.get("signal") or -999, reverse=True)
            rows = []
            for s in stations:
                host = s.get("host") or {}
                ap_info = s.get("_fbx_ap") or {}
                rows.append(
                    (
                        str(s.get("hostname") or host.get("primary_name") or s.get("mac") or ""),
                        str(ap_info.get("band") or ""),
                        f"{s.get('signal')} dBm" if s.get("signal") is not None else "",
                        f"{fmt.human_rate(s.get('rx_rate'))}/{fmt.human_rate(s.get('tx_rate'))}",
                    )
                )
            refill(self.query_one("#top-stations", DataTable), rows)
