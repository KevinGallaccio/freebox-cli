"""Virtual machines: lifecycle, resources, serial console, one-shot exec."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Static

from ...cli import fmt
from ...core import cloudinit, vmconsole
from ...core.api import fs, vm
from ...core.errors import FbxError
from ...core.fspath import decode_lenient
from .. import oslaunch
from ..support import BoxCallError, human_error
from ..widgets import Field, FormModal, TextModal, cursor_key, refill
from ._base import BoxScreen

_STATUS_STYLE = {"running": "green", "stopped": "dim"}

_PREFLIGHT = (
    "This attaches your terminal to the VM's serial port (its tty) — not a "
    "fresh shell. You may land on a guest login prompt, or on whatever the "
    "console last printed; a sleeping getty may need an Enter to wake up."
    f"\n\nTo come back to fbx, press {vmconsole.DETACH_HINT}"
)


class ConsolePreflightModal(ModalScreen["str | None"]):
    """What the serial console is and how to leave it, asked BEFORE the
    terminal is handed over. Dismisses with "attach", "terminal", or None.

    Guest credentials found in cloud-init are shown masked; `r` reveals them
    in place. They are never typed into the guest tty.
    """

    BINDINGS = [
        Binding("a", "attach", "Attach here"),
        Binding("t", "terminal", "New terminal"),
        Binding("r", "reveal", "Reveal credentials", show=False),
        Binding("p", "copy_password", "Copy password", show=False),
        Binding("u", "copy_login", "Copy login", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        name: str,
        credentials: list[tuple[str, str]],
        *,
        offer_terminal: bool,
    ) -> None:
        super().__init__()
        self._name = name
        self._credentials = credentials
        self._offer_terminal = offer_terminal
        self._revealed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="preflight-box"):
            yield Static(f"Serial console — {self._name}", id="preflight-title")
            yield Static(_PREFLIGHT, id="preflight-text")
            if self._credentials:
                yield Static(self._cred_text(), id="preflight-creds")
            with Horizontal(id="preflight-buttons"):
                yield Button("Attach here (a)", variant="primary", id="attach")
                if self._offer_terminal:
                    yield Button("New terminal window (t)", id="terminal")
                yield Button("Cancel (esc)", id="cancel")

    def _cred_text(self) -> Text:
        text = Text("Guest credentials (cloud-init): ", style="dim")
        for i, (label, secret) in enumerate(self._credentials):
            if i:
                text.append("  ")
            text.append(f"{label}: ", style="bold dim")
            if self._revealed:
                text.append(secret)
            else:
                # Fixed-width mask: the length is a secret too.
                text.append("••••••••", style="dim")
        text.append(
            "  —  r reveals · p copies the password · u the login",
            style="dim italic",
        )
        return text

    def action_reveal(self) -> None:
        if not self._credentials:
            return
        self._revealed = True
        self.query_one("#preflight-creds", Static).update(self._cred_text())

    def action_copy_password(self) -> None:
        if not self._credentials:
            return
        self.app.copy_to_clipboard(self._credentials[0][1])
        self.notify("Password copied to the clipboard.")

    def action_copy_login(self) -> None:
        if not self._credentials:
            return
        login = self._credentials[0][0]
        if login == "password":  # the generic label: no username to copy
            self.notify("cloud-init names no login for this one.", severity="warning")
            return
        self.app.copy_to_clipboard(login)
        self.notify(f"Login {login!r} copied to the clipboard.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice = event.button.id
        self.dismiss(choice if choice in ("attach", "terminal") else None)

    def action_attach(self) -> None:
        self.dismiss("attach")

    def action_terminal(self) -> None:
        if self._offer_terminal:
            self.dismiss("terminal")

    def action_cancel(self) -> None:
        self.dismiss(None)


class VmScreen(BoxScreen):
    POLL_INTERVAL = 3.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("s", "start", "Start"),
        Binding("S", "shutdown", "Shutdown"),
        Binding("K", "stop", "Hard stop"),
        Binding("D", "delete", "Delete"),
        Binding("c", "console", "Console"),
        Binding("v", "vnc", "VNC screen"),
        Binding("x", "exec", "Exec…"),
        Binding("u", "userdata", "cloud-init"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, dict] = {}
        # Per-disk caches for the details pane (both survive the 3 s poll).
        self._disk_sizes: dict[str, int | None] = {}
        self._disk_infos: dict[str, dict | None] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("…", id="vm-info", classes="panel")
        yield DataTable(id="vms", cursor_type="row")
        yield Static("", id="vm-detail", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#vms", DataTable).add_columns(
            "Id", "Name", "Status", "vCPUs", "Memory", "Disk"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        info = await self.box(vm.info)
        # vm/info memory counts are MB, not bytes.
        total_mem = (info.get("total_memory") or 0) * 1024 * 1024
        used_mem = (info.get("used_memory") or 0) * 1024 * 1024
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
                    decode_lenient(v.get("disk_path")) or "",
                )
            )
        refill(self.query_one("#vms", DataTable), rows, list(self._by_id))
        self._show_detail()

    def _selected(self) -> tuple[int, dict] | None:
        vm_id = cursor_key(self.query_one("#vms", DataTable))
        if vm_id is None:
            return None
        return int(vm_id), self._by_id.get(vm_id, {})

    # -- details pane -----------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail()

    @work(exclusive=True, group="vm-detail")
    async def _show_detail(self) -> None:
        pane = self.query_one("#vm-detail", Static)
        if (sel := self._selected()) is None:
            pane.update("")
            return
        vm_id, item = sel
        disk = decode_lenient(item.get("disk_path"))
        size = await self._disk_size(disk) if disk else None
        dinfo = None
        if disk and item.get("status") != "running":
            # Verified live: the box refuses vm/disk/info while the disk is
            # attached to a running VM — only stopped VMs get virtual size.
            dinfo = await self._disk_info(disk)
        # The cursor may have moved while we were fetching.
        if (again := self._selected()) is None or again[0] != vm_id:
            return
        pane.update(self._detail_text(item, disk, size, dinfo))

    async def _disk_size(self, disk: str) -> int | None:
        """Bytes the image occupies on the box, via fs (works while running)."""
        path = "/" + disk.lstrip("/")
        if path not in self._disk_sizes:
            parent, _, name = path.rpartition("/")
            try:
                listing = await self.box(fs.ls, parent or "/")
            except BoxCallError:
                self._disk_sizes[path] = None
            else:
                sizes = {str(e.get("name")): e.get("size") for e in fs.entries(listing)}
                size = sizes.get(name)
                self._disk_sizes[path] = int(size) if isinstance(size, int) else None
        return self._disk_sizes[path]

    async def _disk_info(self, disk: str) -> dict | None:
        # The box stores VM disk paths relative as often as absolute, but
        # accepts the absolute form on input — normalize (also the cache key).
        path = "/" + disk.lstrip("/")
        if path not in self._disk_infos:
            try:
                info = await self.box(vm.disk_info, path)
            except BoxCallError:
                info = None
            self._disk_infos[path] = info if isinstance(info, dict) else None
        return self._disk_infos[path]

    def _detail_text(
        self, item: dict, disk: str, size: int | None, dinfo: dict | None
    ) -> Text:
        def label(text: Text, name: str) -> None:
            text.append(f"{name} ", style="dim")

        line1 = Text()
        label(line1, "OS")
        line1.append(str(item.get("os") or "?"))
        label(line1, "  ·  MAC")
        line1.append(str(item.get("mac") or "—"))
        label(line1, "  ·  screen (VNC)")
        line1.append(
            "yes — v opens Freebox OS" if item.get("enable_screen") else "no"
        )

        line2 = Text()
        label(line2, "Disk")
        line2.append(disk or "—")
        if item.get("disk_type"):
            line2.append(f" ({item.get('disk_type')})", style="dim")
        if size is not None:
            label(line2, "  —  on box")
            line2.append(fmt.human_bytes(size))
        if dinfo and dinfo.get("virtual_size") is not None:
            label(line2, "  ·  virtual")
            line2.append(fmt.human_bytes(dinfo.get("virtual_size")))
        elif item.get("status") == "running":
            line2.append("  ·  virtual size unavailable while running", style="dim")
        cd = decode_lenient(item.get("cd_path"))
        if cd:
            label(line2, "  ·  CD")
            line2.append(cd)

        line3 = Text()
        label(line3, "cloud-init")
        if item.get("enable_cloudinit"):
            line3.append("yes")
            if item.get("cloudinit_hostname"):
                label(line3, " — host")
                line3.append(str(item.get("cloudinit_hostname")))
            line3.append("  (u shows userdata)", style="dim")
        else:
            line3.append("no")

        return Text("\n").join([line1, line2, line3])

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

    def action_vnc(self) -> None:
        """The box's own VNC view, in the browser (no native client — issue #3).

        `#Fbx.os.app.vm.app` is Freebox OS's hash route for the VM app
        (discovered in its bundle: opening an app sets `#<className>`, and a
        hash on load reopens it); the screen window itself has no route.
        """
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        name = item.get("name") or vm_id
        if not item.get("enable_screen"):
            self.notify(
                f"{name} has no screen: enable_screen is off in its config, so "
                "the box runs it headless (serial console only).",
                severity="warning",
                timeout=8,
            )
            return
        import webbrowser

        host = self.app.runtime.host or "mafreebox.freebox.fr"
        webbrowser.open(f"http://{host}/#Fbx.os.app.vm.app")
        self.notify(f"Freebox OS opens in the browser — VMs → {name} → écran.")

    # -- console / exec / userdata ---------------------------------------------

    @work
    async def action_console(self) -> None:
        if (sel := self._selected()) is None:
            return
        vm_id, item = sel
        if item.get("status") != "running":
            self.notify("The VM must be running to attach its console.", severity="warning")
            return
        choice = await self.app.push_screen_wait(
            ConsolePreflightModal(
                str(item.get("name") or vm_id),
                cloudinit.find_credentials(str(item.get("cloudinit_userdata") or "")),
                offer_terminal=oslaunch.can_spawn_terminal(),
            )
        )
        if choice == "terminal":
            if oslaunch.spawn_terminal(["fbx", "vm", "console", str(vm_id)]):
                self.notify("Console opened in its own window — Ctrl-] there detaches.")
            else:
                self.notify(
                    "Couldn't open a terminal window — `a` attaches here instead.",
                    severity="warning",
                )
            return
        if choice != "attach":
            return
        # Release the terminal to the raw byte pump; the pump runs in a
        # thread so its own event loop (asyncio.run) doesn't collide with
        # the app's. A detach key brings the app back.
        with self.app.suspend():
            # A serial tty prints nothing until the guest does — without this
            # banner an idle console looks like a hang.
            name = item.get("name") or vm_id
            print(
                f"── {name} · serial console — {vmconsole.DETACH_HINT} returns "
                "to fbx; Enter wakes an idle prompt.",
                flush=True,
            )
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
