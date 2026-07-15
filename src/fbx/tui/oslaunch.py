"""Open an OS terminal window running a command.

The app's only process-spawning code: the VM console pre-flight offers a
window of its own instead of suspending the TUI. Per terminal:

- Warp: its documented Tab Config file + `warp://tab_config/` URI (launch
  configurations are legacy and their URI proved a no-op).
- iTerm2: AppleScript, first-class support.
- Anything else on macOS: Terminal.app AppleScript (verified working).
- Linux: the first of the common terminal emulators found on PATH.
- Windows: not offered — the serial console pump itself is POSIX-only
  (termios), so a spawned window could only print an error.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

_WARP_TAB_CONFIG = """\
name = "fbx console"

[[panes]]
id = "console"
type = "terminal"
commands = [{command}]
"""


# Linux terminal emulators we know how to hand a command, in try order.
_LINUX_TERMINALS: tuple[tuple[str, ...], ...] = (
    ("x-terminal-emulator", "-e"),
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("xfce4-terminal", "-x"),
    ("xterm", "-e"),
)


def can_spawn_terminal() -> bool:
    if sys.platform == "darwin":
        return True
    if sys.platform.startswith("linux"):
        import shutil

        return any(shutil.which(term[0]) for term in _LINUX_TERMINALS)
    return False


def spawn_terminal(argv: list[str]) -> bool:
    """Run `argv` in a new terminal window; True if one was opened.

    The user's own terminal when we know how to talk to it ($TERM_PROGRAM:
    Warp, iTerm2), Terminal.app otherwise on macOS, best-effort on Linux.
    """
    command = shlex.join(argv)
    if sys.platform == "darwin":
        program = os.environ.get("TERM_PROGRAM", "")
        if program == "WarpTerminal" and _spawn_warp(command):
            return True
        if program == "iTerm.app" and _spawn_iterm(command):
            return True
        return _spawn_terminal_app(command)
    if sys.platform.startswith("linux"):
        return _spawn_linux(argv)
    return False


def _spawn_warp(command: str) -> bool:
    """One stable Tab Config, overwritten per launch, opened by file stem."""
    try:
        # An earlier fbx wrote a legacy launch-config that Warp ignores;
        # tidy it up if it's still around.
        with contextlib.suppress(OSError):
            (Path.home() / ".warp" / "launch_configurations" / "fbx-console.yaml").unlink()
        config_dir = Path.home() / ".warp" / "tab_configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = config_dir / "fbx-console.toml"
        # json.dumps produces a valid TOML basic string (quoting included).
        config.write_text(_WARP_TAB_CONFIG.format(command=json.dumps(command)))
        done = subprocess.run(
            ["open", "warp://tab_config/fbx-console?new_window=true"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0


def _applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _spawn_terminal_app(command: str) -> bool:
    script = f"tell application \"Terminal\" to do script {_applescript_quote(command)}"
    try:
        done = subprocess.run(
            ["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0


def _spawn_iterm(command: str) -> bool:
    lines = [
        'tell application "iTerm2"',
        "activate",
        "set newWindow to (create window with default profile)",
        f"tell current session of newWindow to write text {_applescript_quote(command)}",
        "end tell",
    ]
    script: list[str] = []
    for line in lines:
        script += ["-e", line]
    try:
        done = subprocess.run(
            ["osascript", *script], capture_output=True, check=False
        )
    except OSError:
        return False
    return done.returncode == 0


def _spawn_linux(argv: list[str]) -> bool:
    import shutil

    for terminal, flag in _LINUX_TERMINALS:
        if not shutil.which(terminal):
            continue
        try:
            subprocess.Popen(
                [terminal, flag, *argv],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue
        return True
    return False
