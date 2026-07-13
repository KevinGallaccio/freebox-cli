"""DHCP domain — server config, dynamic leases, static reservations."""

from __future__ import annotations

from typing import Any

from . import as_list


def config(client: Any) -> dict:
    """GET /dhcp/config/ — DHCPv4 server configuration."""
    return client.get("dhcp/config/")


def dynamic_leases(client: Any) -> list:
    """GET /dhcp/dynamic_lease/ — currently active leases."""
    return as_list(client.get("dhcp/dynamic_lease/"))


def static_leases(client: Any) -> list:
    """GET /dhcp/static_lease/ — configured static reservations."""
    return as_list(client.get("dhcp/static_lease/"))


# -- writes (all gated by the `settings` permission) -----------------------


def create_static_lease(client: Any, *, mac: str, ip: str, comment: str | None = None) -> dict:
    """POST /dhcp/static_lease/ — reserve `ip` for `mac`.

    The box keys the reservation on the MAC (returned as `id`). `comment` is a
    user note; only sent when provided (the documented minimal body is
    `{mac, ip}`)."""
    client.require_permission("settings")
    body: dict[str, Any] = {"mac": mac, "ip": ip}
    if comment is not None:
        body["comment"] = comment
    return client.post("dhcp/static_lease/", data=body)


def update_static_lease(client: Any, lease_id: str, fields: dict) -> dict:
    """PUT /dhcp/static_lease/{id} — change a reservation (id == the MAC)."""
    client.require_permission("settings")
    return client.put(f"dhcp/static_lease/{lease_id}", data=fields)


def delete_static_lease(client: Any, lease_id: str) -> Any:
    """DELETE /dhcp/static_lease/{id} — drop a reservation (id == the MAC)."""
    client.require_permission("settings")
    return client.delete(f"dhcp/static_lease/{lease_id}")


def set_config(client: Any, fields: dict) -> dict:
    """PUT /dhcp/config/ — update the DHCPv4 server config (partial body ok)."""
    client.require_permission("settings")
    return client.put("dhcp/config/", data=fields)
