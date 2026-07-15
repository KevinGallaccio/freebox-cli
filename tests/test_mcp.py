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

# Core functions exposed through a registry wait-wrapper rather than directly.
_VIA_WRAPPER = {
    fs.move, fs.copy, fs.remove,          # _fs_move/_fs_copy/_fs_remove
    vm.disk_create, vm.disk_resize,       # _vm_disk_create/_vm_disk_resize
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
    assert first == "client", f"{spec.name}: first param of {spec.fn} must be client"
    fn_params.pop("client")

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
    assert len(select()) == len(TOOLS) == 107


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
    # No stored credential (isolated store): the tool must NOT trigger pairing.
    rt = FbxRuntime()
    with pytest.raises(FbxMcpToolError, match="fbx auth login"):
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
            assert len(listed.tools) == 107
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
