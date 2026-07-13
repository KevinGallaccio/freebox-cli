"""System domain — box status and control (reboot, shutdown, standby)."""

from __future__ import annotations

from typing import Any


def info(client: Any) -> dict:
    """GET /system/ — firmware, model, uptime, temperatures, fans."""
    return client.get("system/")


def standby_status(client: Any) -> dict:
    """GET /standby/status — box standby planning state."""
    return client.get("standby/status")


# -- writes (all gated by the `settings` permission) -----------------------


def reboot(client: Any) -> Any:
    """POST /system/reboot/ — reboot the box."""
    client.require_permission("settings")
    return client.post("system/reboot/")


def shutdown(client: Any) -> Any:
    """POST /system/shutdown/ — shut the box down."""
    client.require_permission("settings")
    return client.post("system/shutdown/")


def set_standby(client: Any, fields: dict) -> dict:
    """PUT /standby/config — update standby planning (partial body ok)."""
    client.require_permission("settings")
    return client.put("standby/config", data=fields)
