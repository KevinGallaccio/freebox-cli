"""`fbx downloads` — the download manager (read side)."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import downloads as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Download manager: tasks and stats.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="downloads")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List download tasks."""
    data = fetch(ctx, api.tasks)
    ui.emit(data, ctx.obj, table=_tasks_table)


@app.command()
def stats(ctx: typer.Context) -> None:
    """Show download-manager counters and throughput."""
    data = fetch(ctx, api.stats)
    ui.emit(data, ctx.obj, table=_stats_table)


# -- writes ----------------------------------------------------------------


@app.command()
def add(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Download URL or magnet link."),
    dir_: str | None = typer.Option(None, "--dir", help="Destination directory (absolute path)."),
    filename: str | None = typer.Option(None, "--filename", help="Override the saved name."),
    hash_: str | None = typer.Option(None, "--hash", help="sha256:… / sha512:… to verify."),
    username: str | None = typer.Option(None, "--user", help="HTTP auth username."),
    password: str | None = typer.Option(None, "--password", help="HTTP auth password."),
    recursive: bool = typer.Option(False, "--recursive", help="Recursive download."),
    archive_password: str | None = typer.Option(
        None, "--archive-password", help="Password to extract (nzb)."
    ),
    cookies: str | None = typer.Option(None, "--cookies", help="HTTP Cookie header value."),
) -> None:
    """Add a download from a URL or magnet link."""
    data = fetch(
        ctx,
        api.add_url,
        url=url,
        download_dir=dir_,
        filename=filename,
        hash=hash_,
        username=username,
        password=password,
        recursive=recursive if recursive else None,
        archive_password=archive_password,
        cookies=cookies,
    )
    ui.emit_write(data, ctx.obj, message="download queued")


@app.command("add-file")
def add_file(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Local .torrent or .nzb file to upload."),
    dir_: str | None = typer.Option(None, "--dir", help="Destination directory (absolute path)."),
    archive_password: str | None = typer.Option(
        None, "--archive-password", help="Password to extract (nzb)."
    ),
) -> None:
    """Add a download from a local .torrent/.nzb file."""
    data = fetch(ctx, api.add_file, path, download_dir=dir_, archive_password=archive_password)
    ui.emit_write(data, ctx.obj, message="download queued")


@app.command()
def pause(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
) -> None:
    """Pause a download task."""
    data = fetch(ctx, api.update_task, task_id, {"status": "stopped"})
    ui.emit_write(data, ctx.obj, message=f"paused task {task_id}")


@app.command()
def resume(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
) -> None:
    """Resume a paused download task."""
    data = fetch(ctx, api.update_task, task_id, {"status": "downloading"})
    ui.emit_write(data, ctx.obj, message=f"resumed task {task_id}")


@app.command()
def priority(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
    level: str = typer.Argument(..., help="I/O priority: low, normal, or high."),
) -> None:
    """Set a download task's I/O priority."""
    data = fetch(ctx, api.update_task, task_id, {"io_priority": level})
    ui.emit_write(data, ctx.obj, message=f"set task {task_id} priority to {level}")


@app.command()
def rm(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
) -> None:
    """Remove a download task, keeping the downloaded files."""
    data = fetch(ctx, api.delete_task, task_id)
    ui.emit_write(data, ctx.obj, message=f"removed task {task_id} (files kept)")


@app.command()
def erase(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove a download task AND erase its downloaded files."""
    ui.confirm(
        f"Erase task {task_id} and DELETE its downloaded files? This cannot be undone.",
        yes=yes,
    )
    data = fetch(ctx, api.erase_task, task_id)
    ui.emit_write(data, ctx.obj, message=f"erased task {task_id} and its files")


@app.command()
def throttle(
    ctx: typer.Context,
    mode: str = typer.Argument(..., help="Throttling profile: normal, slow, or schedule."),
) -> None:
    """Switch the download throttling profile."""
    data = fetch(ctx, api.set_throttling, mode)
    ui.emit_write(data, ctx.obj, message=f"throttling → {mode}")


@app.command("file-priority")
def file_priority(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Download task id."),
    file_id: str = typer.Argument(..., help="File id (e.g. 1-1; see the task's files)."),
    level: str = typer.Argument(..., help="Priority: no_dl, low, normal, or high."),
) -> None:
    """Set the priority of one file within a task."""
    data = fetch(ctx, api.set_file_priority, task_id, file_id, level)
    ui.emit_write(data, ctx.obj, message=f"set file {file_id} priority to {level}")


_STATUS_STYLE = {"done": "green", "downloading": "cyan", "seeding": "cyan", "error": "red"}


def _tasks_table(items: list) -> Table:
    t = Table(box=None, title=f"Downloads — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Status")
    t.add_column("Progress", justify="right")
    t.add_column("Size", justify="right")
    t.add_column("Rate ↓")
    t.add_column("ETA")
    for task in items:
        status = str(task.get("status") or "")
        style = _STATUS_STYLE.get(status)
        rx_pct = task.get("rx_pct")
        # rx_pct is per-10000; floor, so 9999 shows 99% (not a premature 100%).
        progress = f"{int(rx_pct // 100)}%" if fmt.is_num(rx_pct) else ""
        t.add_row(
            str(task.get("id", "")),
            fmt.safe(task.get("name")),
            fmt.safe(task.get("type")),
            f"[{style}]{fmt.safe(status)}[/]" if style else fmt.safe(status),
            progress,
            fmt.human_bytes(task.get("size")),
            fmt.human_rate(task.get("rx_rate")),
            fmt.duration(task.get("eta")) if task.get("eta") else "",
        )
    return t


def _stats_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Download stats")
    t.add_column(style="bold")
    t.add_column()
    throttling = d.get("throttling_rate") or {}
    throttle = ""
    if throttling.get("rx_rate") or throttling.get("tx_rate"):
        throttle = (
            f"{fmt.human_rate(throttling.get('rx_rate'))} / "
            f"{fmt.human_rate(throttling.get('tx_rate'))}"
        )
    rows = [
        ("Tasks", d.get("nb_tasks")),
        ("Active", d.get("nb_tasks_active")),
        ("Downloading", d.get("nb_tasks_downloading")),
        ("Seeding", d.get("nb_tasks_seeding")),
        ("Queued", d.get("nb_tasks_queued")),
        ("Stopped", d.get("nb_tasks_stopped")),
        ("Done", d.get("nb_tasks_done")),
        ("Error", d.get("nb_tasks_error")),
        (
            "Rate ↓ / ↑",
            f"{fmt.human_rate(d.get('rx_rate'))} / {fmt.human_rate(d.get('tx_rate'))}"
            if d.get("rx_rate") is not None or d.get("tx_rate") is not None
            else None,
        ),
        ("Throttling", d.get("throttling_mode")),
        ("Throttle ↓ / ↑", throttle or None),
        ("Peers", d.get("nb_peer")),
        ("Connection ready", fmt.yesno(d.get("conn_ready"))),
    ]
    for label, value in rows:
        if value is not None and value != "":
            t.add_row(label, fmt.safe(value))
    return t
