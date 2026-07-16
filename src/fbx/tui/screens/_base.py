"""The base domain screen: box I/O, confirm gates, polite polling."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen

from ..support import BoxCallError
from ..widgets import ConfirmModal


class BoxScreen(Screen):
    """A screen over the box.

    Subclasses implement `refresh_data()` (async; fetch with `self.box(...)`,
    then update widgets) and may set POLL_INTERVAL to auto-refresh. Polling
    skips while the screen is covered, re-fires the moment it becomes current
    again, and backs off after a failed call so a dead box doesn't get hit
    (or the user toasted) once a second.
    """

    POLL_INTERVAL: float | None = None
    ERROR_BACKOFF_TICKS = 5

    BINDINGS = [Binding("r", "refresh", "Refresh", show=False)]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._skip_ticks = 0

    def on_mount(self) -> None:
        self.run_refresh()
        if self.POLL_INTERVAL:
            self.set_interval(self.POLL_INTERVAL, self.run_refresh)

    def on_screen_resume(self) -> None:
        # Coming back from a covering screen (or a modal): show fresh data.
        self.run_refresh()

    def run_refresh(self) -> None:
        if self._skip_ticks > 0:
            self._skip_ticks -= 1
            return
        if self.is_current:
            self._refresh_worker()

    @work(exclusive=True, group="refresh")
    async def _refresh_worker(self) -> None:
        try:
            await self.refresh_data()
        except BoxCallError:
            self._skip_ticks = self.ERROR_BACKOFF_TICKS
        except NoMatches:
            # A refresh can outlive its screen: covered or torn down while a
            # slow fetch was in flight (e.g. app exit mid-pass). Rendering
            # into gone DOM is a no-op then — but a missing widget on the
            # live, current screen is a real bug and must stay loud.
            if self.is_attached and self.is_current:
                raise

    async def refresh_data(self) -> None:
        raise NotImplementedError

    async def box(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """One core.api call; raises BoxCallError after toasting the failure."""
        return await self.app.box(fn, *args, **kwargs)

    async def confirm(self, message: str, *, confirm_label: str = "Confirm") -> bool:
        """Gate a destructive action. Must be awaited from a @work method."""
        return await self.app.push_screen_wait(
            ConfirmModal(message, confirm_label=confirm_label)
        )

    def action_refresh(self) -> None:
        self.run_refresh()
