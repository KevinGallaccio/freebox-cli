"""Domain screens: each screen's key write action, asserted at the wire.

Every test drives the real app with keys, fills the real modals, and asserts
the REQUEST the box received — the same write contract as the CLI suite.
"""

from __future__ import annotations

import pytest
import respx
from textual.widgets import DataTable, Input, Static

from fbx.core import fspath
from fbx.tui.app import FbxApp
from fbx.tui.widgets import ConfirmModal, FormModal
from tests.helpers import mock_get, mock_write, sent_form, sent_json
from tests.test_tui import _mock_dashboard_box, _settle, authorize


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _open(pilot, app: FbxApp, domain: str, table_id: str | None = None):
    """From the mounted dashboard, open a domain screen and wait for its data."""
    await _settle(pilot, lambda: "tile-connection" in str(app.screen.query("#tile-connection")))
    app.open_domain(domain)
    if table_id:
        await _settle(
            pilot,
            lambda: bool(app.screen.query(f"#{table_id}"))
            and app.screen.query_one(f"#{table_id}", DataTable).row_count > 0,
        )


async def _fill_form(pilot, app: FbxApp, values: dict[str, str]) -> None:
    await _settle(pilot, lambda: isinstance(app.screen, FormModal))
    for key, value in values.items():
        app.screen.query_one(f"#field-{key}", Input).value = value
    await pilot.press("enter")


async def _confirm_yes(pilot, app: FbxApp) -> None:
    await _settle(pilot, lambda: isinstance(app.screen, ConfirmModal))
    await pilot.press("y")


@pytest.mark.anyio
@respx.mock
async def test_lan_rename_sends_primary_name():
    authorize()
    _mock_dashboard_box()
    # Hosts sort unnamed-first, so the cursor lands on the nameless device —
    # exactly the one a user would label.
    route = mock_write("PUT", "lan/browser/pub/ether-02:00:00:00:00:0b/")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "lan", "hosts")
        await pilot.press("n")
        await _fill_form(pilot, app, {"name": "Living Room TV"})
        await _settle(pilot, lambda: route.called)
        # core's update_host echoes the id into the body (same as the CLI).
        assert sent_json(route) == {
            "id": "ether-02:00:00:00:00:0b",
            "primary_name": "Living Room TV",
        }


@pytest.mark.anyio
@respx.mock
async def test_dhcp_reserves_an_ip():
    authorize()
    _mock_dashboard_box()
    mock_get("dhcp/config/", {"enabled": True, "ip_range_start": "192.0.2.2",
                              "ip_range_end": "192.0.2.50", "dns": ["192.0.2.1"]})
    mock_get("dhcp/static_lease/", [{"id": "02:00:00:00:00:99", "ip": "192.0.2.99",
                                     "mac": "02:00:00:00:00:99"}])
    mock_get("dhcp/dynamic_lease/", [])
    route = mock_write("POST", "dhcp/static_lease/")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "dhcp", "static-leases")
        await pilot.press("a")
        await _fill_form(
            pilot, app,
            {"mac": "02:00:00:00:00:42", "ip": "192.0.2.42", "comment": "printer"},
        )
        await _settle(pilot, lambda: route.called)
        assert sent_json(route) == {
            "mac": "02:00:00:00:00:42", "ip": "192.0.2.42", "comment": "printer",
        }


@pytest.mark.anyio
@respx.mock
async def test_fw_adds_and_toggles_a_rule():
    authorize()
    _mock_dashboard_box()
    mock_get(
        "fw/redir/",
        [{"id": 3, "enabled": True, "ip_proto": "tcp", "wan_port_start": 17000,
          "wan_port_end": 17000, "lan_ip": "192.0.2.9", "lan_port": 80,
          "src_ip": "0.0.0.0", "comment": "web"}],
    )
    added = mock_write("POST", "fw/redir/")
    toggled = mock_write("PUT", "fw/redir/3")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fw", "redirs")
        await pilot.press("a")
        await _fill_form(
            pilot, app,
            {"lan_ip": "192.0.2.9", "lan_port": "8080", "wan_port": "17001",
             "proto": "tcp", "comment": "test"},
        )
        await _settle(pilot, lambda: added.called)
        assert sent_json(added) == {
            "enabled": True, "comment": "test", "lan_ip": "192.0.2.9",
            "lan_port": 8080, "wan_port_start": 17001, "wan_port_end": 17001,
            "ip_proto": "tcp", "src_ip": "0.0.0.0",
        }

        await _settle(pilot, lambda: not isinstance(app.screen, FormModal))
        await pilot.press("t")
        await _settle(pilot, lambda: toggled.called)
        assert sent_json(toggled) == {"enabled": False}


@pytest.mark.anyio
@respx.mock
async def test_downloads_pause_and_erase():
    authorize()
    _mock_dashboard_box()
    paused = mock_write("PUT", "downloads/1")
    erased = mock_write("DELETE", "downloads/1/erase")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "downloads", "tasks")
        # Fixture task is "done" → space resumes it (status downloading).
        await pilot.press("space")
        await _settle(pilot, lambda: paused.called)
        assert sent_json(paused) == {"status": "downloading"}

        await pilot.press("E")
        await _confirm_yes(pilot, app)
        await _settle(pilot, lambda: erased.called)


@pytest.mark.anyio
@respx.mock
async def test_wifi_wps_toggle_and_temp_disable():
    authorize()
    _mock_dashboard_box()
    mock_get("wifi/config/", {"enabled": True, "mac_filter_state": "disabled"})
    wps = mock_write("PUT", "wifi/wps/config/")
    disabled = mock_write("POST", "wifi/temp_disable")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "wifi", "aps")
        # Fixture has WPS enabled → toggle turns it off (the hygiene suggestion).
        await pilot.press("P")
        await _settle(pilot, lambda: wps.called)
        assert sent_json(wps) == {"enabled": False}

        await pilot.press("t")
        await _fill_form(pilot, app, {"minutes": "5", "keep": "2d4g"})
        await _confirm_yes(pilot, app)
        await _settle(pilot, lambda: disabled.called)
        assert sent_json(disabled) == {"duration": 300, "keep": "2d4g"}


@pytest.mark.anyio
@respx.mock
async def test_contacts_add_sends_only_filled_fields():
    authorize()
    _mock_dashboard_box()
    mock_get("contact/", [{"id": 1, "display_name": "Existing"}])
    route = mock_write("POST", "contact/")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "contacts", "contacts")
        await pilot.press("a")
        await _fill_form(pilot, app, {"display_name": "Sandy Kilo", "first_name": "Sandy"})
        await _settle(pilot, lambda: route.called)
        assert sent_json(route) == {"display_name": "Sandy Kilo", "first_name": "Sandy"}


@pytest.mark.anyio
@respx.mock
async def test_calls_clear_log_is_gated():
    authorize()
    _mock_dashboard_box()
    route = mock_write("POST", "call/log/delete_all/")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "calls", "calls")
        await pilot.press("C")
        await _settle(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("n")
        await _settle(pilot, lambda: not isinstance(app.screen, ConfirmModal))
        assert not route.called

        await pilot.press("C")
        await _confirm_yes(pilot, app)
        await _settle(pilot, lambda: route.called)


@pytest.mark.anyio
@respx.mock
async def test_fs_shell_mkdir_and_gated_rm():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", [], startswith=True)
    made = mock_write("POST", "fs/mkdir/")
    removed = mock_write("POST", "fs/rm/", result={"id": 7})
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _settle(pilot, lambda: bool(app.screen.query("#fs-input")))

        app.screen.query_one("#fs-input", Input).value = "mkdir photos"
        await pilot.press("enter")
        await _settle(pilot, lambda: made.called)
        assert sent_json(made) == {"parent": fspath.encode("/"), "dirname": "photos"}

        # The prompt is disabled while a command runs; wait for it back.
        await _settle(pilot, lambda: not app.screen.query_one("#fs-input", Input).disabled)
        app.screen.query_one("#fs-input", Input).value = "rm /Freebox/old"
        await pilot.press("enter")
        await _confirm_yes(pilot, app)
        await _settle(pilot, lambda: removed.called)
        assert sent_json(removed) == {"files": [fspath.encode("/Freebox/old")]}
        text = str(app.screen.query_one("#fs-scrollback", Static).content)
        assert "task 7" in text


@pytest.mark.anyio
@respx.mock
async def test_vm_hard_stop_is_gated():
    authorize()
    _mock_dashboard_box()
    mock_get("vm/info/", {"total_memory": 2048, "used_memory": 1536,
                          "total_cpus": 2, "used_cpus": 2})
    route = mock_write("POST", "vm/0/stop")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        # Cursor starts on the first row: vm 0 (running).
        await pilot.press("K")
        await _confirm_yes(pilot, app)
        await _settle(pilot, lambda: route.called)


@pytest.mark.anyio
@respx.mock
async def test_vm_actions_target_the_visually_selected_row():
    """Regression (review finding): the box's vm listing order is not
    guaranteed id-ascending; rows are displayed sorted, so the row keys must
    come from the SAME sorted sequence or actions hit the wrong VM."""
    authorize()
    _mock_dashboard_box()
    # Out-of-order listing: id 5 first (replaces the dashboard fixture's
    # vm/ route — respx dedupes same-pattern routes). Sorted display puts
    # id 1 on row 0.
    mock_get("vm/info/", {"total_memory": 2048, "used_memory": 512,
                          "total_cpus": 2, "used_cpus": 1})
    mock_get(
        "vm/",
        [{"id": 5, "name": "vm-five", "status": "stopped"},
         {"id": 1, "name": "vm-one", "status": "stopped"}],
    )
    started = mock_write("POST", "vm/1/start")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        # Row 0 shows vm-one (id 1, sorted first) — `s` must start THAT one.
        await pilot.press("s")
        await _settle(pilot, lambda: started.called)


@pytest.mark.anyio
@respx.mock
async def test_downloads_add_url_posts_form():
    authorize()
    _mock_dashboard_box()
    route = mock_write("POST", "downloads/add")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "downloads", "tasks")
        await pilot.press("a")
        await _fill_form(pilot, app, {"url": "magnet:?xt=urn:btih:abc"})
        await _settle(pilot, lambda: route.called)
        assert sent_form(route) == {"download_url": "magnet:?xt=urn:btih:abc"}
