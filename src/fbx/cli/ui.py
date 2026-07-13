"""Terminal UX and the stdout/stderr contract.

**Rule #2, load-bearing: stdout is data, stderr is UI.** Command results go to
stdout (so `fbx … --json | jq` works); every message, spinner, prompt, warning,
and error goes to stderr. Get this wrong and piping breaks and the agent story
collapses. All output flows through this module so the rule is enforced in one
place.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

# Data → stdout. UI (messages, spinners, prompts, errors) → stderr.
out = Console()
err = Console(stderr=True)


class OutputFormat(str, Enum):
    TABLE = "table"
    JSON = "json"


@dataclasses.dataclass
class CliState:
    """Global options, threaded to commands via the Typer context."""

    profile: str = "default"
    output: OutputFormat = OutputFormat.TABLE
    json: bool = False
    quiet: bool = False
    verbose: bool = False
    host: str | None = None

    @property
    def as_json(self) -> bool:
        return self.json or self.output is OutputFormat.JSON


# -- messages (always stderr) ---------------------------------------------


def info(msg: str, state: CliState | None = None) -> None:
    if state is None or not state.quiet:
        err.print(msg)


def warn(msg: str) -> None:
    err.print(f"[yellow]warning:[/] {msg}")


def error(msg: str) -> None:
    err.print(f"[red]error:[/] {msg}")


def success(msg: str) -> None:
    err.print(f"[green]✓[/] {msg}")


# -- data (always stdout) -------------------------------------------------


def emit(
    data: Any,
    state: CliState,
    *,
    table: Callable[[Any], Table] | None = None,
) -> None:
    """Render `data` to stdout in the selected format.

    JSON mode prints the *whole* upstream object (rule #5: never a lossy
    subset). Table mode uses `table(data)` when a renderer is provided, and
    falls back to JSON when it isn't — so `--output table` never loses data it
    doesn't have a table for.
    """
    if state.as_json or table is None:
        emit_json(data)
    else:
        out.print(table(data))


def emit_json(data: Any) -> None:
    # Compact-but-readable, and never re-colorized (stdout may be a pipe).
    out.print_json(json.dumps(data, ensure_ascii=False, default=str))
