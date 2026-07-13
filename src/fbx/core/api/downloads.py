"""Downloads domain — the torrent/NZB/HTTP download manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import fspath
from . import as_list


def tasks(client: Any) -> list:
    """GET /downloads/ — every download task."""
    return as_list(client.get("downloads/"))


def stats(client: Any) -> dict:
    """GET /downloads/stats — aggregate manager counters and throughput."""
    return client.get("downloads/stats")


# -- writes (all gated by the `downloader` permission) ---------------------


def add_url(
    client: Any,
    *,
    url: str | None = None,
    url_list: list[str] | None = None,
    download_dir: str | None = None,
    filename: str | None = None,
    hash: str | None = None,
    username: str | None = None,
    password: str | None = None,
    recursive: bool | None = None,
    archive_password: str | None = None,
    cookies: str | None = None,
) -> Any:
    """POST /downloads/add — queue a download from a URL or magnet link.

    Form-encoded (not JSON). `download_dir` is a plain absolute path here; the
    box wants it base64-encoded, so we encode it. Magnet links are just passed
    as `url`."""
    client.require_permission("downloader")
    form: dict[str, str] = {}
    if url is not None:
        form["download_url"] = url
    if url_list is not None:
        form["download_url_list"] = "\n".join(url_list)
    if download_dir is not None:
        form["download_dir"] = fspath.encode(download_dir)
    if filename is not None:
        form["filename"] = filename
    if hash is not None:
        form["hash"] = hash
    if username is not None:
        form["username"] = username
    if password is not None:
        form["password"] = password
    if recursive is not None:
        form["recursive"] = "true" if recursive else "false"
    if archive_password is not None:
        form["archive_password"] = archive_password
    if cookies is not None:
        form["cookies"] = cookies
    return client.post_form("downloads/add", form=form)


def add_file(
    client: Any,
    file_path: str,
    *,
    download_dir: str | None = None,
    archive_password: str | None = None,
) -> Any:
    """POST /downloads/add — queue a download from a local .torrent/.nzb file.

    Uploaded as `multipart/form-data` under the `download_file` field."""
    client.require_permission("downloader")
    p = Path(file_path)
    files = {"download_file": (p.name, p.read_bytes())}
    form: dict[str, str] = {}
    if download_dir is not None:
        form["download_dir"] = fspath.encode(download_dir)
    if archive_password is not None:
        form["archive_password"] = archive_password
    return client.post_form("downloads/add", form=form or None, files=files)


def update_task(client: Any, task_id: int, fields: dict) -> Any:
    """PUT /downloads/{id} — pause/resume (`status`) or reprioritize."""
    client.require_permission("downloader")
    return client.put(f"downloads/{task_id}", data=fields)


def delete_task(client: Any, task_id: int) -> Any:
    """DELETE /downloads/{id} — remove the task, keeping downloaded files."""
    client.require_permission("downloader")
    return client.delete(f"downloads/{task_id}")


def erase_task(client: Any, task_id: int) -> Any:
    """DELETE /downloads/{id}/erase — remove the task AND erase its files."""
    client.require_permission("downloader")
    return client.delete(f"downloads/{task_id}/erase")


def set_throttling(client: Any, mode: str) -> Any:
    """PUT /downloads/throttling — force a throttling profile (or `schedule`)."""
    client.require_permission("downloader")
    return client.put("downloads/throttling", data={"throttling": mode})


def set_file_priority(client: Any, task_id: int, file_id: str, priority: str) -> Any:
    """PUT /downloads/{task_id}/files/{file_id} — set one file's priority."""
    client.require_permission("downloader")
    return client.put(f"downloads/{task_id}/files/{file_id}", data={"priority": priority})
