"""`fbx vm` — the Freebox Ultra's virtual-machine manager (the flagship)."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

import typer
from rich.table import Table

from ...core import client as core_client
from ...core import vmconsole
from ...core.api import vm as api
from .. import fmt, ui
from ._common import fetch


def _disk_display(token: object) -> str:
    """Decode a VM disk/cd base64 path for display.

    Unlike fs paths, the box stores VM disk paths **relative** (no leading `/`,
    e.g. `Freebox/VMs/x.qcow2`), so `core.fspath.decode`'s absolute-path guard
    can't render them — decode directly, falling back to the raw token."""
    if not token:
        return ""
    try:
        return base64.b64decode(str(token), validate=True).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return str(token)

app = typer.Typer(help="Virtual machines: lifecycle, disks, and the console.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="vm")


_SIZE_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def _parse_size(text: str) -> int:
    """'2G' / '512M' / '1073741824' → bytes."""
    s = text.strip().upper()
    if s and s[-1] in _SIZE_UNITS:
        return int(float(s[:-1]) * _SIZE_UNITS[s[-1]])
    return int(s)


# -- reads -----------------------------------------------------------------


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List all virtual machines."""
    data = fetch(ctx, api.list_vms)
    ui.emit(data, ctx.obj, table=_vms_table)


@app.command()
def show(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id (see `fbx vm list`)."),
) -> None:
    """Show one VM's configuration."""
    data = fetch(ctx, api.get, vm_id)
    ui.emit(data, ctx.obj, table=_vm_detail_table)


@app.command()
def info(ctx: typer.Context) -> None:
    """Show hypervisor capacity and current usage."""
    data = fetch(ctx, api.info)
    ui.emit(data, ctx.obj, table=_info_table)


@app.command()
def distros(ctx: typer.Context) -> None:
    """List installable cloud images from Free's catalog."""
    data = fetch(ctx, api.distros)
    ui.emit(data, ctx.obj, table=_distros_table)


# -- lifecycle writes ------------------------------------------------------


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="VM name."),
    disk: str = typer.Option(..., "--disk", help="Disk image path (absolute)."),
    os_: str = typer.Option("debian", "--os", help="OS hint (debian, ubuntu, alpine, …)."),
    memory: int = typer.Option(..., "--memory", help="RAM in MB."),
    vcpus: int = typer.Option(1, "--vcpus", help="vCPU count."),
    disk_type: str = typer.Option("qcow2", "--disk-type", help="qcow2 or raw."),
    cd: str | None = typer.Option(None, "--cd", help="Install ISO/CD image path (absolute)."),
    screen: bool = typer.Option(False, "--screen", help="Expose a VNC framebuffer."),
    usb: str | None = typer.Option(None, "--usb", help="USB ports to bind (see `fbx vm info`)."),
    cloudinit_hostname: str | None = typer.Option(
        None, "--cloudinit-hostname", help="cloud-init hostname."
    ),
    cloudinit_file: str | None = typer.Option(
        None, "--cloudinit-file", help="Path to a local #cloud-config userdata file."
    ),
) -> None:
    """Create a virtual machine."""
    config: dict = {
        "name": name,
        "os": os_,
        "vcpus": vcpus,
        "memory": memory,
        "disk_path": disk,
        "disk_type": disk_type,
        "enable_screen": screen,
    }
    if cd is not None:
        config["cd_path"] = cd
    if usb is not None:
        config["bind_usb_ports"] = usb
    if cloudinit_hostname is not None or cloudinit_file is not None:
        config["enable_cloudinit"] = True
        config["cloudinit_hostname"] = cloudinit_hostname or name
    if cloudinit_file is not None:
        config["cloudinit_userdata"] = Path(cloudinit_file).read_text()
    data = fetch(ctx, api.create, config)
    ui.emit_write(data, ctx.obj, message=f"created VM {name!r}")


@app.command("set")
def set_(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
    name: str | None = typer.Option(None, "--name", help="New name."),
    memory: int | None = typer.Option(None, "--memory", help="RAM in MB."),
    vcpus: int | None = typer.Option(None, "--vcpus", help="vCPU count."),
    disk: str | None = typer.Option(None, "--disk", help="Disk image path (absolute)."),
    cd: str | None = typer.Option(None, "--cd", help="CD image path (absolute)."),
    screen: bool | None = typer.Option(None, "--screen/--no-screen", help="VNC framebuffer."),
    cloudinit_hostname: str | None = typer.Option(None, "--cloudinit-hostname"),
    cloudinit_file: str | None = typer.Option(
        None, "--cloudinit-file", help="Path to a #cloud-config userdata file."
    ),
) -> None:
    """Modify a VM's configuration."""
    fields: dict = {}
    for key, value in (
        ("name", name),
        ("memory", memory),
        ("vcpus", vcpus),
        ("disk_path", disk),
        ("cd_path", cd),
        ("enable_screen", screen),
        ("cloudinit_hostname", cloudinit_hostname),
    ):
        if value is not None:
            fields[key] = value
    if cloudinit_file is not None:
        fields["cloudinit_userdata"] = Path(cloudinit_file).read_text()
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.update, vm_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated VM {vm_id}")


@app.command()
def start(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
) -> None:
    """Power a VM on."""
    data = fetch(ctx, api.start, vm_id)
    ui.emit_write(data, ctx.obj, message=f"started VM {vm_id}")


@app.command()
def stop(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Force stop a VM (hard power-off — the guest is NOT shut down cleanly)."""
    ui.confirm(
        f"Hard-stop VM {vm_id}? The guest OS is cut off immediately (like pulling "
        "the plug); use `vm shutdown` for a clean ACPI shutdown. Continue?",
        yes=yes,
    )
    data = fetch(ctx, api.stop, vm_id)
    ui.emit_write(data, ctx.obj, message=f"stopped VM {vm_id}")


@app.command()
def shutdown(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
) -> None:
    """Send the ACPI power button (graceful guest shutdown)."""
    data = fetch(ctx, api.powerbutton, vm_id)
    ui.emit_write(data, ctx.obj, message=f"sent ACPI shutdown to VM {vm_id}")


@app.command()
def restart(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Restart a VM."""
    ui.confirm(f"Restart VM {vm_id}?", yes=yes)
    data = fetch(ctx, api.restart, vm_id)
    ui.emit_write(data, ctx.obj, message=f"restarted VM {vm_id}")


@app.command()
def rm(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a VM definition (its disk image file is NOT removed)."""
    ui.confirm(
        f"Delete VM {vm_id}? Its configuration is removed (the disk image file "
        "stays on storage — delete it separately with `fbx fs rm`). Continue?",
        yes=yes,
    )
    data = fetch(ctx, api.delete, vm_id)
    ui.emit_write(data, ctx.obj, message=f"deleted VM {vm_id}")


# -- disk management -------------------------------------------------------


@app.command("disk-create")
def disk_create(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="New disk image path (absolute)."),
    size: str = typer.Argument(..., help="Size, e.g. 2G, 512M, or raw bytes."),
    disk_type: str = typer.Option("qcow2", "--type", help="qcow2 or raw."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for the task to finish."),
    timeout: float = typer.Option(120.0, "--timeout", help="Seconds to wait."),
) -> None:
    """Create a virtual disk image."""
    nbytes = _size_or_exit(size)
    _run_disk_task(
        ctx, lambda c: api.disk_create(c, path, nbytes, disk_type=disk_type), wait, timeout,
        f"create disk {path}",
    )


@app.command("disk-resize")
def disk_resize(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Disk image path (absolute)."),
    size: str = typer.Argument(..., help="New size, e.g. 4G."),
    shrink: bool = typer.Option(False, "--shrink", help="Allow shrinking (destructive!)."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for the task to finish."),
    timeout: float = typer.Option(120.0, "--timeout", help="Seconds to wait."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the shrink confirmation."),
) -> None:
    """Resize a virtual disk image."""
    nbytes = _size_or_exit(size)
    if shrink:
        ui.confirm(
            f"Shrink {path} to {size}? Data beyond the new size is LOST. Continue?",
            yes=yes,
        )
    _run_disk_task(
        ctx, lambda c: api.disk_resize(c, path, nbytes, shrink_allow=shrink), wait, timeout,
        f"resize disk {path}",
    )


@app.command("disk-info")
def disk_info(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Disk image path (absolute)."),
) -> None:
    """Inspect a virtual disk image."""
    data = fetch(ctx, api.disk_info, path)
    ui.emit(data, ctx.obj)


@app.command("disk-task")
def disk_task(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Disk task id."),
) -> None:
    """Show a disk task's progress."""
    data = fetch(ctx, api.disk_task, task_id)
    ui.emit(data, ctx.obj)


@app.command("disk-task-rm")
def disk_task_rm(
    ctx: typer.Context,
    task_id: int = typer.Argument(..., help="Disk task id."),
) -> None:
    """Cancel/clear a disk task."""
    data = fetch(ctx, api.delete_disk_task, task_id)
    ui.emit_write(data, ctx.obj, message=f"cleared disk task {task_id}")


# -- console ---------------------------------------------------------------


@app.command()
def console(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
) -> None:
    """Attach to a VM's serial console (Ctrl-] to detach)."""
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host)
        with fbx:
            ui.info(f"[dim]attached to VM {vm_id} serial console — press Ctrl-] to detach[/]")
            vmconsole.console_runner(fbx, vm_id)
    ui.info("[dim]detached.[/]")


@app.command()
def vnc(
    ctx: typer.Context,
    vm_id: int = typer.Argument(..., help="VM id."),
) -> None:
    """Print the VNC framebuffer WebSocket URL (needs `--screen`; use a noVNC client)."""
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host, login=False)
        with fbx:
            url = vmconsole.vnc_url(fbx.base_url, vm_id)
    ui.emit_write({"vnc_url": url}, state, message="point a noVNC client at this URL")


# -- task-based disk helper ------------------------------------------------


def _size_or_exit(text: str) -> int:
    try:
        return _parse_size(text)
    except ValueError as exc:
        ui.error(f"invalid size {text!r}: use e.g. 2G, 512M, or a byte count.")
        raise typer.Exit(1) from exc


def _run_disk_task(ctx: typer.Context, submit, wait: bool, timeout: float, verb: str) -> None:
    """Submit a disk op, optionally poll its task, and report the outcome."""

    def op(client):
        result = submit(client)
        task_id = result.get("id") if isinstance(result, dict) else None
        if not wait or task_id is None:
            return result, None
        return result, api.poll_disk_task(client, task_id, timeout=timeout)

    submitted, final = fetch(ctx, op)
    task_id = submitted.get("id") if isinstance(submitted, dict) else None
    if not wait or task_id is None:
        ui.emit_write(submitted, ctx.obj, message=f"{verb} — task submitted")
        return
    if api.task_failed(final):
        ui.emit_write(final or submitted, ctx.obj)
        ui.error(f"{verb} failed: {(final or {}).get('error', 'unknown')}")
        raise typer.Exit(1)
    if api.task_pending(final):
        ui.emit_write(final, ctx.obj)
        ui.warn(
            f"{verb}: task {task_id} still running after {timeout:g}s "
            f"(state {final.get('state')}); check `fbx vm disk-task {task_id}`."
        )
        return
    ui.emit_write(final if final is not None else submitted, ctx.obj, message=f"{verb} — done")


# -- tables ----------------------------------------------------------------

_STATUS_STYLE = {"running": "green", "stopped": "red", "starting": "yellow", "stopping": "yellow"}


def _vms_table(items: list) -> Table:
    t = Table(box=None, title=f"Virtual machines — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Status")
    t.add_column("OS")
    t.add_column("vCPU", justify="right")
    t.add_column("RAM", justify="right")
    t.add_column("Disk")
    for v in sorted(items, key=lambda v: v.get("id", 0)):
        status = str(v.get("status") or "")
        style = _STATUS_STYLE.get(status)
        t.add_row(
            str(v.get("id", "")),
            fmt.safe(v.get("name")),
            f"[{style}]{fmt.safe(status)}[/]" if style else fmt.safe(status),
            fmt.safe(v.get("os")),
            str(v.get("vcpus", "")),
            f"{v.get('memory')} MB" if v.get("memory") is not None else "",
            fmt.safe(v.get("disk_type")),
        )
    return t


def _vm_detail_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title=f"VM {d.get('id')} — {fmt.safe(d.get('name'))}")
    t.add_column(style="bold")
    t.add_column()
    rows = [
        ("Status", fmt.safe(d.get("status"))),
        ("OS", fmt.safe(d.get("os"))),
        ("vCPUs", d.get("vcpus")),
        ("Memory", f"{d.get('memory')} MB" if d.get("memory") is not None else None),
        ("MAC", fmt.safe(d.get("mac"))),
        ("Disk", fmt.safe(_disk_display(d.get("disk_path"))) or None),
        ("Disk type", fmt.safe(d.get("disk_type"))),
        ("CD", fmt.safe(_disk_display(d.get("cd_path"))) or None),
        ("Screen (VNC)", fmt.yesno(d.get("enable_screen"))),
        ("cloud-init", fmt.yesno(d.get("enable_cloudinit"))),
        ("cloud-init host", fmt.safe(d.get("cloudinit_hostname"))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, str(value))
    # cloudinit_userdata holds secrets (SSH keys, passwords) — never in a table.
    if d.get("cloudinit_userdata"):
        t.add_row("cloud-init data", "[dim](hidden; use --json to see it)[/]")
    return t


def _info_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Hypervisor")
    t.add_column(style="bold")
    t.add_column()
    tc, uc = d.get("total_cpus"), d.get("used_cpus")
    tm, um = d.get("total_memory"), d.get("used_memory")
    if tc is not None:
        t.add_row("vCPUs", f"{uc}/{tc} used ({tc - uc} free)")
    if tm is not None:
        t.add_row("Memory", f"{um}/{tm} MB used ({tm - um} MB free)")
    usb = d.get("usb_ports") or []
    if usb:
        t.add_row("USB ports", ", ".join(fmt.safe(p) for p in usb))
    t.add_row("USB in use", fmt.yesno(d.get("usb_used")))
    return t


def _distros_table(items: list) -> Table:
    t = Table(box=None, title=f"Installable images — {len(items)}")
    t.add_column("Name")
    t.add_column("OS")
    t.add_column("URL")
    for d in items:
        t.add_row(fmt.safe(d.get("name")), fmt.safe(d.get("os")), fmt.safe(d.get("url")))
    return t
