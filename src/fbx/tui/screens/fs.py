"""Files: a terminal-in-terminal over the box's filesystem.

A tiny shell — `ls`, `cd`, `mkdir`, `mv`, `cp`, `rm`, `share`, `tasks` — with
the box's current directory in the prompt. Long operations (mv/cp/rm) are
task-based on the box; they're submitted and reported, and `tasks` shows
their progress.
"""

from __future__ import annotations

import shlex
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, Label, RichLog

from ...cli import fmt
from ...core.api import fs, share
from ..support import BoxCallError
from ._base import BoxScreen

_HELP = """\
ls [PATH]          list a directory
cd PATH            change directory (.. goes up)
pwd                print the current directory
mkdir NAME         create a directory here
mv SRC DST         move (box-side task)
cp SRC DST         copy (box-side task)
rm PATH            delete (box-side task, asks first)
share PATH [DAYS]  publish a download link (default: never expires)
tasks              show the box's file tasks
help               this text"""


class FsScreen(BoxScreen):
    POLL_INTERVAL = None  # a shell pulls, it doesn't poll

    BINDINGS = [Binding("escape", "app.back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.cwd = "/"

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="fs-log", markup=False, highlight=False, wrap=True)
        with Horizontal(id="fs-prompt-row"):
            yield Label("", id="fs-prompt")
            yield Input(id="fs-input", placeholder="type `help` for commands")
        yield Footer()

    def on_mount(self) -> None:
        self.cwd = str(self.app.prefs.get("screens.fs.last_dir", "/"))
        self._update_prompt()
        log = self.query_one("#fs-log", RichLog)
        log.write("The Freebox filesystem. Type `help` for commands.")
        self.query_one("#fs-input", Input).focus()
        super().on_mount()

    async def refresh_data(self) -> None:  # no polling; BoxScreen contract
        return

    def _update_prompt(self) -> None:
        self.query_one("#fs-prompt", Label).update(f"{self.cwd} > ")

    def _abs(self, path: str) -> str:
        if path.startswith("/"):
            parts = []
            base = path
        else:
            parts = [p for p in self.cwd.split("/") if p]
            base = path
        for piece in base.split("/"):
            if piece in ("", "."):
                continue
            if piece == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(piece)
        return "/" + "/".join(parts)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if line:
            self._run_line(line)

    @work
    async def _run_line(self, line: str) -> None:
        log = self.query_one("#fs-log", RichLog)
        log.write(f"{self.cwd} > {line}")
        try:
            args = shlex.split(line)
        except ValueError as exc:
            log.write(f"parse error: {exc}")
            return
        cmd, rest = args[0], args[1:]
        try:
            await self._dispatch(cmd, rest, log)
        except BoxCallError as exc:
            log.write(f"error: {exc}")

    async def _dispatch(self, cmd: str, args: list[str], log: RichLog) -> None:
        if cmd == "help":
            log.write(_HELP)
        elif cmd == "pwd":
            log.write(self.cwd)
        elif cmd == "ls":
            path = self._abs(args[0]) if args else self.cwd
            listing = await self.box(fs.ls, path)
            entries = [e for e in fs.entries(listing) if e.get("name") not in (".", "..")]
            entries.sort(key=lambda e: (e.get("type") != "dir", str(e.get("name") or "").lower()))
            for e in entries:
                if e.get("type") == "dir":
                    log.write(f"  {e.get('name')}/")
                else:
                    log.write(f"  {e.get('name')}  ({fmt.human_bytes(e.get('size'))})")
            log.write(f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} in {path}")
        elif cmd == "cd":
            if not args:
                log.write("cd: which directory?")
                return
            target = self._abs(args[0])
            await self.box(fs.ls, target)  # existence check; raises if bogus
            self.cwd = target
            self.app.prefs.set("screens.fs.last_dir", target)
            self._update_prompt()
        elif cmd == "mkdir":
            if not args:
                log.write("mkdir: which name?")
                return
            await self.box(fs.mkdir, self.cwd, args[0])
            log.write(f"created {self._abs(args[0])}")
        elif cmd in ("mv", "cp"):
            if len(args) != 2:
                log.write(f"{cmd}: needs SRC and DST")
                return
            src, dst = self._abs(args[0]), self._abs(args[1])
            op = fs.move if cmd == "mv" else fs.copy
            task = await self.box(op, [src], dst)
            task_id = task.get("id") if isinstance(task, dict) else "?"
            log.write(f"{cmd} started (task {task_id}) — `tasks` shows progress")
        elif cmd == "rm":
            if not args:
                log.write("rm: which path?")
                return
            target = self._abs(args[0])
            if not await self.confirm(
                f"Delete {target} from the box? This cannot be undone.",
                confirm_label="Delete",
            ):
                log.write("rm: cancelled")
                return
            task = await self.box(fs.remove, [target])
            task_id = task.get("id") if isinstance(task, dict) else "?"
            log.write(f"rm started (task {task_id})")
        elif cmd == "share":
            if not args:
                log.write("share: which path?")
                return
            expire = 0
            if len(args) > 1:
                try:
                    expire = int(time.time()) + int(args[1]) * 86400
                except ValueError:
                    log.write("share: DAYS must be a number")
                    return
            link = await self.box(share.create, self._abs(args[0]), expire=expire)
            log.write(f"→ {link.get('fullurl') or link}")
        elif cmd == "tasks":
            tasks = await self.box(fs.tasks)
            if not tasks:
                log.write("no file tasks")
            for t in tasks:
                pct = t.get("progress")
                pct_s = f" {pct}%" if pct is not None else ""
                log.write(
                    f"  #{t.get('id')} {t.get('type')} {t.get('state')}{pct_s}"
                    f"  {t.get('from') or ''} → {t.get('to') or ''}"
                )
        else:
            log.write(f"unknown command {cmd!r} — try `help`")
