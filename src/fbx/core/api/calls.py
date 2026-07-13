"""Telephony domain — call log (requires the `calls` permission)."""

from __future__ import annotations

from typing import Any

from . import as_list


def log(client: Any) -> list:
    """GET /call/log/ — call history, newest first."""
    return as_list(client.get("call/log/"))


# -- writes (all gated by the `calls` permission) --------------------------


def mark_read(client: Any, call_id: int) -> dict:
    """PUT /call/log/{id} — mark one call entry as read (`new: false`)."""
    client.require_permission("calls")
    return client.put(f"call/log/{call_id}", data={"new": False})


def mark_all_read(client: Any) -> Any:
    """POST /call/log/mark_all_as_read/ — mark every call entry as read."""
    client.require_permission("calls")
    return client.post("call/log/mark_all_as_read/")


def delete_entry(client: Any, call_id: int) -> Any:
    """DELETE /call/log/{id} — delete one call-log entry."""
    client.require_permission("calls")
    return client.delete(f"call/log/{call_id}")


def delete_all(client: Any) -> Any:
    """POST /call/log/delete_all/ — clear the entire call log."""
    client.require_permission("calls")
    return client.post("call/log/delete_all/")
