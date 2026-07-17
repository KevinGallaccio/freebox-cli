"""Splash: a one-second brand moment on every launch — the « f », our way.

Deliberately NOT a loading screen: no spinner, no progress. The dashboard is
already mounted (and fetching) underneath, so the splash costs nothing — it
just covers the first placeholders, and any key skips it.
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from ... import __version__
from ..brand import FREE_RED, logo
from ..i18n import _


class SplashScreen(Screen):
    DURATION = 1.0  # classvar so tests can shrink the beat

    def compose(self) -> ComposeResult:
        title = Text.assemble(
            ("fbx", f"bold {FREE_RED}"), (" · ", "dim"), (f"v{__version__}", "bold")
        )
        with Vertical(id="splash-body"):
            yield Static(logo(), id="splash-art")
            yield Static(title, id="splash-title")
            yield Static(_("press any key"), id="splash-hint")

    def on_mount(self) -> None:
        self.set_timer(self.DURATION, self._done)

    def on_key(self, event: events.Key) -> None:
        # Swallow the key: `q` here skips the splash, it must not quit.
        # (textual's built-in priority ctrl+q still quits — fine.)
        event.stop()
        self._done()

    def _done(self) -> None:
        # The timer and a keypress can race; only the top screen pops.
        if self.app.screen is self:
            self.app.pop_screen()
