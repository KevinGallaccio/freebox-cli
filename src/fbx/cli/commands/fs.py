"""`fbx fs` — browse the box's filesystem."""

from __future__ import annotations

import time

import typer
from rich.table import Table

from ...core.api import fs as api
from ...core.api import share as share_api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Browse files on the box's storage.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="fs")


@app.command()
def ls(
    ctx: typer.Context,
    path: str = typer.Argument("/", help="Absolute path on the box (e.g. /Freebox)."),
) -> None:
    """List a directory on the box's storage."""
    data = fetch(ctx, api.ls, path)
    ui.emit(data, ctx.obj, table=lambda d: _ls_table(d, path))


@app.command()
def tasks(ctx: typer.Context) -> None:
    """List active file-operation tasks (copy/move/delete/extract…)."""
    data = fetch(ctx, api.tasks)
    ui.emit(data, ctx.obj, table=_tasks_table)


@app.command()
def task(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="File-operation task id."),
) -> None:
    """Show one file-operation task's progress."""
    data = fetch(ctx, api.task, task_id)
    ui.emit(data, ctx.obj)


# -- writes ----------------------------------------------------------------


@app.command()
def mkdir(
    ctx: typer.Context,
    parent: str = typer.Argument(..., help="Parent directory (absolute path)."),
    name: str = typer.Argument(..., help="New directory name."),
) -> None:
    """Create a directory."""
    data = fetch(ctx, api.mkdir, parent, name)
    ui.emit_write(data, ctx.obj, message=f"created {parent.rstrip('/')}/{name}")


@app.command()
def rename(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File/dir to rename (absolute path)."),
    name: str = typer.Argument(..., help="New name (no path)."),
) -> None:
    """Rename a file or directory in place."""
    data = fetch(ctx, api.rename, path, name)
    ui.emit_write(data, ctx.obj, message=f"renamed to {name}")


@app.command()
def mv(
    ctx: typer.Context,
    files: list[str] = typer.Argument(..., help="Files/dirs to move (absolute paths)."),
    to: str = typer.Option(..., "--to", help="Destination directory (absolute path)."),
    mode: str = typer.Option("overwrite", "--mode", help="Conflict: overwrite/both/recent/skip."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for the task to finish."),
    timeout: float = typer.Option(60.0, "--timeout", help="Seconds to wait."),
) -> None:
    """Move files/directories into another directory."""
    _run_fs_task(ctx, lambda c: api.move(c, files, to, mode=mode), wait, timeout, "move")


@app.command()
def cp(
    ctx: typer.Context,
    files: list[str] = typer.Argument(..., help="Files/dirs to copy (absolute paths)."),
    to: str = typer.Option(..., "--to", help="Destination directory (absolute path)."),
    mode: str = typer.Option("overwrite", "--mode", help="Conflict: overwrite/both/recent/skip."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for the task to finish."),
    timeout: float = typer.Option(60.0, "--timeout", help="Seconds to wait."),
) -> None:
    """Copy files/directories into another directory."""
    _run_fs_task(ctx, lambda c: api.copy(c, files, to, mode=mode), wait, timeout, "copy")


@app.command()
def rm(
    ctx: typer.Context,
    files: list[str] = typer.Argument(..., help="Files/dirs to delete (absolute paths)."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for the task to finish."),
    timeout: float = typer.Option(60.0, "--timeout", help="Seconds to wait."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete files/directories (recursively)."""
    ui.confirm(
        f"Delete {len(files)} path(s): {', '.join(files)}? This cannot be undone.",
        yes=yes,
    )
    _run_fs_task(ctx, lambda c: api.remove(c, files), wait, timeout, "delete")


@app.command("task-rm")
def task_rm(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="File-operation task id."),
) -> None:
    """Cancel/clear a file-operation task."""
    data = fetch(ctx, api.delete_task, task_id)
    ui.emit_write(data, ctx.obj, message=f"cleared fs task {task_id}")


# -- public share links ----------------------------------------------------


@app.command()
def shares(ctx: typer.Context) -> None:
    """List public share links."""
    data = fetch(ctx, share_api.list_links)
    ui.emit(data, ctx.obj, table=_shares_table)


@app.command()
def share(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File/dir to share (absolute path)."),
    days: int | None = typer.Option(None, "--days", help="Expire after N days (default: never)."),
) -> None:
    """Create a public share link for a path."""
    expire = 0 if days is None else int(time.time()) + days * 86400
    data = fetch(ctx, share_api.create, path, expire=expire)
    ui.emit_write(data, ctx.obj, message=f"shared {path}")


@app.command()
def unshare(
    ctx: typer.Context,
    token: str = typer.Argument(..., help="Share-link token (see `fbx fs shares`)."),
) -> None:
    """Revoke a public share link."""
    data = fetch(ctx, share_api.delete, token)
    ui.emit_write(data, ctx.obj, message=f"revoked share {token}")


def _run_fs_task(ctx: typer.Context, submit, wait: bool, timeout: float, verb: str) -> None:
    """Submit a task-based fs op, optionally poll it, and report the outcome."""

    def op(client):
        task_obj = submit(client)
        task_id = (task_obj or {}).get("id") if isinstance(task_obj, dict) else None
        if not wait or task_id is None:
            return task_obj, None
        final = api.poll_task(client, task_id, timeout=timeout)
        return task_obj, final

    submitted, final = fetch(ctx, op)
    task_id = submitted.get("id") if isinstance(submitted, dict) else None
    if not wait or task_id is None:
        ui.emit_write(submitted, ctx.obj, message=f"{verb} task submitted")
        return
    if api.task_failed(final):
        ui.emit_write(final or submitted, ctx.obj)
        ui.error(f"{verb} task {task_id} failed: {(final or {}).get('error', 'unknown')}")
        raise typer.Exit(1)
    if api.task_pending(final):
        # We stopped waiting, but the box is still working — don't claim success.
        ui.emit_write(final, ctx.obj)
        ui.warn(
            f"{verb} task {task_id} still running after {timeout:g}s "
            f"(state {final.get('state')}); check `fbx fs tasks`."
        )
        return
    state = (final or {}).get("state", "done")
    ui.emit_write(final if final is not None else submitted, ctx.obj, message=f"{verb} {state}")


def _tasks_table(items: list) -> Table:
    t = Table(box=None, title=f"File tasks — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Type")
    t.add_column("State")
    t.add_column("Progress", justify="right")
    t.add_column("From")
    t.add_column("To")
    for task in items:
        pct = task.get("progress")
        # `from`/`to` come back as plain paths here (not base64, unlike /fs/ls).
        t.add_row(
            str(task.get("id", "")),
            fmt.safe(task.get("type")),
            fmt.safe(task.get("state")),
            f"{pct}%" if fmt.is_num(pct) else "",
            fmt.safe(task.get("from")),
            fmt.safe(task.get("to")),
        )
    return t


def _shares_table(items: list) -> Table:
    t = Table(box=None, title=f"Share links — {len(items)}")
    t.add_column("Name")
    t.add_column("Token")
    t.add_column("Expire")
    t.add_column("URL")
    for s in items:
        expire = s.get("expire")
        t.add_row(
            fmt.safe(s.get("name")),
            fmt.safe(s.get("token")),
            fmt.epoch(expire) if expire else "never",
            fmt.safe(s.get("fullurl")),
        )
    return t


def _ls_table(data: object, path: str) -> Table:
    # `.` and `..` are display noise in a listing (JSON keeps them).
    entries = [e for e in api.entries(data) if e.get("name") not in (".", "..")]
    t = Table(box=None, title=f"{fmt.safe(path)} — {len(entries)} entries")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Size", justify="right")
    t.add_column("Modified")

    def sort_key(e: dict):
        return (e.get("type") != "dir", str(e.get("name") or "").lower())

    for e in sorted(entries, key=sort_key):
        is_dir = e.get("type") == "dir"
        name = fmt.safe(e.get("name") or "?")
        if e.get("hidden"):
            name = f"[dim]{name}[/]"
        contents = ""
        if is_dir:
            folders, files = e.get("foldercount"), e.get("filecount")
            if fmt.is_num(folders) and fmt.is_num(files):
                contents = f"{int(folders) + int(files)} items"
        t.add_row(
            f"[bold blue]{name}/[/]" if is_dir else name,
            fmt.safe(e.get("type")),
            contents if is_dir else fmt.human_bytes(e.get("size")),
            fmt.epoch(e.get("modification")),
        )
    return t
