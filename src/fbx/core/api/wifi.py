"""Wi-Fi domain — global state, per-radio APs, BSS/SSIDs, associated stations."""

from __future__ import annotations

from typing import Any

from . import as_list


def config(client: Any) -> dict:
    """GET /wifi/config/ — global Wi-Fi service state."""
    return client.get("wifi/config/")


def state(client: Any) -> dict:
    """GET /wifi/state/ — radio detection map (one entry per PHY)."""
    return client.get("wifi/state/")


def aps(client: Any) -> list:
    """GET /wifi/ap/ — access points, one per radio/PHY."""
    return as_list(client.get("wifi/ap/"))


def bss(client: Any) -> list:
    """GET /wifi/bss/ — broadcast SSIDs with security config and status."""
    return as_list(client.get("wifi/bss/"))


def ap_stations(client: Any, ap_id: int) -> list:
    """GET /wifi/ap/{id}/stations/ — clients associated to one AP."""
    return as_list(client.get(f"wifi/ap/{ap_id}/stations/"))


def stations(client: Any) -> list:
    """All associated Wi-Fi clients, aggregated across every AP.

    There is no box-wide stations endpoint — only the per-AP one — so this
    walks /wifi/ap/ and concatenates. Each station is annotated with the AP
    it came from under `_fbx_ap` (an fbx-side key, absent upstream).
    """
    result: list = []
    for ap in aps(client):
        ap_id = ap.get("id")
        if ap_id is None:
            continue
        ap_band = (ap.get("config") or {}).get("band")
        for station in ap_stations(client, ap_id):
            station["_fbx_ap"] = {"id": ap_id, "name": ap.get("name"), "band": ap_band}
            result.append(station)
    return result


def mac_filters(client: Any) -> list:
    """GET /wifi/mac_filter/ — the MAC access-control list (empty → [])."""
    return as_list(client.get("wifi/mac_filter/"))


def planning(client: Any) -> dict:
    """GET /wifi/planning/ — the scheduled Wi-Fi on/off grid."""
    return client.get("wifi/planning/")


def wps_config(client: Any) -> dict:
    """GET /wifi/wps/config/ — the global WPS enable state."""
    return client.get("wifi/wps/config/")


# -- writes (all gated by the `settings` permission) -----------------------


def set_config(client: Any, fields: dict) -> dict:
    """PUT /wifi/config/ — global Wi-Fi state (`enabled`, `mac_filter_state`)."""
    client.require_permission("settings")
    return client.put("wifi/config/", data=fields)


def update_ap(client: Any, ap_id: int, config: dict) -> dict:
    """PUT /wifi/ap/{id} — change a radio's config (channel, width, enable)."""
    client.require_permission("settings")
    return client.put(f"wifi/ap/{ap_id}", data={"config": config})


def update_bss(client: Any, bss_id: str, config: dict) -> dict:
    """PUT /wifi/bss/{id} — change an SSID's config (ssid, key, encryption…)."""
    client.require_permission("settings")
    return client.put(f"wifi/bss/{bss_id}", data={"config": config})


def create_mac_filter(client: Any, *, mac: str, type: str, comment: str = "") -> dict:
    """POST /wifi/mac_filter/ — add a MAC to the access-control list.

    `type` is `whitelist` or `blacklist`. The entry only takes effect once the
    global `mac_filter_state` is set to a matching mode via `set_config`."""
    client.require_permission("settings")
    return client.post("wifi/mac_filter/", data={"mac": mac, "type": type, "comment": comment})


def update_mac_filter(client: Any, filter_id: str, fields: dict) -> dict:
    """PUT /wifi/mac_filter/{id} — edit a MAC-filter entry (type/comment)."""
    client.require_permission("settings")
    return client.put(f"wifi/mac_filter/{filter_id}", data=fields)


def delete_mac_filter(client: Any, filter_id: str) -> Any:
    """DELETE /wifi/mac_filter/{id} — remove a MAC-filter entry."""
    client.require_permission("settings")
    return client.delete(f"wifi/mac_filter/{filter_id}")


def set_planning(client: Any, fields: dict) -> dict:
    """PUT /wifi/planning/ — update the scheduled on/off planning."""
    client.require_permission("settings")
    return client.put("wifi/planning/", data=fields)


def temp_disable(client: Any, *, duration: int, keep: str | None = None) -> Any:
    """POST /wifi/temp_disable — disable Wi-Fi for `duration` seconds.

    `keep` optionally names a band to leave up (e.g. `2d4g`) so you don't cut
    your own link entirely."""
    client.require_permission("settings")
    body: dict[str, Any] = {"duration": duration}
    if keep is not None:
        body["keep"] = keep
    return client.post("wifi/temp_disable", data=body)


def set_wps(client: Any, enabled: bool) -> dict:
    """PUT /wifi/wps/config/ — set the global WPS enable state."""
    client.require_permission("settings")
    return client.put("wifi/wps/config/", data={"enabled": enabled})


def wps_start(client: Any, bssid: str) -> Any:
    """POST /wifi/wps/start/ — begin a WPS pairing session on a BSS."""
    client.require_permission("settings")
    return client.post("wifi/wps/start/", data={"bssid": bssid})


def wps_stop(client: Any) -> Any:
    """DELETE /wifi/wps/sessions/ — clear all active WPS sessions."""
    client.require_permission("settings")
    return client.delete("wifi/wps/sessions/")
