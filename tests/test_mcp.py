"""The MCP adapter: registry integrity, filtering, dispatch, and error mapping.

The registry tests are the drift guard: every public `core.api` function must
be exposed (directly or through a wait-wrapper) or explicitly excluded, and
every spec's params must match its function's real signature. The dispatch
tests drive the real MCP protocol over the SDK's in-memory transport against
the respx-mocked box.
"""

from __future__ import annotations

import inspect
import json

import pytest
import respx

from fbx.core import vmconsole
from fbx.core.api import (
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
from fbx.mcp import registry
from fbx.mcp.registry import TOOLS, TOOLSETS, by_name, input_schema, select
from fbx.mcp.runtime import FbxMcpToolError, FbxRuntime
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

# -- registry completeness ---------------------------------------------------

_API_MODULES = (
    calls, connection, contacts, dhcp, downloads, fs, fw, lan, share, storage,
    system, vm, wifi,
)

# Core functions exposed through a registry wrapper rather than directly
# (wait-polling, secrets redaction, or size filtering).
_VIA_WRAPPER = {
    fs.move, fs.copy, fs.remove,          # _fs_move/_fs_copy/_fs_remove
    vm.disk_create, vm.disk_resize,       # _vm_disk_create/_vm_disk_resize
    vm.list_vms, vm.get,                  # _vm_list/_vm_get (userdata redaction)
    wifi.bss,                             # _wifi_bss (key redaction)
    lan.devices,                          # _lan_devices (reachable-only default)
}

# Pure helpers / pollers — not box operations, so never tools themselves.
_NOT_TOOLS = {
    fs.entries, fs.poll_task, fs.task_failed, fs.task_pending,
    vm.poll_disk_task, vm.task_failed, vm.task_pending,
}


def _public_api_functions() -> set:
    out = set()
    for mod in _API_MODULES:
        for name, obj in vars(mod).items():
            if inspect.isfunction(obj) and not name.startswith("_") \
                    and obj.__module__ == mod.__name__:
                out.add(obj)
    return out


def test_every_core_api_function_is_exposed_or_excluded():
    direct = {spec.fn for spec in TOOLS}
    missing = _public_api_functions() - direct - _VIA_WRAPPER - _NOT_TOOLS
    assert not missing, (
        "core.api functions with no MCP tool (add a ToolSpec or an explicit "
        f"exclusion): {sorted(f.__qualname__ for f in missing)}"
    )


def test_wrapper_covered_functions_are_really_wrapped():
    # The wait-wrappers must keep calling the functions they claim to cover.
    src = inspect.getsource(registry)
    for fn in _VIA_WRAPPER:
        assert f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}(" in src


def test_vm_exec_is_exposed():
    assert by_name()["fbx_vm_exec"].fn is vmconsole.run_command


# -- spec ↔ signature consistency ---------------------------------------------


@pytest.mark.parametrize("spec", TOOLS, ids=lambda s: s.name)
def test_spec_params_match_function_signature(spec):
    sig = inspect.signature(spec.fn)
    fn_params = dict(sig.parameters)
    first = next(iter(fn_params))
    # Regular tools receive the box client; pre-pairing tools the runtime.
    expected = "client" if spec.requires_client else "rt"
    assert first == expected, f"{spec.name}: first param of {spec.fn} must be {expected}"
    fn_params.pop(expected)

    spec_names = {p.name for p in spec.params}
    # Every spec param exists on the function (dispatch is fn(client, **args)).
    unknown = spec_names - set(fn_params)
    assert not unknown, f"{spec.name}: params not in {spec.fn.__qualname__}: {unknown}"
    # Every required function param is a required spec param.
    for name, p in fn_params.items():
        if p.default is inspect.Parameter.empty and p.kind not in (
            inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD
        ):
            match = [sp for sp in spec.params if sp.name == name]
            assert match and match[0].required, (
                f"{spec.name}: {spec.fn.__qualname__} requires `{name}` but the "
                "spec doesn't"
            )


def test_tool_names_are_unique_and_conventional():
    names = [s.name for s in TOOLS]
    assert len(names) == len(set(names))
    for s in TOOLS:
        assert s.name.startswith("fbx_"), s.name
        assert s.toolset in TOOLSETS
        if s.readonly:
            assert not s.destructive, f"{s.name}: readonly can't be destructive"


def test_confirm_language_implies_destructive_annotation():
    # The description and the destructiveHint annotation must never disagree:
    # an agent that trusts the structured hint would skip the confirmation the
    # prose asks for.
    for s in TOOLS:
        if "confirm" in s.description.lower():
            assert s.destructive, (
                f"{s.name}: description asks for confirmation but the spec "
                "isn't destructive=True"
            )


def test_input_schema_shape():
    schema = input_schema(by_name()["fbx_dhcp_static_add"])
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"mac", "ip"}
    assert schema["properties"]["comment"]["type"] == "string"
    filt = input_schema(by_name()["fbx_wifi_mac_filter_add"])
    assert filt["properties"]["type"]["enum"] == ["whitelist", "blacklist"]
    noargs = input_schema(by_name()["fbx_system_info"])
    assert noargs["properties"] == {} and "required" not in noargs


# -- operator filtering --------------------------------------------------------


def test_select_read_only_drops_every_write():
    specs = select(read_only=True)
    assert specs and all(s.readonly for s in specs)
    assert "fbx_api_request" not in {s.name for s in specs}  # raw is a write


def test_select_toolsets_and_exclude():
    vm_only = {s.toolset for s in select(toolsets={"vm"})}
    assert vm_only == {"vm"}
    names = {s.name for s in select(exclude={"raw", "fbx_system_reboot"})}
    assert "fbx_api_request" not in names
    assert "fbx_system_reboot" not in names
    assert "fbx_system_info" in names


def test_default_surface_is_everything():
    assert len(select()) == len(TOOLS) == 111


# -- secrets redaction + size filtering ----------------------------------------


_BSS_FIXTURE = [{
    "id": "02:00:00:00:00:10",
    "config": {"ssid": "net-a", "key": "hunter2", "encryption": "wpa2_psk_ccmp"},
    "bss_params": {"ssid": "net-a", "key": "hunter2"},
    "shared_bss_params": {"ssid": "net-a", "key": "hunter2"},
}]


@respx.mock
def test_vm_userdata_is_redacted_by_default_and_raw_on_request():
    authorize()
    mock_login()
    mock_get("vm/", [{"id": 0, "name": "vm-a", "cloudinit_userdata": "password: s3cret"}])
    rt = FbxRuntime()
    try:
        masked = rt.call(by_name()["fbx_vm_list"], {})
        raw = rt.call(by_name()["fbx_vm_list"], {"include_secrets": True})
    finally:
        rt.close()
    assert "s3cret" not in json.dumps(masked)
    assert "redacted by fbx" in masked[0]["cloudinit_userdata"]
    assert "fbx vm userdata" in masked[0]["cloudinit_userdata"]  # the recovery hint
    assert raw[0]["cloudinit_userdata"] == "password: s3cret"


@respx.mock
def test_vm_get_redacts_userdata_too():
    authorize()
    mock_login()
    mock_get("vm/0", {"id": 0, "name": "vm-a", "cloudinit_userdata": "password: s3cret"})
    rt = FbxRuntime()
    try:
        masked = rt.call(by_name()["fbx_vm_get"], {"vm_id": 0})
    finally:
        rt.close()
    assert "s3cret" not in json.dumps(masked)


@respx.mock
def test_wifi_keys_masked_at_every_level():
    authorize()
    mock_login()
    mock_get("wifi/bss/", _BSS_FIXTURE)
    rt = FbxRuntime()
    try:
        masked = rt.call(by_name()["fbx_wifi_bss"], {})
        raw = rt.call(by_name()["fbx_wifi_bss"], {"include_secrets": True})
    finally:
        rt.close()
    dumped = json.dumps(masked)
    assert "hunter2" not in dumped
    for field in ("config", "bss_params", "shared_bss_params"):
        assert "redacted by fbx" in masked[0][field]["key"]
    assert masked[0]["config"]["ssid"] == "net-a"  # only the key is touched
    assert raw[0]["bss_params"]["key"] == "hunter2"


@respx.mock
def test_lan_devices_defaults_to_reachable_only():
    authorize()
    mock_login()
    mock_get("lan/browser/pub/", [
        {"id": "ether-02:00:00:00:00:01", "active": True},
        {"id": "ether-02:00:00:00:00:02", "active": False},
    ])
    rt = FbxRuntime()
    try:
        reachable = rt.call(by_name()["fbx_lan_devices"], {})
        everything = rt.call(by_name()["fbx_lan_devices"], {"all": True})
    finally:
        rt.close()
    assert [h["id"] for h in reachable] == ["ether-02:00:00:00:00:01"]
    assert len(everything) == 2


@respx.mock
def test_wifi_neighbors_tools_hit_the_survey_endpoints():
    authorize()
    mock_login()
    mock_get("wifi/ap/10/neighbors/", [{"bssid": "02:00:00:00:00:aa", "channel": 6}])
    scan_route = mock_write("post", "wifi/ap/10/neighbors/scan", envelope={"success": True})
    rt = FbxRuntime()
    try:
        seen = rt.call(by_name()["fbx_wifi_neighbors"], {"ap_id": 10})
        rt.call(by_name()["fbx_wifi_neighbors_scan"], {"ap_id": 10})
    finally:
        rt.close()
    assert seen[0]["channel"] == 6
    assert scan_route.called


# -- runtime dispatch + error mapping (respx-mocked box) ------------------------


@respx.mock
def test_runtime_read_dispatch():
    authorize()
    mock_login()
    mock_get("system/", {"firmware_version": "4.12.2"})
    rt = FbxRuntime()
    try:
        result = rt.call(by_name()["fbx_system_info"], {})
    finally:
        rt.close()
    assert result == {"firmware_version": "4.12.2"}


@respx.mock
def test_runtime_write_sends_the_documented_body():
    authorize()
    mock_login()
    route = mock_write("post", "dhcp/static_lease/", {"id": "02:00:00:00:00:99"})
    rt = FbxRuntime()
    try:
        rt.call(
            by_name()["fbx_dhcp_static_add"],
            {"mac": "02:00:00:00:00:99", "ip": "192.168.1.222", "comment": "printer"},
        )
    finally:
        rt.close()
    assert sent_json(route) == {
        "mac": "02:00:00:00:00:99", "ip": "192.168.1.222", "comment": "printer"
    }


@respx.mock
def test_runtime_raw_api_request_strips_doc_prefix():
    authorize()
    mock_login()
    mock_get("system/", {"ok": True})
    rt = FbxRuntime()
    try:
        result = rt.call(
            by_name()["fbx_api_request"],
            {"method": "GET", "path": "/api/v16/system/"},
        )
    finally:
        rt.close()
    assert result == {"ok": True}


def test_runtime_not_authenticated_says_how_to_pair():
    # No stored credential (isolated store): the tool must NOT trigger pairing,
    # and the message must name both pairing paths (terminal + guided tool).
    rt = FbxRuntime()
    with pytest.raises(FbxMcpToolError, match="fbx auth login"):
        rt.call(by_name()["fbx_system_info"], {})
    with pytest.raises(FbxMcpToolError, match="fbx_auth_enroll"):
        rt.call(by_name()["fbx_system_info"], {})
    rt.close()


@respx.mock
def test_runtime_missing_permission_names_the_scope():
    authorize()
    mock_login(permissions={"vm": False})
    rt = FbxRuntime()
    try:
        with pytest.raises(FbxMcpToolError, match="`vm` permission"):
            rt.call(by_name()["fbx_vm_start"], {"vm_id": 1})
    finally:
        rt.close()


@respx.mock
def test_runtime_fs_wait_wrapper_polls_to_done():
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", {"id": 5, "state": "running"})
    mock_get("fs/tasks/5", {"id": 5, "state": "done", "error": "none"})
    rt = FbxRuntime()
    try:
        result = rt.call(by_name()["fbx_fs_remove"], {"files": ["/Freebox/old"]})
    finally:
        rt.close()
    assert result["status"] == "done"
    assert result["task"]["state"] == "done"


@respx.mock
def test_runtime_fs_wait_wrapper_raises_on_failed_task():
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", {"id": 5, "state": "running"})
    mock_get("fs/tasks/5", {"id": 5, "state": "failed", "error": "disk_full"})
    rt = FbxRuntime()
    try:
        with pytest.raises(FbxMcpToolError, match="disk_full"):
            rt.call(by_name()["fbx_fs_remove"], {"files": ["/Freebox/old"]})
    finally:
        rt.close()


# -- guided pairing (mcp.enroll) ------------------------------------------------

_AUTHORIZE_BODY = {"success": True, "result": {"app_token": "NEW_TOKEN", "track_id": 42}}


def _mock_authorize_start() -> respx.Route:
    import httpx as _httpx

    return respx.post(
        "http://mafreebox.freebox.fr/api/v16/login/authorize/"
    ).mock(return_value=_httpx.Response(200, json=_AUTHORIZE_BODY))


def _mock_track(*statuses: str) -> respx.Route:
    import httpx as _httpx

    return respx.get(
        "http://mafreebox.freebox.fr/api/v16/login/authorize/42"
    ).mock(
        side_effect=[
            _httpx.Response(200, json={"success": True, "result": {"status": s}})
            for s in statuses
        ]
    )


@respx.mock
def test_enroll_happy_path_pairs_and_never_leaks_the_token():
    from fbx.core import credentials

    mock_login()  # discovery + the post-grant session check
    _mock_authorize_start()
    _mock_track("pending", "granted")

    rt = FbxRuntime()
    try:
        started = rt.call(by_name()["fbx_auth_enroll"], {})
        assert started["status"] == "pending"
        assert started["track_id"] == 42
        assert "NEW_TOKEN" not in json.dumps(started)
        assert "▶" in started["action_required"]

        waiting = rt.call(
            by_name()["fbx_auth_enroll_status"], {"track_id": 42, "wait_seconds": 0}
        )
        assert waiting["status"] == "pending"

        done = rt.call(
            by_name()["fbx_auth_enroll_status"], {"track_id": 42, "wait_seconds": 0}
        )
    finally:
        rt.close()

    assert done["status"] == "granted"
    assert "NEW_TOKEN" not in json.dumps(done)
    assert done["permissions_granted"]  # the session check ran
    cred = credentials.load()
    assert cred is not None and cred.app_token == "NEW_TOKEN"
    assert cred.box_model == "fbxgw9-r1"  # identity captured at discovery


@respx.mock
def test_enroll_refuses_when_already_paired_unless_replace():
    authorize()
    mock_login()
    _mock_authorize_start()

    rt = FbxRuntime()
    try:
        refused = rt.call(by_name()["fbx_auth_enroll"], {})
        assert refused["status"] == "already_paired"

        replaced = rt.call(by_name()["fbx_auth_enroll"], {"replace": True})
        assert replaced["status"] == "pending"
    finally:
        rt.close()


@respx.mock
def test_enroll_denial_and_timeout_clear_the_pending_state():
    mock_login()
    _mock_authorize_start()
    _mock_track("denied")

    rt = FbxRuntime()
    try:
        rt.call(by_name()["fbx_auth_enroll"], {})
        verdict = rt.call(
            by_name()["fbx_auth_enroll_status"], {"track_id": 42, "wait_seconds": 0}
        )
        assert verdict["status"] == "denied"
        # The pending record is gone: a retry must say so, not poll the box.
        again = rt.call(
            by_name()["fbx_auth_enroll_status"], {"track_id": 42, "wait_seconds": 0}
        )
        assert again["status"] == "unknown_track"
    finally:
        rt.close()


def test_enroll_status_with_no_pending_flow_says_start_over():
    rt = FbxRuntime()
    try:
        result = rt.call(
            by_name()["fbx_auth_enroll_status"], {"track_id": 999, "wait_seconds": 0}
        )
    finally:
        rt.close()
    assert result["status"] == "unknown_track"
    assert "fbx_auth_enroll" in result["note"]


def test_enroll_specs_are_annotated_for_consent():
    enroll_spec = by_name()["fbx_auth_enroll"]
    assert enroll_spec.destructive and not enroll_spec.readonly
    assert not enroll_spec.requires_client
    status_spec = by_name()["fbx_auth_enroll_status"]
    assert not status_spec.requires_client
    # Neither may surface in a read-only server.
    names = {s.name for s in select(read_only=True)}
    assert "fbx_auth_enroll" not in names and "fbx_auth_enroll_status" not in names


# -- the real protocol over the in-memory transport ----------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@respx.mock
async def test_mcp_protocol_list_and_call():
    from mcp.shared.memory import create_connected_server_and_client_session

    from fbx.mcp.server import build_server

    authorize()
    mock_login()
    mock_get("system/", {"firmware_version": "4.12.2", "uptime": "up"})

    rt = FbxRuntime()
    server = build_server(rt, select())
    try:
        async with create_connected_server_and_client_session(server) as session:
            listed = await session.list_tools()
            assert len(listed.tools) == 111
            tools = {t.name: t for t in listed.tools}
            assert tools["fbx_system_info"].annotations.readOnlyHint is True
            assert tools["fbx_system_reboot"].annotations.destructiveHint is True
            assert tools["fbx_fs_ls"].inputSchema["properties"]["path"]["type"] == "string"

            result = await session.call_tool("fbx_system_info", {})
            assert result.isError is False
            payload = json.loads(result.content[0].text)
            assert payload["firmware_version"] == "4.12.2"
    finally:
        rt.close()


@pytest.mark.anyio
@respx.mock
async def test_mcp_protocol_maps_errors_to_tool_errors():
    from mcp.shared.memory import create_connected_server_and_client_session

    from fbx.mcp.server import build_server

    # No credential stored: the call must fail with pairing instructions, and
    # the server must stay alive (protocol error, not a crash).
    rt = FbxRuntime()
    server = build_server(rt, select())
    try:
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool("fbx_system_info", {})
            assert result.isError is True
            assert "fbx auth login" in result.content[0].text
    finally:
        rt.close()


@pytest.mark.anyio
@respx.mock
async def test_mcp_protocol_bodiless_write_returns_success_object():
    from mcp.shared.memory import create_connected_server_and_client_session

    from fbx.mcp.server import build_server

    authorize()
    mock_login()
    mock_write("post", "vm/1/start", envelope={"success": True})

    rt = FbxRuntime()
    server = build_server(rt, select())
    try:
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool("fbx_vm_start", {"vm_id": 1})
            assert result.isError is False
            assert json.loads(result.content[0].text) == {"success": True}
    finally:
        rt.close()


@pytest.mark.anyio
async def test_mcp_read_only_server_hides_writes():
    from mcp.shared.memory import create_connected_server_and_client_session

    from fbx.mcp.server import build_server

    rt = FbxRuntime()
    server = build_server(rt, select(read_only=True))
    try:
        async with create_connected_server_and_client_session(server) as session:
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            assert "fbx_system_info" in names
            assert "fbx_system_reboot" not in names
            assert "fbx_api_request" not in names
            # Calling a hidden tool fails without touching the box.
            result = await session.call_tool("fbx_system_reboot", {})
            assert result.isError is True
    finally:
        rt.close()


# -- plugin manifest ------------------------------------------------------------


def test_plugin_manifest_tracks_the_package():
    from pathlib import Path

    import fbx

    manifest = json.loads(
        (Path(__file__).parent.parent / ".claude-plugin" / "plugin.json").read_text()
    )
    # The plugin version is what /plugin shows users — it must be the package's.
    assert manifest["version"] == fbx.__version__
    # The server must run from the plugin's own copy so plugin updates ARE
    # server updates (a git+/registry spec here would pin uvx to a stale build).
    # The dist is freebox-cli (PyPI prohibits "fbx"); command/tools stay fbx.
    args = manifest["mcpServers"]["fbx"]["args"]
    assert "freebox-cli[mcp] @ file://${CLAUDE_PLUGIN_ROOT}" in args, args
    assert args[-2:] == ["mcp", "serve"]


def test_mcpb_manifest_tracks_the_package():
    import subprocess
    import sys
    from pathlib import Path

    import fbx

    out = subprocess.run(
        [sys.executable, "scripts/build_mcpb.py", "--print-manifest"],
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).parent.parent,
    )
    manifest = json.loads(out.stdout)
    # The bundle must pin the exact release: uv caches resolutions, so an
    # unpinned spec would freeze users on whatever version they installed
    # first (the plugin's v0.5.2 lesson, again).
    assert manifest["version"] == fbx.__version__
    cfg = manifest["server"]["mcp_config"]
    assert cfg["command"] == "uvx"
    assert f"freebox-cli[mcp]=={fbx.__version__}" in cfg["args"]
    assert cfg["args"][-2:] == ["mcp", "serve"]
    # Live-install lessons (Claude Desktop, 2026-07-16) — each of these broke
    # a real install/chat attempt before being pinned here:
    assert manifest["manifest_version"] == "0.2"  # newest shape the app's validators accept
    assert manifest["server"]["entry_point"]  # required by every embedded schema version
    display = manifest["display_name"]
    assert display.isascii() and " " not in display  # fancy names get dropped chat-side


def test_marketplace_entry_tracks_the_package():
    from pathlib import Path

    import fbx

    marketplace = json.loads(
        (Path(__file__).parent.parent / ".claude-plugin" / "marketplace.json").read_text()
    )
    # Installers watch the marketplace for changes; without a version stamp the
    # file is byte-identical across releases and caches never refresh (the
    # Desktop "stuck at an old version" failure).
    (entry,) = marketplace["plugins"]
    assert entry["version"] == fbx.__version__


# -- CLI surface ----------------------------------------------------------------


def test_cli_mcp_tools_lists_and_filters():
    from typer.testing import CliRunner

    from fbx.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--json", "mcp", "tools", "--toolsets", "vm"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert {t["toolset"] for t in data} == {"vm"}

    bad = runner.invoke(app, ["mcp", "tools", "--toolsets", "nope"])
    assert bad.exit_code == 1


def test_cli_mcp_install_json_shape():
    from typer.testing import CliRunner

    from fbx.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--json", "mcp", "install"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["command"][-2:] == ["mcp", "serve"]
    assert "claude mcp add fbx" in data["claude_code"]
