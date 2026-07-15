"""Files: a terminal-in-terminal over the box's filesystem.

A tiny shell — `ls`, `cd`, `tree`, `mkdir`, `mv`, `cp`, `rm`, `share`,
`tasks` — that behaves like a real one: the prompt lives inline in the
scrollback, Tab completes commands and remote paths, ↑/↓ recall history
(persisted), and long operations (mv/cp/rm) are task-based on the box.
"""

from __future__ import annotations

import os.path
import shlex
import time

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, Static

from ...cli import fmt
from ...core.api import fs, share
from ..support import BoxCallError
from ._base import BoxScreen

_HELP = """\
ls [PATH]          list a directory
cd [PATH]          change directory (`cd` → /, `cd -` → back, .. goes up)
pwd                print the current directory
tree [PATH]        directory tree, a few levels deep
mkdir NAME         create a directory here
mv SRC DST         move (box-side task)
cp SRC DST         copy (box-side task)
rm PATH            delete (box-side task, asks first)
share PATH [DAYS]  publish a download link (default: never expires)
tasks              show the box's file tasks
clear              wipe the scrollback
help               this text"""

_COMMANDS = (
    "cd", "clear", "cp", "help", "ls", "mkdir", "mv", "pwd", "rm", "share",
    "tasks", "tree",
)

HISTORY_MAX = 100
SCROLLBACK_MAX = 2000
TREE_DEPTH = 3
TREE_ENTRIES = 500


class ShellInput(Input):
    """The prompt's input line; the screen owns completion and history."""

    BINDINGS = [
        Binding("tab", "screen.complete", "Complete", show=False),
        Binding("up", "screen.history_prev", "History", show=False),
        Binding("down", "screen.history_next", "History", show=False),
    ]


class FsScreen(BoxScreen):
    POLL_INTERVAL = None  # a shell pulls, it doesn't poll

    BINDINGS = [Binding("escape", "app.back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.cwd = "/"
        self._prev_cwd: str | None = None
        self._lines: list[Text] = []
        self._flush_scheduled = False
        self._history: list[str] = []
        self._hist_pos: int | None = None
        self._hist_draft = ""
        # Listings fetched for completion/ls, reused by Tab until a write.
        self._ls_cache: dict[str, list[dict]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="fs-term"):
            yield Static(Text(), id="fs-scrollback")
            with Horizontal(id="fs-prompt-line"):
                yield Label("", id="fs-prompt")
                yield ShellInput(id="fs-input", placeholder="type `help` for commands")
        yield Footer()

    def on_mount(self) -> None:
        self.cwd = str(self.app.prefs.get("screens.fs.last_dir", "/"))
        history = self.app.prefs.get("screens.fs.history")
        if isinstance(history, list):
            self._history = [str(line) for line in history][-HISTORY_MAX:]
        self._update_prompt()
        self._write("The Freebox filesystem. `help` lists commands; Tab completes.")
        self.query_one("#fs-input", ShellInput).focus()
        super().on_mount()

    async def refresh_data(self) -> None:  # no polling; BoxScreen contract
        return

    # -- scrollback -----------------------------------------------------------

    def _write(self, line: Text | str) -> None:
        if isinstance(line, str):
            line = Text(line)
        self._lines.append(line)
        if len(self._lines) > SCROLLBACK_MAX:
            del self._lines[: len(self._lines) - SCROLLBACK_MAX]
        # Commands emit many lines at once; re-render the Static once per batch.
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.call_next(self._flush)

    def _flush(self) -> None:
        self._flush_scheduled = False
        self.query_one("#fs-scrollback", Static).update(Text("\n").join(self._lines))
        # Output jumps the view to the prompt, terminal-style. (Not anchor():
        # textual 8.2.8's compositor wedges an anchored, underfull container
        # at a negative scroll offset — set_reactive skips the clamp.)
        self.query_one("#fs-term", VerticalScroll).scroll_end(animate=False)

    # -- prompt line ----------------------------------------------------------

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
        self._hist_pos = None
        if not line:
            return
        if not self._history or self._history[-1] != line:
            self._history = (self._history + [line])[-HISTORY_MAX:]
            self.app.prefs.set("screens.fs.history", self._history)
        # Submitting re-pins the view to the bottom, like a terminal would.
        self.query_one("#fs-term", VerticalScroll).scroll_end(animate=False)
        self._run_line(line)

    # -- history --------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        # Editing a recalled line leaves history mode (our own recall sets the
        # value to the entry itself, so this only fires for real edits).
        if self._hist_pos is not None and event.value != self._history[self._hist_pos]:
            self._hist_pos = None

    def action_history_prev(self) -> None:
        if not self._history:
            return
        inp = self.query_one("#fs-input", ShellInput)
        if self._hist_pos is None:
            self._hist_draft = inp.value
            self._hist_pos = len(self._history)
        if self._hist_pos > 0:
            self._hist_pos -= 1
            inp.value = self._history[self._hist_pos]
            inp.cursor_position = len(inp.value)

    def action_history_next(self) -> None:
        if self._hist_pos is None:
            return
        inp = self.query_one("#fs-input", ShellInput)
        self._hist_pos += 1
        if self._hist_pos >= len(self._history):
            self._hist_pos = None
            inp.value = self._hist_draft
        else:
            inp.value = self._history[self._hist_pos]
        inp.cursor_position = len(inp.value)

    # -- completion -----------------------------------------------------------

    def action_complete(self) -> None:
        self._complete()

    @work(exclusive=True, group="fs-complete")
    async def _complete(self) -> None:
        inp = self.query_one("#fs-input", ShellInput)
        value = inp.value
        before, sep, token = value.rpartition(" ")
        if not sep:
            # First word: a command name.
            cands = [c + " " for c in _COMMANDS if c.startswith(token)]
            self._offer(inp, value, token, cands)
            return
        # A path: list the directory the fragment sits in.
        base, slash, frag = token.rpartition("/")
        if slash:
            dirpath = self._abs(base or "/") if token.startswith("/") else self._abs(base)
        else:
            dirpath = self.cwd
        try:
            entries = await self._listing(dirpath)
        except BoxCallError:
            return
        cands = []
        for e in entries:
            name = str(e.get("name") or "")
            if name in (".", "..") or not name.startswith(frag):
                continue
            cands.append(name + "/" if e.get("type") == "dir" else name + " ")
        self._offer(inp, value, frag, cands)

    def _offer(self, inp: ShellInput, value: str, frag: str, cands: list[str]) -> None:
        """Readline rules: unique → insert, common prefix → extend, else show."""
        if not cands:
            return
        if len(cands) == 1:
            completed = cands[0]
        else:
            common = os.path.commonprefix(cands)
            if len(common.rstrip()) <= len(frag):
                self._write(Text("  ".join(sorted(c.strip() for c in cands)), style="dim"))
                return
            completed = common
        inp.value = value[: len(value) - len(frag)] + completed
        inp.cursor_position = len(inp.value)

    async def _listing(self, path: str) -> list[dict]:
        if path not in self._ls_cache:
            listing = await self.box(fs.ls, path)
            self._ls_cache[path] = list(fs.entries(listing))
        return self._ls_cache[path]

    # -- the shell ------------------------------------------------------------

    @work
    async def _run_line(self, line: str) -> None:
        echo = Text()
        echo.append(f"{self.cwd} > ", style="bold")
        echo.append(line)
        self._write(echo)
        inp = self.query_one("#fs-input", ShellInput)
        inp.disabled = True  # one command at a time, like a terminal
        try:
            try:
                args = shlex.split(line)
            except ValueError as exc:
                self._write(f"parse error: {exc}")
                return
            try:
                await self._dispatch(args[0], args[1:])
            except BoxCallError as exc:
                self._write(f"error: {exc}")
        finally:
            inp.disabled = False
            inp.focus()

    def _ls_line(self, e: dict, name_width: int) -> Text:
        is_dir = e.get("type") == "dir"
        name = str(e.get("name") or "?") + ("/" if is_dir else "")
        style = "bold blue" if is_dir else ""
        if e.get("hidden"):
            style = f"dim {style}".strip()
        if is_dir:
            folders, files = e.get("foldercount"), e.get("filecount")
            size = (
                f"{int(folders) + int(files)} items"
                if fmt.is_num(folders) and fmt.is_num(files)
                else ""
            )
        else:
            size = fmt.human_bytes(e.get("size"))
        line = Text("  ")
        line.append(name.ljust(name_width), style=style)
        line.append(size.rjust(10), style="" if not is_dir else "dim")
        line.append("  ")
        line.append(fmt.epoch(e.get("modification")), style="dim")
        return line

    async def _dispatch(self, cmd: str, args: list[str]) -> None:
        if cmd == "help":
            self._write(_HELP)
        elif cmd == "pwd":
            self._write(self.cwd)
        elif cmd == "clear":
            self._lines.clear()
            self._flush()
        elif cmd == "ls":
            path = self._abs(args[0]) if args else self.cwd
            listing = await self.box(fs.ls, path)
            entries = [e for e in fs.entries(listing) if e.get("name") not in (".", "..")]
            self._ls_cache[path] = entries  # completion reuses fresh listings
            entries.sort(key=lambda e: (e.get("type") != "dir", str(e.get("name") or "").lower()))
            width = max((len(str(e.get("name") or "?")) for e in entries), default=0) + 2
            for e in entries:
                self._write(self._ls_line(e, width))
            self._write(f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} in {path}")
        elif cmd == "tree":
            root = self._abs(args[0]) if args else self.cwd
            self._write(root)
            shown = await self._tree(root, "", TREE_DEPTH, TREE_ENTRIES)
            if shown < 0:
                self._write(Text("… (truncated)", style="dim"))
        elif cmd == "cd":
            if args and args[0] == "-":
                if self._prev_cwd is None:
                    self._write("cd: no previous directory")
                    return
                target = self._prev_cwd
            else:
                target = self._abs(args[0]) if args else "/"
            await self.box(fs.ls, target)  # existence check; raises if bogus
            self._prev_cwd, self.cwd = self.cwd, target
            self.app.prefs.set("screens.fs.last_dir", target)
            self._update_prompt()
        elif cmd == "mkdir":
            if not args:
                self._write("mkdir: which name?")
                return
            await self.box(fs.mkdir, self.cwd, args[0])
            self._ls_cache.clear()
            self._write(f"created {self._abs(args[0])}")
        elif cmd in ("mv", "cp"):
            if len(args) != 2:
                self._write(f"{cmd}: needs SRC and DST")
                return
            src, dst = self._abs(args[0]), self._abs(args[1])
            op = fs.move if cmd == "mv" else fs.copy
            task = await self.box(op, [src], dst)
            self._ls_cache.clear()
            task_id = task.get("id") if isinstance(task, dict) else "?"
            self._write(f"{cmd} started (task {task_id}) — `tasks` shows progress")
        elif cmd == "rm":
            if not args:
                self._write("rm: which path?")
                return
            target = self._abs(args[0])
            if not await self.confirm(
                f"Delete {target} from the box? This cannot be undone.",
                confirm_label="Delete",
            ):
                self._write("rm: cancelled")
                return
            task = await self.box(fs.remove, [target])
            self._ls_cache.clear()
            task_id = task.get("id") if isinstance(task, dict) else "?"
            self._write(f"rm started (task {task_id})")
        elif cmd == "share":
            if not args:
                self._write("share: which path?")
                return
            expire = 0
            if len(args) > 1:
                try:
                    expire = int(time.time()) + int(args[1]) * 86400
                except ValueError:
                    self._write("share: DAYS must be a number")
                    return
            link = await self.box(share.create, self._abs(args[0]), expire=expire)
            self._write(f"→ {link.get('fullurl') or link}")
        elif cmd == "tasks":
            tasks = await self.box(fs.tasks)
            if not tasks:
                self._write("no file tasks")
            for t in tasks:
                pct = t.get("progress")
                pct_s = f" {pct}%" if pct is not None else ""
                self._write(
                    f"  #{t.get('id')} {t.get('type')} {t.get('state')}{pct_s}"
                    f"  {t.get('from') or ''} → {t.get('to') or ''}"
                )
        else:
            self._write(f"unknown command {cmd!r} — try `help`")

    async def _tree(self, path: str, indent: str, depth: int, budget: int) -> int:
        """Write one directory level; return the remaining budget (<0: truncated)."""
        listing = await self.box(fs.ls, path)
        entries = [e for e in fs.entries(listing) if e.get("name") not in (".", "..")]
        entries.sort(key=lambda e: (e.get("type") != "dir", str(e.get("name") or "").lower()))
        for i, e in enumerate(entries):
            if budget <= 0:
                return -1
            budget -= 1
            last = i == len(entries) - 1
            is_dir = e.get("type") == "dir"
            line = Text(f"{indent}{'└── ' if last else '├── '}")
            line.append(
                str(e.get("name") or "?") + ("/" if is_dir else ""),
                style="bold blue" if is_dir else "",
            )
            self._write(line)
            if is_dir and depth > 1:
                budget = await self._tree(
                    self._abs(f"{path}/{e.get('name')}"),
                    indent + ("    " if last else "│   "),
                    depth - 1,
                    budget,
                )
                if budget < 0:
                    return budget
        return budget
