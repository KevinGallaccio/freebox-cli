"""Virtual Machines domain — the Freebox Ultra's aarch64 hypervisor.

Undocumented in the public SDK; shapes come from the on-box v16 docs and live
captures. Every write needs the `vm` permission. Disk operations are
long-running and task-based (poll `/vm/disk/task/{id}`). Filesystem paths
(`disk_path`, `cd_path`) cross the API base64-encoded — callers pass plain
absolute paths and this module encodes them.
"""

from __future__ import annotations

import time
from typing import Any

from .. import fspath
from ..errors import FbxAPIError
from . import as_list

# A disk task is `{id, type, error: bool, done: bool}` (verified live — NOTE this
# differs from fs tasks, which use string `state`/`error`). Terminal when
# `done` is true; failed when `error` is true.
_TASK_GONE_CODES = {"noent", "not_found", "task_not_found", "invalid_id"}

# VM config keys whose values are absolute paths and must be base64-encoded.
_PATH_KEYS = ("disk_path", "cd_path")


def _encode_paths(fields: dict) -> dict:
    """Return a copy of `fields` with any path-valued keys base64-encoded."""
    out = dict(fields)
    for key in _PATH_KEYS:
        if key in out and out[key] is not None and out[key] != "":
            out[key] = fspath.encode(out[key])
    return out


# -- reads -----------------------------------------------------------------


def list_vms(client: Any) -> list:
    """GET /vm/ — every configured VM (full config object each)."""
    return as_list(client.get("vm/"))


def get(client: Any, vm_id: int) -> dict:
    """GET /vm/{id} — one VM's config."""
    return client.get(f"vm/{vm_id}")


def info(client: Any) -> dict:
    """GET /vm/info/ — hypervisor capacity and current usage."""
    return client.get("vm/info/")


def distros(client: Any) -> list:
    """GET /vm/distros/ — the Free-curated catalog of installable cloud images."""
    return as_list(client.get("vm/distros/"))


# -- lifecycle writes (all gated by the `vm` permission) -------------------


def create(client: Any, config: dict) -> dict:
    """POST /vm/ — create a VM from a config object (paths given plain)."""
    client.require_permission("vm")
    return client.post("vm/", data=_encode_paths(config))


def update(client: Any, vm_id: int, fields: dict) -> dict:
    """PUT /vm/{id} — modify a VM's config (partial; paths given plain)."""
    client.require_permission("vm")
    return client.put(f"vm/{vm_id}", data=_encode_paths(fields))


def delete(client: Any, vm_id: int) -> Any:
    """DELETE /vm/{id} — remove a VM definition (its disk file is separate)."""
    client.require_permission("vm")
    return client.delete(f"vm/{vm_id}")


def start(client: Any, vm_id: int) -> Any:
    """POST /vm/{id}/start — power the VM on."""
    client.require_permission("vm")
    return client.post(f"vm/{vm_id}/start")


def stop(client: Any, vm_id: int) -> Any:
    """POST /vm/{id}/stop — force stop (hard power-off, no guest shutdown)."""
    client.require_permission("vm")
    return client.post(f"vm/{vm_id}/stop")


def powerbutton(client: Any, vm_id: int) -> Any:
    """POST /vm/{id}/powerbutton — ACPI soft power button (graceful shutdown)."""
    client.require_permission("vm")
    return client.post(f"vm/{vm_id}/powerbutton")


def restart(client: Any, vm_id: int) -> Any:
    """POST /vm/{id}/restart — restart the VM."""
    client.require_permission("vm")
    return client.post(f"vm/{vm_id}/restart")


# -- disk management (gated by the `vm` permission) ------------------------


def disk_info(client: Any, disk_path: str) -> dict:
    """POST /vm/disk/info — inspect a disk image (`disk_path` given plain)."""
    client.require_permission("vm")
    return client.post("vm/disk/info", data={"disk_path": fspath.encode(disk_path)})


def disk_create(client: Any, disk_path: str, size: int, *, disk_type: str = "qcow2") -> dict:
    """POST /vm/disk/create — create a virtual disk of `size` bytes. Returns a task."""
    client.require_permission("vm")
    return client.post(
        "vm/disk/create",
        data={"disk_path": fspath.encode(disk_path), "size": size, "disk_type": disk_type},
    )


def disk_resize(
    client: Any, disk_path: str, size: int, *, shrink_allow: bool = False
) -> dict:
    """POST /vm/disk/resize — grow (or, with `shrink_allow`, shrink) a disk. Returns a task."""
    client.require_permission("vm")
    return client.post(
        "vm/disk/resize",
        data={
            "disk_path": fspath.encode(disk_path),
            "size": size,
            "shrink_allow": shrink_allow,
        },
    )


def disk_task(client: Any, task_id: int) -> dict:
    """GET /vm/disk/task/{id} — poll a disk task's progress/state."""
    return client.get(f"vm/disk/task/{task_id}")


def delete_disk_task(client: Any, task_id: int) -> Any:
    """DELETE /vm/disk/task/{id} — cancel/clear a disk task."""
    client.require_permission("vm")
    return client.delete(f"vm/disk/task/{task_id}")


def poll_disk_task(
    client: Any, task_id: int, *, timeout: float = 120.0, interval: float = 0.5
) -> dict | None:
    """Poll a disk task until `done` is true or `timeout` elapses.

    Returns the final task object, or `None` if the box reaped it (completed).
    A returned object may still be un-done if `timeout` hit first — check
    `task_pending`. Only a "task gone" error ends the poll as `None`; any other
    box error propagates."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            current = disk_task(client, task_id)
        except FbxAPIError as exc:
            if exc.error_code in _TASK_GONE_CODES:
                return None
            raise
        if (current or {}).get("done") or time.monotonic() >= deadline:
            return current
        time.sleep(interval)


def task_failed(task_obj: dict | None) -> bool:
    """True if a finished disk task ended in error (None = reaped = success).

    `error` is a boolean here; tolerate a string form too (defensive)."""
    if not task_obj:
        return False
    error = task_obj.get("error")
    if isinstance(error, bool):
        return error
    return error not in (None, "none", "", False)


def task_pending(task_obj: dict | None) -> bool:
    """True if the disk task is STILL running (poll returned at its deadline)."""
    return bool(task_obj) and not task_obj.get("done", False)
