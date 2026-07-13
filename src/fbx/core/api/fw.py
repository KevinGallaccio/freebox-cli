"""Firewall domain — port forwarding, DMZ, incoming-port policy, UPnP IGD.

New in Phase 3 (no read commands existed before). Static rules live under
`/fw/redir/`; the box's own built-in services under `/fw/incoming/`; the DMZ
host under `/fw/dmz/`; and the automatic (client-created) mappings under
`/upnpigd/redir/`. All writes need the `settings` permission.
"""

from __future__ import annotations

from typing import Any

from . import as_list


def redirs(client: Any) -> list:
    """GET /fw/redir/ — static (user-defined) port-forwarding rules."""
    return as_list(client.get("fw/redir/"))


def dmz(client: Any) -> dict:
    """GET /fw/dmz/ — the DMZ target host."""
    return client.get("fw/dmz/")


def incoming(client: Any) -> list:
    """GET /fw/incoming/ — incoming-port policy for the box's own services."""
    return as_list(client.get("fw/incoming/"))


def upnpigd_config(client: Any) -> dict:
    """GET /upnpigd/config/ — UPnP IGD (automatic port mapping) service state."""
    return client.get("upnpigd/config/")


def upnpigd_redirs(client: Any) -> list:
    """GET /upnpigd/redir/ — dynamic redirects created by LAN clients via UPnP."""
    return as_list(client.get("upnpigd/redir/"))


# -- writes (all gated by the `settings` permission) -----------------------


def create_redir(client: Any, fields: dict) -> dict:
    """POST /fw/redir/ — create a port-forwarding rule."""
    client.require_permission("settings")
    return client.post("fw/redir/", data=fields)


def update_redir(client: Any, redir_id: str, fields: dict) -> dict:
    """PUT /fw/redir/{redir_id} — change a port-forwarding rule (partial body)."""
    client.require_permission("settings")
    return client.put(f"fw/redir/{redir_id}", data=fields)


def delete_redir(client: Any, redir_id: str) -> Any:
    """DELETE /fw/redir/{redir_id} — remove a port-forwarding rule."""
    client.require_permission("settings")
    return client.delete(f"fw/redir/{redir_id}")


def set_dmz(client: Any, fields: dict) -> dict:
    """PUT /fw/dmz/ — set (or clear) the DMZ host (`{enabled, ip}`)."""
    client.require_permission("settings")
    return client.put("fw/dmz/", data=fields)


def update_incoming(client: Any, port_id: str, fields: dict) -> dict:
    """PUT /fw/incoming/{port_id} — reconfigure one built-in service's port."""
    client.require_permission("settings")
    return client.put(f"fw/incoming/{port_id}", data=fields)


def set_upnpigd_config(client: Any, fields: dict) -> dict:
    """PUT /upnpigd/config/ — enable/disable UPnP IGD or set its version."""
    client.require_permission("settings")
    return client.put("upnpigd/config/", data=fields)


def delete_upnpigd_redir(client: Any, redir_id: str) -> Any:
    """DELETE /upnpigd/redir/{id} — tear down a client-created UPnP mapping."""
    client.require_permission("settings")
    return client.delete(f"upnpigd/redir/{redir_id}")
