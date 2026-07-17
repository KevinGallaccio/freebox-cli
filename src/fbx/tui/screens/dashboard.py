"""The landing screen: box-overview tiles, navigation menu, suggestions."""

from __future__ import annotations

import time
from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ...core.api import calls, connection, downloads, lan, storage, system, vm, wifi
from .. import fmt
from ..i18n import _, _p
from ..suggestions import Suggestion, suggest
from ..support import BoxCallError
from ..widgets import LanguageModal
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
        Binding("l", "language", "Language"),
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
                yield Static(_("Go to"), classes="pane-title")
                yield OptionList(*self._menu_options(), id="dash-menu")
                yield Static("", id="dash-menu-blurb")
            with Container(id="dash-tiles-area"):
                with Grid(id="dash-tiles"):
                    for tile in _TILES:
                        yield Static("…", id=f"tile-{tile}", classes="tile")
        with Vertical(id="dash-suggestions-pane"):
            yield Static(_("Suggestions"), classes="pane-title")
            yield OptionList(id="dash-suggestions")
        yield Footer()

    @staticmethod
    def _menu_options() -> list[Option]:
        """The navigation entries: the title alone, one line each.

        Blurbs wrapped into word soup when inlined (worse in French), so
        they live in the description box under the menu instead — see
        `on_option_list_option_highlighted`.
        """
        return [Option(Text(_(d.title), style="bold"), id=d.key) for d in DOMAINS.values()]

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        # The menu's tooltip-of-sorts: the highlighted entry's blurb, in the
        # box under the menu, following the cursor.
        if event.option_list.id != "dash-menu":
            return
        domain = DOMAINS.get(event.option.id or "")
        if domain:
            self.query_one("#dash-menu-blurb", Static).update(_(domain.blurb))

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
            f"[b]{_('Connection')}[/b]\n"
            f"{dot} {fmt.safe(_p('state', state))} · {fmt.safe(conn.get('media'))}\n"
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
            f"[b]{_('System')}[/b]\n"
            f"{fmt.safe(model.get('pretty_name') or d.get('board_name'))}\n"
            + _("firmware {version}").format(version=fmt.safe(d.get("firmware_version")))
            + "\n"
            + _("up {uptime}").format(uptime=fmt.safe(d.get("uptime")))
            + hottest
        )

    def _render_slow(self) -> None:
        radios = []
        for a in self._snap.get("aps") or []:
            st, cfg = a.get("status") or {}, a.get("config") or {}
            channel = st.get("primary_channel") or cfg.get("primary_channel")
            radios.append(
                _("{name} ch {channel} · {state}").format(
                    name=fmt.safe(a.get("name")),
                    channel=channel,
                    state=fmt.safe(_p("ap-state", str(st.get("state") or ""))),
                )
            )
        self._tile("wifi").update(
            "[b]Wi-Fi[/b]\n" + ("\n".join(radios) or _("no radios"))
        )

        devices = self._snap.get("lan_devices") or []
        active = sum(1 for h in devices if h.get("active"))
        self._tile("lan").update(
            f"[b]{_('Devices')}[/b]\n" + _("{n} active on the LAN").format(n=active)
        )

        vm_lines = []
        for v in self._snap.get("vms") or []:
            dot = "[green]●[/]" if v.get("status") == "running" else "[dim]○[/]"
            vm_lines.append(
                f"{dot} {fmt.safe(v.get('name'))} — "
                f"{fmt.safe(_p('vm-status', str(v.get('status') or '')))}"
            )
        self._tile("vm").update(
            "[b]VMs[/b]\n" + ("\n".join(vm_lines) or _("none defined"))
        )

        part_lines = []
        for p in self._snap.get("partitions") or []:
            used, total = p.get("used_bytes"), p.get("total_bytes")
            if used and total:
                part_lines.append(
                    _("{label} {pct}% of {total}").format(
                        label=fmt.safe(p.get("label")),
                        pct=round(100 * used / total),
                        total=fmt.human_bytes(total),
                    )
                )
        self._tile("storage").update(
            f"[b]{_('Storage')}[/b]\n" + ("\n".join(part_lines) or _("no disks"))
        )

        tasks = self._snap.get("downloads") or []
        downloading = sum(1 for t in tasks if t.get("status") == "downloading")
        rate = sum(t.get("rx_rate") or 0 for t in tasks if t.get("status") == "downloading")
        self._tile("downloads").update(
            f"[b]{_('Downloads')}[/b]\n"
            + _("{n} task(s), {active} active").format(n=len(tasks), active=downloading)
            + f"\n↓ {fmt.human_rate(rate)}"
        )

        missed = sum(
            1 for c in self._snap.get("calls") or [] if c.get("new") and c.get("type") == "missed"
        )
        if missed:
            missed_line = "[red]" + _("{n} new missed call(s)").format(n=missed) + "[/]"
        else:
            missed_line = _("no new calls")
        self._tile("calls").update(f"[b]{_('Phone')}[/b]\n{missed_line}")

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
                [Option(_("Nothing pressing — the box looks tidy."), disabled=True)]
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
            self.notify(_("The {key} screen lands later in Phase 6.").format(key=key))

    def action_language(self) -> None:
        # Callback style, not push_screen_wait: set_language tears this very
        # screen down, which would cancel a waiting worker mid-await.
        self.app.push_screen(
            LanguageModal(), lambda code: code and self.app.set_language(code)
        )
