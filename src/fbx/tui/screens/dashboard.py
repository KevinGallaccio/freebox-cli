"""The landing screen: box-overview tiles, navigation menu, suggestions."""

from __future__ import annotations

import time
from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ...cli import fmt
from ...core.api import calls, connection, downloads, lan, storage, system, vm, wifi
from ..suggestions import Suggestion, suggest
from ..support import BoxCallError
from . import DOMAINS
from ._base import BoxScreen

_TILES = ("connection", "system", "wifi", "lan", "vm", "storage", "downloads", "calls")

# Slow-lane fetches: list endpoints and configs that feed tiles + suggestions.
_SLOW_FETCHES: tuple[tuple[str, Callable], ...] = (
    ("aps", wifi.aps),
    ("wps", wifi.wps_config),
    ("lan_devices", lan.devices),
    ("vms", vm.list_vms),
    ("partitions", storage.partitions),
    ("downloads", downloads.tasks),
    ("calls", calls.log),
)


class DashboardScreen(BoxScreen):
    """Box overview + "what next" — the app's home."""

    POLL_INTERVAL = 1.0  # fast lane: connection state/rates + system sensors
    SLOW_REFRESH_S = 10.0  # slow lane (lists, suggestions) at most this often

    # Tile columns follow the terminal width (classes drive grid-size in tcss).
    HORIZONTAL_BREAKPOINTS = [(0, "-w2"), (150, "-w3"), (190, "-w4")]

    BINDINGS = [
        Binding("escape", "app.back", "Back", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._snap: dict = {}
        # Deadline, not a tick counter: refresh workers are exclusive, so a
        # cancelled slow pass must retry on the next tick, not in N ticks.
        self._slow_due = 0.0
        self._suggestions: list[Suggestion] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="dash-body"):
            with Vertical(id="dash-menu-pane"):
                yield Static("Go to", classes="pane-title")
                yield OptionList(
                    *(Option(f"{d.title} — {d.blurb}", id=d.key) for d in DOMAINS.values()),
                    id="dash-menu",
                )
            with Container(id="dash-tiles-area"):
                with Grid(id="dash-tiles"):
                    for tile in _TILES:
                        yield Static("…", id=f"tile-{tile}", classes="tile")
        with Vertical(id="dash-suggestions-pane"):
            yield Static("Suggestions", classes="pane-title")
            yield OptionList(id="dash-suggestions")
        yield Footer()

    # -- data ---------------------------------------------------------------

    async def refresh_data(self) -> None:
        ok = 0
        for key, fn in (("connection", connection.status), ("system", system.info)):
            try:
                self._snap[key] = await self.box(fn)
                ok += 1
            except BoxCallError:
                pass
        if not ok:
            # Box unreachable: trigger the base backoff instead of a 1 Hz hammer.
            raise BoxCallError("box unreachable")
        self._render_fast()

        if time.monotonic() >= self._slow_due:
            for key, fn in _SLOW_FETCHES:
                try:
                    self._snap[key] = await self.box(fn)
                except BoxCallError:
                    pass  # partial snapshot is fine; tile keeps last data
            self._render_slow()
            self._update_suggestions()
            # Only after a completed pass — a cancelled one retries next tick.
            self._slow_due = time.monotonic() + self.SLOW_REFRESH_S

    # -- rendering ----------------------------------------------------------

    def _tile(self, name: str) -> Static:
        return self.query_one(f"#tile-{name}", Static)

    def _render_fast(self) -> None:
        conn = self._snap.get("connection") or {}
        state = str(conn.get("state") or "?")
        dot = "[green]●[/]" if state == "up" else "[red]●[/]"
        self._tile("connection").update(
            "[b]Connection[/b]\n"
            f"{dot} {fmt.safe(state)} · {fmt.safe(conn.get('media'))}\n"
            f"↓ {fmt.human_rate(conn.get('rate_down'))}   ↑ {fmt.human_rate(conn.get('rate_up'))}\n"
            f"IPv4 {fmt.safe(conn.get('ipv4'))}"
        )

        d = self._snap.get("system") or {}
        model = d.get("model_info") or {}
        temps = [
            s.get("value")
            for s in d.get("sensors") or []
            if isinstance(s.get("value"), (int, float))
        ]
        hottest = f" · {max(temps)}°C max" if temps else ""
        self._tile("system").update(
            "[b]System[/b]\n"
            f"{fmt.safe(model.get('pretty_name') or d.get('board_name'))}\n"
            f"firmware {fmt.safe(d.get('firmware_version'))}\n"
            f"up {fmt.safe(d.get('uptime'))}{hottest}"
        )

    def _render_slow(self) -> None:
        radios = []
        for a in self._snap.get("aps") or []:
            st, cfg = a.get("status") or {}, a.get("config") or {}
            channel = st.get("primary_channel") or cfg.get("primary_channel")
            radios.append(
                f"{fmt.safe(a.get('name'))} ch {channel} · {fmt.safe(st.get('state'))}"
            )
        self._tile("wifi").update("[b]Wi-Fi[/b]\n" + ("\n".join(radios) or "no radios"))

        devices = self._snap.get("lan_devices") or []
        active = sum(1 for h in devices if h.get("active"))
        self._tile("lan").update(f"[b]Devices[/b]\n{active} active on the LAN")

        vm_lines = []
        for v in self._snap.get("vms") or []:
            dot = "[green]●[/]" if v.get("status") == "running" else "[dim]○[/]"
            vm_lines.append(f"{dot} {fmt.safe(v.get('name'))} — {fmt.safe(v.get('status'))}")
        self._tile("vm").update("[b]VMs[/b]\n" + ("\n".join(vm_lines) or "none defined"))

        part_lines = []
        for p in self._snap.get("partitions") or []:
            used, total = p.get("used_bytes"), p.get("total_bytes")
            if used and total:
                part_lines.append(
                    f"{fmt.safe(p.get('label'))} {round(100 * used / total)}% of "
                    f"{fmt.human_bytes(total)}"
                )
        self._tile("storage").update("[b]Storage[/b]\n" + ("\n".join(part_lines) or "no disks"))

        tasks = self._snap.get("downloads") or []
        downloading = sum(1 for t in tasks if t.get("status") == "downloading")
        rate = sum(t.get("rx_rate") or 0 for t in tasks if t.get("status") == "downloading")
        self._tile("downloads").update(
            "[b]Downloads[/b]\n"
            f"{len(tasks)} task(s), {downloading} active\n↓ {fmt.human_rate(rate)}"
        )

        missed = sum(
            1 for c in self._snap.get("calls") or [] if c.get("new") and c.get("type") == "missed"
        )
        missed_line = f"[red]{missed} new missed call(s)[/]" if missed else "no new calls"
        self._tile("calls").update(f"[b]Phone[/b]\n{missed_line}")

    def _update_suggestions(self) -> None:
        self._suggestions = suggest(self._snap)
        option_list = self.query_one("#dash-suggestions", OptionList)
        option_list.clear_options()
        if self._suggestions:
            option_list.add_options(
                Option(f"→ {fmt.safe(s.text)}", id=str(i)) for i, s in enumerate(self._suggestions)
            )
        else:
            option_list.add_options(
                [Option("Nothing pressing — the box looks tidy.", disabled=True)]
            )

    # -- navigation ---------------------------------------------------------

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "dash-menu":
            key = event.option.id or ""
        else:
            if not self._suggestions:
                return
            key = self._suggestions[event.option_index].domain
        if key in DOMAINS:
            self.app.open_domain(key)
        else:
            self.notify(f"The {key} screen lands later in Phase 6.")
