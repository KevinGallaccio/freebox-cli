"""The declarative tool table: every MCP tool is one row mapping to `core.api`.

Each `ToolSpec` names a core function, its parameters (which become the tool's
JSON-Schema input), and its safety annotations. Dispatch is generic —
`spec.fn(client, **args)` — so a tool can't drift from its core function:
`tests/test_mcp.py` asserts every spec's params match the function's real
signature, and that every public `core.api` function is either exposed here or
explicitly excluded.

This module imports nothing from the `mcp` SDK, so listing tools (`fbx mcp
tools`) works without the optional dependency installed.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from typing import Any

from ..core import vmconsole
from ..core.api import (
    calls,
    connection,
    contacts,
    dhcp,
    downloads,
    fs,
    fw,
    lan,
    share,
    storage,
    system,
    vm,
    wifi,
)
from ..core.errors import FbxError

# -- the spec model ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Param:
    """One tool parameter; `type` is a JSON-Schema type name."""

    name: str
    type: str  # "string" | "integer" | "number" | "boolean" | "object" | "array"
    help: str
    required: bool = True
    items: str | None = None  # array item type
    enum: tuple[str, ...] | None = None


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: a name, a core function, and how to describe it."""

    name: str
    toolset: str
    fn: Callable[..., Any]
    description: str
    params: tuple[Param, ...] = ()
    readonly: bool = False
    destructive: bool = False  # only meaningful when not readonly
    open_world: bool = False   # reaches beyond the box (e.g. downloads a URL)


def input_schema(spec: ToolSpec) -> dict:
    """The JSON-Schema `inputSchema` for a tool, built from its params."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.params:
        prop: dict[str, Any] = {"type": p.type, "description": p.help}
        if p.items:
            prop["items"] = {"type": p.items}
        if p.enum:
            prop["enum"] = list(p.enum)
        props[p.name] = prop
        if p.required:
            required.append(p.name)
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _p(name: str, type_: str, help_: str, **kw: Any) -> Param:
    return Param(name, type_, help_, **kw)


# A `fields`/`config` object param, the API's read-modify-write shape.
def _fields(help_: str) -> Param:
    return _p("fields", "object", help_)


# -- thin adapter functions ---------------------------------------------------
# Composition of existing core calls only (submit + core poller, exactly the
# CLI's semantics); no new protocol logic.

_API_PREFIX_RE = re.compile(r"^/?api/(?:v\d+|latest)/", re.IGNORECASE)


def _api_request(
    client: Any, method: str, path: str, data: Any = None, params: dict | None = None
) -> Any:
    """A raw authenticated call; strips a pasted `/api/v16/` prefix like the CLI."""
    rel = _API_PREFIX_RE.sub("", path).lstrip("/")
    return client.request(method, rel, data=data, params=params)


def _finish_fs_task(client: Any, submitted: Any, wait: bool, timeout: float) -> dict:
    """Poll a submitted fs task like the CLI does; never report pending as done."""
    task_id = (submitted or {}).get("id") if isinstance(submitted, dict) else None
    if not wait or task_id is None:
        return {"status": "submitted", "task": submitted}
    final = fs.poll_task(client, task_id, timeout=timeout)
    if fs.task_failed(final):
        raise FbxError(f"fs task {task_id} failed: {(final or {}).get('error', 'unknown')}")
    if fs.task_pending(final):
        return {"status": "pending", "task": final,
                "note": f"still running after {timeout:g}s; poll with fbx_fs_task"}
    return {"status": "done", "task": final if final is not None else submitted}


def _fs_move(client: Any, files: list, dst: str, mode: str = "overwrite",
             wait: bool = True, timeout: float = 60.0) -> dict:
    return _finish_fs_task(client, fs.move(client, files, dst, mode=mode), wait, timeout)


def _fs_copy(client: Any, files: list, dst: str, mode: str = "overwrite",
             wait: bool = True, timeout: float = 60.0) -> dict:
    return _finish_fs_task(client, fs.copy(client, files, dst, mode=mode), wait, timeout)


def _fs_remove(client: Any, files: list, wait: bool = True, timeout: float = 60.0) -> dict:
    return _finish_fs_task(client, fs.remove(client, files), wait, timeout)


def _finish_disk_task(client: Any, submitted: Any, wait: bool, timeout: float) -> dict:
    task_id = (submitted or {}).get("id") if isinstance(submitted, dict) else None
    if not wait or task_id is None:
        return {"status": "submitted", "task": submitted}
    final = vm.poll_disk_task(client, task_id, timeout=timeout)
    if vm.task_failed(final):
        raise FbxError(f"disk task {task_id} failed")
    if vm.task_pending(final):
        return {"status": "pending", "task": final,
                "note": f"still running after {timeout:g}s; poll with fbx_vm_disk_task"}
    return {"status": "done", "task": final if final is not None else submitted}


def _vm_disk_create(client: Any, disk_path: str, size: int, disk_type: str = "qcow2",
                    wait: bool = True, timeout: float = 120.0) -> dict:
    return _finish_disk_task(
        client, vm.disk_create(client, disk_path, size, disk_type=disk_type), wait, timeout
    )


def _vm_disk_resize(client: Any, disk_path: str, size: int, shrink_allow: bool = False,
                    wait: bool = True, timeout: float = 120.0) -> dict:
    return _finish_disk_task(
        client, vm.disk_resize(client, disk_path, size, shrink_allow=shrink_allow), wait, timeout
    )


# -- shared param fragments ---------------------------------------------------

_WAIT = (
    _p("wait", "boolean", "Wait for the box-side task to finish (default true).",
       required=False),
    _p("timeout", "number", "Seconds to wait before reporting the task as pending.",
       required=False),
)

_FS_OP = (
    _p("files", "array", "Absolute box paths (e.g. /Freebox/…) to operate on.",
       items="string"),
    _p("dst", "string", "Destination directory (absolute box path)."),
    _p("mode", "string", "On name conflict.", required=False,
       enum=("overwrite", "both", "recent", "skip")),
) + _WAIT


# -- the table ---------------------------------------------------------------

TOOLS: tuple[ToolSpec, ...] = (
    # ── system ────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_system_info", "system", system.info,
        "Box hardware/firmware info: model, firmware version, uptime, temperatures, fans.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_system_standby_status", "system", system.standby_status,
        "Current standby/power state of the box.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_system_reboot", "system", system.reboot,
        "Reboot the Freebox. DISRUPTIVE: drops every LAN/WAN connection, Wi-Fi and "
        "running VMs for ~2 minutes. Confirm with the user first.",
        destructive=True,
    ),
    ToolSpec(
        "fbx_system_shutdown", "system", system.shutdown,
        "Power the Freebox OFF. It stays off until physically powered back on — "
        "this cuts the network AND any remote access for good. Confirm with the user first.",
        destructive=True,
    ),
    ToolSpec(
        "fbx_system_standby_set", "system", system.set_standby,
        "Configure planned standby (fields is the standby config object to merge).",
        params=(_fields("Standby config fields to set."),),
    ),
    # ── connection ────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_connection_status", "connection", connection.status,
        "WAN status: state, public IPv4/IPv6, media, current up/down rates.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_connection_config", "connection", connection.config,
        "WAN configuration (ping response, remote access, wol, adblock…).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_connection_ipv6_config", "connection", connection.ipv6_config,
        "IPv6 configuration and delegated prefixes.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_connection_logs", "connection", connection.logs,
        "WAN connection up/down history.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_connection_ftth", "connection", connection.ftth,
        "Optical link health: SFP module, RX/TX power. (FTTH boxes only.)",
        readonly=True,
    ),
    ToolSpec(
        "fbx_connection_config_set", "connection", connection.set_config,
        "Update WAN configuration. Read fbx_connection_config first, send only the "
        "fields to change (partial update).",
        params=(_fields("Connection config fields to change."),),
    ),
    ToolSpec(
        "fbx_connection_ipv6_config_set", "connection", connection.set_ipv6_config,
        "Update the IPv6 configuration (partial update of the ipv6 config object).",
        params=(_fields("IPv6 config fields to change."),),
    ),
    # ── lan ───────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_lan_config", "lan", lan.config,
        "LAN configuration: box IP, network mode, DNS name.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_lan_interfaces", "lan", lan.interfaces,
        "Browsable LAN interfaces (pub, wifiguest, …) with host counts.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_lan_devices", "lan", lan.devices,
        "Devices on a LAN interface: names, MACs, IPs, reachability, host type. "
        "Host ids look like `ether-xx:xx:…` and are per-interface.",
        params=(_p("interface", "string", "Interface name (default `pub`, the main LAN).",
                   required=False),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_lan_wake", "lan", lan.wake,
        "Send a Wake-on-LAN magic packet to a MAC on a LAN interface.",
        params=(
            _p("mac", "string", "Target MAC address."),
            _p("interface", "string", "Interface (default `pub`).", required=False),
            _p("password", "string", "WoL password, if the NIC needs one.", required=False),
        ),
    ),
    ToolSpec(
        "fbx_lan_host_set", "lan", lan.update_host,
        "Update a LAN host's entry — e.g. rename it (`primary_name`) or set "
        "`persistent`. Get host ids from fbx_lan_devices.",
        params=(
            _p("host_id", "string", "Host id, e.g. `ether-02:00:00:00:00:0a`."),
            _fields("Host fields to change (e.g. {\"primary_name\": \"TV\"})."),
            _p("interface", "string", "Interface (default `pub`).", required=False),
        ),
    ),
    ToolSpec(
        "fbx_lan_config_set", "lan", lan.set_config,
        "Update the LAN configuration (partial update). Changing the box IP will "
        "renumber the LAN — confirm with the user first.",
        params=(_fields("LAN config fields to change."),),
        destructive=True,
    ),
    # ── dhcp ──────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_dhcp_config", "dhcp", dhcp.config,
        "DHCP server configuration: enabled, IP range, DNS servers, sticky assign.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_dhcp_leases", "dhcp", dhcp.dynamic_leases,
        "Current dynamic DHCP leases.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_dhcp_static_leases", "dhcp", dhcp.static_leases,
        "Static DHCP reservations. Lease ids are the MAC address.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_dhcp_static_add", "dhcp", dhcp.create_static_lease,
        "Reserve a fixed IP for a MAC address.",
        params=(
            _p("mac", "string", "Device MAC address."),
            _p("ip", "string", "IPv4 to assign (inside the LAN subnet)."),
            _p("comment", "string", "Optional note.", required=False),
        ),
    ),
    ToolSpec(
        "fbx_dhcp_static_set", "dhcp", dhcp.update_static_lease,
        "Update a static lease (change IP or comment).",
        params=(
            _p("lease_id", "string", "Lease id (the MAC, as listed)."),
            _fields("Lease fields to change (e.g. {\"ip\": \"192.168.1.50\"})."),
        ),
    ),
    ToolSpec(
        "fbx_dhcp_static_rm", "dhcp", dhcp.delete_static_lease,
        "Delete a static DHCP reservation.",
        params=(_p("lease_id", "string", "Lease id (the MAC, as listed)."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_dhcp_config_set", "dhcp", dhcp.set_config,
        "Update DHCP server config (partial update — e.g. {\"dns\": [\"1.1.1.1\"]}). "
        "Wrong DNS/range settings can break the whole LAN — read the config first.",
        params=(_fields("DHCP config fields to change."),),
    ),
    # ── fw (port forwarding / DMZ / UPnP) ─────────────────────────────────
    ToolSpec(
        "fbx_fw_redirs", "fw", fw.redirs,
        "Port-forwarding rules (redirections).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fw_dmz", "fw", fw.dmz,
        "DMZ configuration (which LAN host receives unmatched inbound traffic).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fw_incoming", "fw", fw.incoming,
        "The box's own built-in services' incoming ports (ftp, http…).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fw_upnp_config", "fw", fw.upnpigd_config,
        "UPnP IGD state (enabled or not).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fw_upnp_redirs", "fw", fw.upnpigd_redirs,
        "Port mappings created by LAN clients via UPnP IGD.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fw_redir_add", "fw", fw.create_redir,
        "Create a port-forwarding rule. fields is the rule object, e.g. "
        "{\"enabled\": true, \"wan_port_start\": 443, \"wan_port_end\": 443, "
        "\"lan_ip\": \"192.168.1.42\", \"lan_port\": 443, \"ip_proto\": \"tcp\", "
        "\"src_ip\": \"0.0.0.0\", \"comment\": \"https\"}. Note: some boxes reject "
        "WAN ports outside an allowed range (`port_outside_range`).",
        params=(_fields("The redirection rule object."),),
    ),
    ToolSpec(
        "fbx_fw_redir_set", "fw", fw.update_redir,
        "Update a port-forwarding rule (partial update; get ids from fbx_fw_redirs).",
        params=(
            _p("redir_id", "string", "Rule id."),
            _fields("Rule fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_fw_redir_rm", "fw", fw.delete_redir,
        "Delete a port-forwarding rule.",
        params=(_p("redir_id", "string", "Rule id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_fw_dmz_set", "fw", fw.set_dmz,
        "Set the DMZ: {\"enabled\": true, \"ip\": \"192.168.1.x\"} exposes that host "
        "to ALL unmatched inbound WAN traffic; {\"enabled\": false} turns it off. "
        "Security-sensitive — confirm with the user first.",
        params=(_fields("DMZ config: enabled + ip."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_fw_incoming_set", "fw", fw.update_incoming,
        "Reconfigure one of the box's own service ports (get ids from fbx_fw_incoming).",
        params=(
            _p("port_id", "string", "Incoming-port id (e.g. `ftp`)."),
            _fields("Fields to change (e.g. {\"enabled\": true, \"in_port\": 2121})."),
        ),
    ),
    ToolSpec(
        "fbx_fw_upnp_config_set", "fw", fw.set_upnpigd_config,
        "Enable/disable UPnP IGD: {\"enabled\": bool}.",
        params=(_fields("UPnP IGD config fields."),),
    ),
    ToolSpec(
        "fbx_fw_upnp_redir_rm", "fw", fw.delete_upnpigd_redir,
        "Delete a UPnP-created port mapping (get ids from fbx_fw_upnp_redirs).",
        params=(_p("redir_id", "string", "UPnP redirection id."),),
        destructive=True,
    ),
    # ── wifi ──────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_wifi_config", "wifi", wifi.config,
        "Global Wi-Fi configuration (enabled, MAC-filter state).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_state", "wifi", wifi.state,
        "Global Wi-Fi runtime state (expected vs actual, e.g. during a planning-off window).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_aps", "wifi", wifi.aps,
        "Radio access points (one per band). AP ids are NOT stable across "
        "firmware/reboots — always list before acting on one.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_bss", "wifi", wifi.bss,
        "BSSes (SSIDs) per radio, with security config. WPA keys appear in this "
        "result — do not echo them back to the user unless asked.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_ap_stations", "wifi", wifi.ap_stations,
        "Clients associated to one AP (signal, rates, cipher).",
        params=(_p("ap_id", "integer", "AP id from fbx_wifi_aps."),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_stations", "wifi", wifi.stations,
        "All associated Wi-Fi clients across every AP (each annotated with its AP "
        "under `_fbx_ap`).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_mac_filters", "wifi", wifi.mac_filters,
        "Wi-Fi MAC access-control entries. Entry ids look like `<mac>-<type>`.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_planning", "wifi", wifi.planning,
        "Wi-Fi on/off weekly planning.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_wps_config", "wifi", wifi.wps_config,
        "WPS global configuration.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_wifi_config_set", "wifi", wifi.set_config,
        "Update global Wi-Fi config. {\"enabled\": false} KILLS ALL Wi-Fi — anyone "
        "(including this machine) on Wi-Fi loses the box. Confirm with the user first.",
        params=(_fields("Wi-Fi config fields to change."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_wifi_ap_set", "wifi", wifi.update_ap,
        "Update one radio's config (channel, width, …). Send only the `config` "
        "subtree fields you mean to change, e.g. {\"primary_channel\": 1}. AP ids "
        "are not stable — get them from fbx_wifi_aps first.",
        params=(
            _p("ap_id", "integer", "AP id from fbx_wifi_aps."),
            _p("config", "object", "AP `config` fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_wifi_bss_set", "wifi", wifi.update_bss,
        "Update a BSS (SSID name, key, encryption…). Most boxes share SSID/key "
        "across all bands (`use_shared_params`), so a change here usually applies "
        "to every band at once.",
        params=(
            _p("bss_id", "string", "BSS id (a MAC-like id from fbx_wifi_bss)."),
            _p("config", "object", "BSS `config` fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_wifi_mac_filter_add", "wifi", wifi.create_mac_filter,
        "Add a Wi-Fi MAC filter entry (whitelist or blacklist). The filter only "
        "applies when the global `mac_filter_state` matches its type.",
        params=(
            _p("mac", "string", "MAC address to filter."),
            _p("type", "string", "Filter type.", enum=("whitelist", "blacklist")),
            _p("comment", "string", "Optional note.", required=False),
        ),
    ),
    ToolSpec(
        "fbx_wifi_mac_filter_set", "wifi", wifi.update_mac_filter,
        "Update a MAC filter entry. Ids are `<mac>-<type>`, from fbx_wifi_mac_filters.",
        params=(
            _p("filter_id", "string", "Filter id (`<mac>-<type>`)."),
            _fields("Filter fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_wifi_mac_filter_rm", "wifi", wifi.delete_mac_filter,
        "Delete a MAC filter entry (id `<mac>-<type>`).",
        params=(_p("filter_id", "string", "Filter id (`<mac>-<type>`)."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_wifi_planning_set", "wifi", wifi.set_planning,
        "Update the Wi-Fi weekly planning ({\"use_planning\": bool, \"mapping\": […]}).",
        params=(_fields("Planning fields to change."),),
    ),
    ToolSpec(
        "fbx_wifi_temp_disable", "wifi", wifi.temp_disable,
        "Disable Wi-Fi for `duration` seconds (auto re-enables). `keep` preserves "
        "one band (e.g. `2d4g`). Without `keep` this cuts every Wi-Fi client, "
        "possibly including the machine running this tool — confirm with the user first.",
        params=(
            _p("duration", "integer", "Seconds to keep Wi-Fi off."),
            _p("keep", "string", "Band to leave up (e.g. `2d4g`).", required=False),
        ),
        destructive=True,
    ),
    ToolSpec(
        "fbx_wifi_wps_set", "wifi", wifi.set_wps,
        "Enable/disable WPS globally.",
        params=(_p("enabled", "boolean", "WPS on or off."),),
    ),
    ToolSpec(
        "fbx_wifi_wps_start", "wifi", wifi.wps_start,
        "Start a WPS push-button session on a BSS.",
        params=(_p("bssid", "string", "Target BSSID (from fbx_wifi_bss)."),),
    ),
    ToolSpec(
        "fbx_wifi_wps_stop", "wifi", wifi.wps_stop,
        "Stop the running WPS session.",
    ),
    # ── downloads ─────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_downloads_list", "downloads", downloads.tasks,
        "Download tasks (torrents, HTTP, news) with status and progress.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_downloads_stats", "downloads", downloads.stats,
        "Download manager counters (active, stopped, rates).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_downloads_add_url", "downloads", downloads.add_url,
        "Queue a download from a URL or magnet link (or several via url_list).",
        params=(
            _p("url", "string", "URL or magnet link.", required=False),
            _p("url_list", "array", "Several URLs at once.", required=False, items="string"),
            _p("download_dir", "string", "Target directory (absolute box path).",
               required=False),
            _p("filename", "string", "Override the saved filename.", required=False),
            _p("hash", "string", "Expected content hash.", required=False),
            _p("username", "string", "HTTP auth username.", required=False),
            _p("password", "string", "HTTP auth password.", required=False),
            _p("recursive", "boolean", "Recursive fetch.", required=False),
            _p("archive_password", "string", "Password for a downloaded archive.",
               required=False),
            _p("cookies", "string", "Cookie header to send.", required=False),
        ),
        open_world=True,
    ),
    ToolSpec(
        "fbx_downloads_add_file", "downloads", downloads.add_file,
        "Upload a local .torrent/.nzb file (path on THIS machine) as a new download task.",
        params=(
            _p("file_path", "string", "Local path to the .torrent/.nzb file."),
            _p("download_dir", "string", "Target directory (absolute box path).",
               required=False),
            _p("archive_password", "string", "Password for a downloaded archive.",
               required=False),
        ),
        open_world=True,
    ),
    ToolSpec(
        "fbx_downloads_task_set", "downloads", downloads.update_task,
        "Update a download task: pause ({\"status\": \"stopped\"}), resume "
        "({\"status\": \"downloading\"}), or set {\"io_priority\": \"low|normal|high\"}.",
        params=(
            _p("task_id", "integer", "Download task id."),
            _fields("Task fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_downloads_task_rm", "downloads", downloads.delete_task,
        "Remove a download task but KEEP its downloaded files.",
        params=(_p("task_id", "integer", "Download task id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_downloads_task_erase", "downloads", downloads.erase_task,
        "Remove a download task AND DELETE its downloaded files. Confirm with the "
        "user first.",
        params=(_p("task_id", "integer", "Download task id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_downloads_throttle_set", "downloads", downloads.set_throttling,
        "Set the download manager throttling mode (e.g. `normal`, `slow`, `hibernate`, "
        "`schedule`).",
        params=(_p("mode", "string", "Throttling mode."),),
    ),
    ToolSpec(
        "fbx_downloads_file_priority_set", "downloads", downloads.set_file_priority,
        "Set one file's priority inside a task (`no_dl`, `low`, `normal`, `high`).",
        params=(
            _p("task_id", "integer", "Download task id."),
            _p("file_id", "string", "File id within the task."),
            _p("priority", "string", "Priority level."),
        ),
    ),
    # ── files (fs + shares) ───────────────────────────────────────────────
    ToolSpec(
        "fbx_fs_ls", "files", fs.ls,
        "List a directory on the box's storage. Paths are plain absolute strings "
        "(e.g. `/Freebox/Téléchargements`); fbx handles the API's base64 encoding.",
        params=(_p("path", "string", "Directory to list (default `/`).", required=False),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_fs_tasks", "files", fs.tasks,
        "File-operation tasks (mv/cp/rm run as tasks on the box).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fs_task", "files", fs.task,
        "One file-operation task's state/progress.",
        params=(_p("task_id", "integer", "Task id."),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_fs_mkdir", "files", fs.mkdir,
        "Create a directory.",
        params=(
            _p("parent", "string", "Parent directory (absolute box path)."),
            _p("dirname", "string", "New directory name."),
        ),
    ),
    ToolSpec(
        "fbx_fs_rename", "files", fs.rename,
        "Rename a file/directory in place (same parent directory).",
        params=(
            _p("src", "string", "Current absolute box path."),
            _p("dst", "string", "New NAME only (not a path)."),
        ),
    ),
    ToolSpec(
        "fbx_fs_move", "files", _fs_move,
        "Move files/directories into a destination directory (box-side task; waits "
        "for completion by default). `overwrite` mode replaces conflicting targets.",
        params=_FS_OP,
        destructive=True,
    ),
    ToolSpec(
        "fbx_fs_copy", "files", _fs_copy,
        "Copy files/directories into a destination directory (box-side task; waits "
        "for completion by default).",
        params=_FS_OP,
    ),
    ToolSpec(
        "fbx_fs_remove", "files", _fs_remove,
        "DELETE files/directories recursively and permanently — there is no trash. "
        "Confirm with the user first.",
        params=(
            _p("files", "array", "Absolute box paths to delete.", items="string"),
        ) + _WAIT,
        destructive=True,
    ),
    ToolSpec(
        "fbx_fs_task_rm", "files", fs.delete_task,
        "Cancel/clear a file-operation task.",
        params=(_p("task_id", "integer", "Task id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_fs_shares", "files", share.list_links,
        "Public share links currently active on the box.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_fs_share_add", "files", share.create,
        "Create a public share link for a box path. Anyone with the link can "
        "download the file — confirm with the user first.",
        params=(
            _p("path", "string", "File/dir to share (absolute box path)."),
            _p("expire", "integer",
               "Expiry as a unix timestamp (0 = never).", required=False),
            _p("fullurl", "string", "Optional URL template.", required=False),
        ),
        destructive=True,
    ),
    ToolSpec(
        "fbx_fs_share_rm", "files", share.delete,
        "Revoke a public share link.",
        params=(_p("token", "string", "Share-link token (from fbx_fs_shares)."),),
        destructive=True,
    ),
    # ── calls ─────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_calls_list", "calls", calls.log,
        "Landline call log (missed/accepted/outgoing).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_calls_mark_read", "calls", calls.mark_read,
        "Mark one call log entry as read.",
        params=(_p("call_id", "integer", "Call entry id."),),
    ),
    ToolSpec(
        "fbx_calls_mark_all_read", "calls", calls.mark_all_read,
        "Mark every call log entry as read.",
    ),
    ToolSpec(
        "fbx_calls_rm", "calls", calls.delete_entry,
        "Delete one call log entry (permanent).",
        params=(_p("call_id", "integer", "Call entry id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_calls_clear", "calls", calls.delete_all,
        "Delete the ENTIRE call log (permanent). Confirm with the user first.",
        destructive=True,
    ),
    # ── contacts ──────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_contacts_list", "contacts", contacts.list_all,
        "The box's address book.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_contacts_add", "contacts", contacts.create,
        "Create a contact. fields is the contact object, e.g. {\"display_name\": "
        "\"Sandy Kilo\", \"first_name\": \"Sandy\", \"last_name\": \"Kilo\"}.",
        params=(_fields("The contact object."),),
    ),
    ToolSpec(
        "fbx_contacts_set", "contacts", contacts.update,
        "Update a contact (partial).",
        params=(
            _p("contact_id", "integer", "Contact id."),
            _fields("Contact fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_contacts_rm", "contacts", contacts.delete,
        "Delete a contact (permanent).",
        params=(_p("contact_id", "integer", "Contact id."),),
        destructive=True,
    ),
    # ── storage ───────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_storage_disks", "storage", storage.disks,
        "Physical disks attached to the box (model, temp, state).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_storage_partitions", "storage", storage.partitions,
        "Partitions and space usage.",
        readonly=True,
    ),
    # ── vm ────────────────────────────────────────────────────────────────
    ToolSpec(
        "fbx_vm_list", "vm", vm.list_vms,
        "Every configured VM with status and full config. VM ids come from here — "
        "never assume them.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_vm_get", "vm", vm.get,
        "One VM's config/status.",
        params=(_p("vm_id", "integer", "VM id from fbx_vm_list."),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_vm_info", "vm", vm.info,
        "Hypervisor capacity: total/used vCPUs and memory.",
        readonly=True,
    ),
    ToolSpec(
        "fbx_vm_distros", "vm", vm.distros,
        "Free's catalog of installable cloud images (name, os, image URL).",
        readonly=True,
    ),
    ToolSpec(
        "fbx_vm_create", "vm", vm.create,
        "Create a VM. config is the VM object: {\"name\": …, \"vcpus\": 1, "
        "\"memory\": 512, \"disk_path\": \"/Freebox/VMs/x.qcow2\", \"disk_type\": "
        "\"qcow2\", \"os\": …, optional cloudinit fields}. Paths are plain absolute "
        "strings; fbx base64-encodes them. Create the disk first (fbx_vm_disk_create).",
        params=(_p("config", "object", "The VM config object."),),
    ),
    ToolSpec(
        "fbx_vm_set", "vm", vm.update,
        "Update a VM's config (partial; most fields need the VM stopped).",
        params=(
            _p("vm_id", "integer", "VM id."),
            _fields("VM config fields to change."),
        ),
    ),
    ToolSpec(
        "fbx_vm_rm", "vm", vm.delete,
        "Delete a VM definition. Its disk file survives — remove it separately via "
        "fbx_fs_remove, along with the UEFI-vars file next to it "
        "(`<disk>.qcow2.efivars`). Confirm with the user first.",
        params=(_p("vm_id", "integer", "VM id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_start", "vm", vm.start,
        "Power a VM on.",
        params=(_p("vm_id", "integer", "VM id."),),
    ),
    ToolSpec(
        "fbx_vm_stop", "vm", vm.stop,
        "HARD power-off (no guest shutdown; like pulling the plug). Prefer "
        "fbx_vm_shutdown. Confirm with the user first.",
        params=(_p("vm_id", "integer", "VM id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_shutdown", "vm", vm.powerbutton,
        "Graceful ACPI shutdown (presses the virtual power button; the guest OS "
        "shuts itself down).",
        params=(_p("vm_id", "integer", "VM id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_restart", "vm", vm.restart,
        "Restart a VM (interrupts whatever it is doing).",
        params=(_p("vm_id", "integer", "VM id."),),
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_exec", "vm", vmconsole.run_command,
        "Run ONE command line on a VM's serial console and return the raw tty "
        "output (echoed command + output + next prompt; no exit code). Needs a "
        "shell on the guest's serial tty (e.g. autologin getty on ttyAMA0). "
        "Collection ends after `quiet_timeout` seconds of console silence. This "
        "is shell access to the guest — confirm state-changing commands with the "
        "user first.",
        params=(
            _p("vm_id", "integer", "VM id."),
            _p("command", "string", "Command line to send."),
            _p("quiet_timeout", "number",
               "Silence (s) that ends collection (default 2).", required=False),
            _p("timeout", "number", "Overall deadline in seconds (default 30).",
               required=False),
        ),
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_disk_info", "vm", vm.disk_info,
        "Inspect a virtual disk image (actual/virtual size).",
        params=(_p("disk_path", "string", "Disk image path (absolute, /Freebox/…).",),),
    ),
    ToolSpec(
        "fbx_vm_disk_create", "vm", _vm_disk_create,
        "Create a virtual disk image (box-side task; waits by default).",
        params=(
            _p("disk_path", "string", "New disk path (absolute, /Freebox/…)."),
            _p("size", "integer", "Size in BYTES."),
            _p("disk_type", "string", "Image format.", required=False,
               enum=("qcow2", "raw")),
        ) + _WAIT,
    ),
    ToolSpec(
        "fbx_vm_disk_resize", "vm", _vm_disk_resize,
        "Resize a virtual disk image (box-side task; waits by default). Shrinking "
        "destroys data beyond the new size — confirm with the user first.",
        params=(
            _p("disk_path", "string", "Disk path (absolute, /Freebox/…)."),
            _p("size", "integer", "New size in BYTES."),
            _p("shrink_allow", "boolean", "Allow shrinking (data loss!).",
               required=False),
        ) + _WAIT,
        destructive=True,
    ),
    ToolSpec(
        "fbx_vm_disk_task", "vm", vm.disk_task,
        "One disk task's progress ({done, error} booleans).",
        params=(_p("task_id", "integer", "Disk task id."),),
        readonly=True,
    ),
    ToolSpec(
        "fbx_vm_disk_task_rm", "vm", vm.delete_disk_task,
        "Cancel/clear a disk task.",
        params=(_p("task_id", "integer", "Disk task id."),),
        destructive=True,
    ),
    # ── raw (the escape hatch) ────────────────────────────────────────────
    ToolSpec(
        "fbx_api_request", "raw", _api_request,
        "Raw authenticated call to any Freebox API endpoint — the escape hatch for "
        "operations that don't have a dedicated tool yet. Paths are relative to the "
        "API base (a pasted `/api/v16/` prefix is stripped). The on-box reference "
        "is at http://mafreebox.freebox.fr/doc. Writes through this tool bypass "
        "every typed schema — double-check method+path+body against the docs, and "
        "treat any POST/PUT/DELETE as needing user confirmation.",
        params=(
            _p("method", "string", "HTTP method.", enum=("GET", "POST", "PUT", "DELETE")),
            _p("path", "string", "Endpoint path, e.g. `system/` or `vm/1/start`."),
            _p("data", "object", "JSON request body (POST/PUT).", required=False),
            _p("params", "object", "Query-string parameters.", required=False),
        ),
        # It can send any write the box accepts, so the hint reflects the
        # worst case (a GET through it is still fine).
        destructive=True,
    ),
)

TOOLSETS: tuple[str, ...] = tuple(
    sorted({spec.toolset for spec in TOOLS})
)


def by_name() -> dict[str, ToolSpec]:
    return {spec.name: spec for spec in TOOLS}


def select(
    *,
    toolsets: set[str] | None = None,
    read_only: bool = False,
    exclude: set[str] | None = None,
) -> list[ToolSpec]:
    """The tool surface after the operator's filters.

    `toolsets` limits to named groups (None = all); `read_only` drops every
    mutating tool; `exclude` drops individual tools or whole toolsets by name.
    """
    out = []
    for spec in TOOLS:
        if toolsets is not None and spec.toolset not in toolsets:
            continue
        if read_only and not spec.readonly:
            continue
        if exclude and (spec.name in exclude or spec.toolset in exclude):
            continue
        out.append(spec)
    return out
