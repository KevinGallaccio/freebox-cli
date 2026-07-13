"""LAN domain — the box's LAN identity and the network device browser."""

from __future__ import annotations

from typing import Any

from . import as_list

DEFAULT_INTERFACE = "pub"


def config(client: Any) -> dict:
    """GET /lan/config/ — the box's own LAN identity and router/bridge mode."""
    return client.get("lan/config/")


def interfaces(client: Any) -> list:
    """GET /lan/browser/interfaces/ — browsable L2 interfaces + host counts."""
    return as_list(client.get("lan/browser/interfaces/"))


def devices(client: Any, interface: str = DEFAULT_INTERFACE) -> list:
    """GET /lan/browser/{interface}/ — the LAN host list (the device browser)."""
    return as_list(client.get(f"lan/browser/{interface}/"))


# -- writes (all gated by the `settings` permission) -----------------------


def wake(client: Any, mac: str, *, interface: str = DEFAULT_INTERFACE, password: str = "") -> Any:
    """POST /lan/wol/{interface}/ — send a Wake-on-LAN magic packet to `mac`."""
    client.require_permission("settings")
    return client.post(f"lan/wol/{interface}/", data={"mac": mac, "password": password})


def update_host(
    client: Any, host_id: str, fields: dict, *, interface: str = DEFAULT_INTERFACE
) -> dict:
    """PUT /lan/browser/{interface}/{hostid}/ — rename a host / set its type.

    `host_id` is the browser id (e.g. `ether-02:00:00:00:00:05`). The box wants
    the id echoed in the body, so we merge it in alongside the changed fields
    (`primary_name`, `host_type`, …)."""
    client.require_permission("settings")
    body = {"id": host_id, **fields}
    return client.put(f"lan/browser/{interface}/{host_id}/", data=body)


def set_config(client: Any, fields: dict) -> dict:
    """PUT /lan/config/ — update the box's LAN identity / router-bridge mode."""
    client.require_permission("settings")
    return client.put("lan/config/", data=fields)
