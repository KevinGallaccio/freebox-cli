"""Connection / WAN domain — status, config, IPv6, logs, FTTH optics."""

from __future__ import annotations

from typing import Any

from . import as_list


def status(client: Any) -> dict:
    """GET /connection/ — WAN state and live throughput counters."""
    return client.get("connection/")


def config(client: Any) -> dict:
    """GET /connection/config/ — remote access & WAN options."""
    return client.get("connection/config/")


def ipv6_config(client: Any) -> dict:
    """GET /connection/ipv6/config/ — IPv6 enablement + delegated prefixes."""
    return client.get("connection/ipv6/config/")


def logs(client: Any) -> list:
    """GET /connection/logs/ — WAN link/connection up-down history."""
    return as_list(client.get("connection/logs/"))


def ftth(client: Any) -> dict:
    """GET /connection/ftth/ — FTTH/SFP optical-module telemetry
    (undocumented upstream; power values are hundredths of a dBm)."""
    return client.get("connection/ftth/")


# -- writes (all gated by the `settings` permission) -----------------------


def set_config(client: Any, fields: dict) -> dict:
    """PUT /connection/config/ — remote-access & WAN options (partial body)."""
    client.require_permission("settings")
    return client.put("connection/config/", data=fields)


def set_ipv6_config(client: Any, fields: dict) -> dict:
    """PUT /connection/ipv6/config/ — IPv6 enablement & firewall (partial body)."""
    client.require_permission("settings")
    return client.put("connection/ipv6/config/", data=fields)
