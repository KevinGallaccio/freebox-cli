"""Address-book domain — contacts (requires the `contacts` permission)."""

from __future__ import annotations

from typing import Any

from . import as_list


def list_all(client: Any) -> list:
    """GET /contact/ — every contact (empty book → missing result → [])."""
    return as_list(client.get("contact/"))


# -- writes (all gated by the `contacts` permission) -----------------------


def create(client: Any, fields: dict) -> dict:
    """POST /contact/ — create a contact (e.g. `{display_name, first_name}`)."""
    client.require_permission("contacts")
    return client.post("contact/", data=fields)


def update(client: Any, contact_id: int, fields: dict) -> dict:
    """PUT /contact/{id} — edit a contact (partial body)."""
    client.require_permission("contacts")
    return client.put(f"contact/{contact_id}", data=fields)


def delete(client: Any, contact_id: int) -> Any:
    """DELETE /contact/{id} — remove a contact."""
    client.require_permission("contacts")
    return client.delete(f"contact/{contact_id}")
