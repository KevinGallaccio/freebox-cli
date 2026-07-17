"""Downloads: the box's download manager, live."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from ...core.api import downloads
from .. import fmt
from ..i18n import _, _p
from ..support import BoxCallError
from ..widgets import Field, FormModal, cursor_key, refill
from ._base import BoxScreen

_STATUS_STYLE = {
    "downloading": "green",
    "done": "blue",
    "error": "red",
    "stopped": "yellow",
    "seeding": "cyan",
}


class DownloadsScreen(BoxScreen):
    POLL_INTERVAL = 2.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("a", "add", "Add URL/magnet"),
        Binding("space", "pause_resume", "Pause/resume"),
        Binding("d", "remove", "Remove task"),
        Binding("E", "erase", "Erase + files"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="tasks", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tasks", DataTable).add_columns(
            _("Name"), _("Status"), "%", _("Size"), _("Rate"), "ETA"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        tasks = await self.box(downloads.tasks)
        self._by_id = {str(t.get("id")): t for t in tasks}
        rows = []
        for t in tasks:
            status = str(t.get("status") or "")
            rx_pct = t.get("rx_pct")
            rows.append(
                (
                    str(t.get("name") or ""),
                    Text(_p("dl-status", status), style=_STATUS_STYLE.get(status, "")),
                    f"{rx_pct / 100:.0f}%" if rx_pct is not None else "",
                    fmt.human_bytes(t.get("size")),
                    fmt.human_rate(t.get("rx_rate")),
                    fmt.duration(t.get("eta")) if t.get("eta") else "",
                )
            )
        refill(self.query_one("#tasks", DataTable), rows, list(self._by_id))

    @work
    async def action_add(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                _("Queue a download"),
                [
                    Field("url", _("URL or magnet link")),
                    Field("dir", _("Download directory (optional)"), placeholder="/Freebox/…"),
                ],
                submit_label=_("Download"),
            )
        )
        if not values or not values["url"]:
            return
        try:
            await self.box(
                downloads.add_url, url=values["url"], download_dir=values["dir"] or None
            )
        except BoxCallError:
            return
        self.notify(_("Download queued."))
        self.run_refresh()

    @work
    async def action_pause_resume(self) -> None:
        task_id = cursor_key(self.query_one("#tasks", DataTable))
        if task_id is None:
            return
        task = self._by_id.get(task_id, {})
        # Same bodies as `fbx downloads pause` / `resume`.
        new_status = "stopped" if task.get("status") == "downloading" else "downloading"
        try:
            await self.box(downloads.update_task, int(task_id), {"status": new_status})
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_remove(self) -> None:
        task_id = cursor_key(self.query_one("#tasks", DataTable))
        if task_id is None:
            return
        name = self._by_id.get(task_id, {}).get("name", _("this task"))
        if not await self.confirm(
            _("Remove {name!r} from the list? Downloaded files are kept.").format(name=name),
            confirm_label=_("Remove"),
        ):
            return
        try:
            await self.box(downloads.delete_task, int(task_id))
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_erase(self) -> None:
        task_id = cursor_key(self.query_one("#tasks", DataTable))
        if task_id is None:
            return
        name = self._by_id.get(task_id, {}).get("name", _("this task"))
        if not await self.confirm(
            _("Erase {name!r} AND delete its downloaded files? This cannot be undone.").format(
                name=name
            ),
            confirm_label=_("Erase files"),
        ):
            return
        try:
            await self.box(downloads.erase_task, int(task_id))
        except BoxCallError:
            return
        self.notify(_("Task and files erased."), severity="warning")
        self.run_refresh()
