"""FbxApp — open once, navigate, act, quit."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from textual.app import App
from textual.binding import Binding

from ..core.errors import FbxError
from ..core.runtime import ClientRuntime
from .prefs import Prefs
from .support import BoxCallError, human_error


class FbxApp(App):
    """The application shell: one shared box connection, a screen stack."""

    TITLE = "fbx"
    CSS_PATH = "app.tcss"

    # Identical error toasts repeat at most once per this many seconds — a
    # 1 Hz poll against an unreachable box must not stack notifications.
    ERROR_DEDUPE_S = 30.0

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "back", "Back", show=False),
    ]

    def __init__(
        self,
        *,
        profile: str = "default",
        host: str | None = None,
        splash: bool = True,
    ) -> None:
        super().__init__()
        self.runtime = ClientRuntime(profile=profile, host=host)
        self._last_error: tuple[str, float] | None = None
        self._show_splash = splash
        self.prefs = Prefs.load()
        from .brand import FREEBOX_DARK, FREEBOX_LIGHT

        self.register_theme(FREEBOX_LIGHT)
        self.register_theme(FREEBOX_DARK)
        # Before the first frame, so there's no flash of the default theme.
        # A stale saved name would raise InvalidThemeError, hence the guard;
        # with nothing (valid) saved, the house theme is the default.
        saved_theme = self.prefs.get("app.theme")
        self.theme = (
            saved_theme if saved_theme in self.available_themes else "freebox-light"
        )

    def on_mount(self) -> None:
        from .screens.dashboard import DashboardScreen
        from .screens.splash import SplashScreen

        self.theme_changed_signal.subscribe(self, self._remember_theme)
        self.push_screen(DashboardScreen())
        if self._show_splash:
            # Over the dashboard, which is already fetching underneath — by
            # the time the splash pops, the first tiles have real data.
            self.push_screen(SplashScreen())

    def _remember_theme(self, theme: Any) -> None:
        self.prefs.set("app.theme", theme.name)

    def on_unmount(self) -> None:
        self.runtime.close()

    async def box(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run one core.api call off-thread (the runtime lock serializes).

        On failure: toast the human message once, then raise `BoxCallError`
        so the caller can keep its last good data without re-reporting.
        """
        try:
            return await asyncio.to_thread(self.runtime.call, fn, *args, **kwargs)
        except FbxError as exc:
            self._toast_error(human_error(exc))
            raise BoxCallError(str(exc)) from exc

    def _toast_error(self, message: str) -> None:
        now = time.monotonic()
        if (
            self._last_error
            and self._last_error[0] == message
            and now - self._last_error[1] < self.ERROR_DEDUPE_S
        ):
            return
        self._last_error = (message, now)
        self.notify(message, title="Box error", severity="error", timeout=8)

    def open_domain(self, key: str) -> None:
        from .screens import DOMAINS

        self.push_screen(DOMAINS[key].factory())

    def action_back(self) -> None:
        # Stack bottom is textual's default screen + the dashboard; never pop those.
        if len(self.screen_stack) > 2:
            self.pop_screen()
