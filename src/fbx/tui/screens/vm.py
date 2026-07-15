"""Virtual machines: lifecycle, resources, serial console, one-shot exec."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from ...cli import fmt
from ...core import vmconsole
from ...core.api import vm
from ...core.errors import FbxError
from ..support import BoxCallError, human_error
from ..widgets import Field, FormModal, TextModal, cursor_key, refill
from ._base import BoxScreen

_STATUS_STYLE = {"running": "green", "stopped": "dim"}


class VmScreen(BoxScreen):
    POLL_INTERVAL = 3.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("s", "start", "Start"),
        Binding("S", "shutdown", "Shutdown"),
        Binding("K", "stop", "Hard stop"),
        Binding("D", "delete", "Delete"),
        Binding("c", "console", "Console"),
        Binding("x", "exec", "Exec…"),
        Binding("u", "userdata", "cloud-init"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("…", id="vm-info", classes="panel")
        yield DataTable(id="vms", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#vms", DataTable).add_columns(
            "Id", "Name", "Status", "vCPUs", "Memory", "Disk"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        info = await self.box(vm.info)
        total_mem, used_mem = info.get("total_memory"), info.get("used_memory")
        self.query_one("#vm-info", Static).update(
            f"Hypervisor: {info.get('used_cpus', '?')}/{info.get('total_cpus', '?')} vCPUs · "
            f"{fmt.human_bytes(used_mem)} / {fmt.human_bytes(total_mem)} memory in use"
        )

        # One sorted list feeds BOTH the rows and the key list: refill() zips
        # them positionally, so any ordering divergence would pair a row with
        # a different VM's id — and route actions at the wrong VM.
        vms = sorted(await self.box(vm.list_vms), key=lambda v: v.get("id", 0))
        self._by_id = {str(v.get("id")): v for v in vms}
        rows = []
        for v in vms:
            status = str(v.get("status") or "")
            rows.append(
                (
                    str(v.get("id", "")),
                    str(v.get("name") or ""),
                    Text(status, style=_STATUS_STYLE.get(status, "yellow")),
                    str(v.get("vcpus", "")),
                    fmt.human_bytes((v.get("memory") or 0) * 1024 * 1024),
                    str(v.get("disk_path") or ""),
                )
            )
        refill(self.query_one("#vms", DataTable), rows, list(self._by_id))

    def _selected(self) -> tuple[int, dict] | None:
        vm_id = cursor_key(self.query_one("#vms", DataTable))
        if vm_id is None:
            return None
        return int(vm_id), self._by_id.get(vm_id, {})

    # -- lifecycle ------------------------------------------------------------

    @work
    async def action_start(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        try:
            await self.box(vm.start, vm_id)
        except BoxCallError:
            return
        self.notify(f"Starting {item.get('name') or vm_id}…")
        self.run_refresh()

    @work
    async def action_shutdown(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        try:
            await self.box(vm.powerbutton, vm_id)
        except BoxCallError:
            return
        self.notify(f"ACPI shutdown sent to {item.get('name') or vm_id}.")
        self.run_refresh()

    @work
    async def action_stop(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        name = item.get("name") or vm_id
        if not await self.confirm(
            f"Hard-stop VM {name!r}? Like pulling the power cord — the guest "
            "gets no chance to sync its disks.",
            confirm_label="Hard stop",
        ):
            return
        try:
            await self.box(vm.stop, vm_id)
        except BoxCallError:
            return
        self.notify(f"{name} powered off.", severity="warning")
        self.run_refresh()

    @work
    async def action_delete(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        name = item.get("name") or vm_id
        if not await self.confirm(
            f"Delete the VM definition {name!r}? Its disk file is kept on the "
            "box, but the VM itself is gone.",
            confirm_label="Delete VM",
        ):
            return
        try:
            await self.box(vm.delete, vm_id)
        except BoxCallError:
            return
        self.notify(f"VM {name} deleted (disk kept).", severity="warning")
        self.run_refresh()

    # -- console / exec / userdata ---------------------------------------------

    @work
    async def action_console(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        if item.get("status") != "running":
            self.notify("The VM must be running to attach its console.", severity="warning")
            return
        # Release the terminal to the raw byte pump; the pump runs in a
        # thread so its own event loop (asyncio.run) doesn't collide with
        # the app's. Ctrl-] detaches, then the app resumes.
        with self.app.suspend():
            try:
                await asyncio.to_thread(
                    self.app.runtime.call, vmconsole.console_runner, vm_id
                )
            except FbxError as exc:
                self.notify(human_error(exc), severity="error", timeout=8)
        self.run_refresh()

    @work
    async def action_exec(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        if item.get("status") != "running":
            self.notify("The VM must be running to run a command.", severity="warning")
            return
        values = await self.app.push_screen_wait(
            FormModal(
                f"Run on {item.get('name') or vm_id}'s serial console",
                [Field("command", "Command", placeholder="uptime")],
                submit_label="Run",
            )
        )
        if not values or not values["command"]:
            return
        self.notify("Running (collects until the tty goes quiet)…")
        try:
            output = await asyncio.to_thread(
                self.app.runtime.call, vmconsole.run_command, vm_id, values["command"]
            )
        except FbxError as exc:
            self.notify(human_error(exc), severity="error", timeout=8)
            return
        await self.app.push_screen_wait(
            TextModal(f"{item.get('name') or vm_id} — {values['command']}", output or "(no output)")
        )

    @work
    async def action_userdata(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        try:
            data = await self.box(vm.get, vm_id)
        except BoxCallError:
            return
        body = data.get("cloudinit_userdata") or "(no cloud-init userdata)"
        await self.app.push_screen_wait(
            TextModal(f"{item.get('name') or vm_id} — cloud-init userdata", body)
        )
