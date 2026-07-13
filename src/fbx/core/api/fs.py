"""Filesystem domain — browse the box's storage.

Paths cross this API base64-encoded (see `core.fspath`); callers hand this
module plain absolute paths and get plain entries back — the `path` token
inside each entry is left as returned, since it is what the API expects on
the next call.
"""

from __future__ import annotations

import time
from typing import Any

from .. import fspath
from ..errors import FbxAPIError
from . import as_list

# FsTask states that mean "still working"; anything else is terminal.
_ACTIVE_TASK_STATES = {"running", "queued", "paused", "starting", "pending"}

# Error codes that mean "this task id no longer exists" — i.e. it completed and
# the box reaped it. Any OTHER FbxAPIError while polling is a real problem
# (permission revoked, internal error) and must NOT be read as success.
_TASK_GONE_CODES = {"noent", "not_found", "task_not_found", "invalid_id"}


def ls(client: Any, path: str = "/") -> Any:
    """GET /fs/ls/{b64path} — list a directory. `path` is a plain absolute path.

    Returns the upstream result object as-is (observed: `{"entries": [...]}`)
    so `--json` stays lossless; use `entries()` to get the entry list.
    `countSubFolder` makes the box include `foldercount`/`filecount` on each
    directory entry (the web UI passes it too; omitted, they're absent).
    """
    return client.get(f"fs/ls/{fspath.encode(path)}", params={"countSubFolder": 1})


def entries(result: Any) -> list:
    """The entry list out of an `ls()` result, whatever the box sent."""
    if isinstance(result, dict):
        return as_list(result.get("entries"))
    # Observed shape is {"entries": [...]}; tolerate a bare list just in case.
    return as_list(result)


def tasks(client: Any) -> list:
    """GET /fs/tasks/ — active/queued file-operation tasks."""
    return as_list(client.get("fs/tasks/"))


def task(client: Any, task_id: int) -> dict:
    """GET /fs/tasks/{id} — one file-operation task's progress/state."""
    return client.get(f"fs/tasks/{task_id}")


# -- writes (all gated by the `explorer` permission) -----------------------
#
# Paths cross this API base64-encoded (see `core.fspath`). Callers pass plain
# absolute paths; we encode. `dst` for rename is a bare name (NOT a path, NOT
# base64) per the on-box docs; `dst` for mv/cp is a base64 destination dir.


def mkdir(client: Any, parent: str, dirname: str) -> Any:
    """POST /fs/mkdir/ — create `dirname` inside the `parent` directory."""
    client.require_permission("explorer")
    return client.post("fs/mkdir/", data={"parent": fspath.encode(parent), "dirname": dirname})


def rename(client: Any, src: str, dst: str) -> Any:
    """POST /fs/rename/ — rename `src` to the new name `dst` (same directory)."""
    client.require_permission("explorer")
    return client.post("fs/rename/", data={"src": fspath.encode(src), "dst": dst})


def move(client: Any, files: list[str], dst: str, *, mode: str = "overwrite") -> dict:
    """POST /fs/mv/ — move `files` into directory `dst`. Returns an FsTask."""
    client.require_permission("explorer")
    body = {"files": [fspath.encode(f) for f in files], "dst": fspath.encode(dst), "mode": mode}
    return client.post("fs/mv/", data=body)


def copy(client: Any, files: list[str], dst: str, *, mode: str = "overwrite") -> dict:
    """POST /fs/cp/ — copy `files` into directory `dst`. Returns an FsTask."""
    client.require_permission("explorer")
    body = {"files": [fspath.encode(f) for f in files], "dst": fspath.encode(dst), "mode": mode}
    return client.post("fs/cp/", data=body)


def remove(client: Any, files: list[str]) -> dict:
    """POST /fs/rm/ — delete `files`. Returns an FsTask."""
    client.require_permission("explorer")
    return client.post("fs/rm/", data={"files": [fspath.encode(f) for f in files]})


def delete_task(client: Any, task_id: int) -> Any:
    """DELETE /fs/tasks/{id} — cancel/clear a file-operation task."""
    client.require_permission("explorer")
    return client.delete(f"fs/tasks/{task_id}")


def poll_task(
    client: Any, task_id: int, *, timeout: float = 60.0, interval: float = 0.4
) -> dict | None:
    """Poll GET /fs/tasks/{id} until it leaves an active state or `timeout`.

    Returns the final task object, or `None` if the box removed the task (a
    completed task can vanish, which we treat as "finished"). A returned object
    may still be in an active state if `timeout` was hit first — the caller must
    check `task_pending` before claiming success. Only a "task gone" error ends
    the poll as `None`; any other box error propagates (a revoked permission or
    an internal error must never masquerade as completion). The `time` module is
    used directly; tests exercise the non-polling path (a task already terminal
    on the first read)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            current = task(client, task_id)
        except FbxAPIError as exc:
            if exc.error_code in _TASK_GONE_CODES:
                return None  # task reaped → it finished
            raise  # a real error (auth, internal) — do not fake success
        state = (current or {}).get("state")
        if state not in _ACTIVE_TASK_STATES or time.monotonic() >= deadline:
            return current
        time.sleep(interval)


def task_failed(task_obj: dict | None) -> bool:
    """True if a finished FsTask ended in error (None = vanished = success)."""
    if not task_obj:
        return False
    state = task_obj.get("state")
    error = task_obj.get("error")
    return state in {"failed", "error"} or (error not in (None, "none"))


def task_pending(task_obj: dict | None) -> bool:
    """True if the task is STILL active — i.e. `poll_task` returned at its
    deadline, not at completion. The caller must not report this as success."""
    return bool(task_obj) and task_obj.get("state") in _ACTIVE_TASK_STATES
