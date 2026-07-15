"""The VM details pane and the v (VNC) key. All data fictional.

The disk_info fixture shape (`type`/`actual_size`/`virtual_size`) comes from
the box's own API docs; a live capture is impossible — the box refuses
vm/disk/info while the disk is attached to a running VM (verified live), so
the pane only asks for stopped VMs.
"""

from __future__ import annotations

import pytest
import respx
from textual.widgets import Static

from fbx.core import fspath
from fbx.tui.app import FbxApp
from tests.helpers import authorize, mock_get, mock_write
from tests.test_tui import _mock_dashboard_box, _settle
from tests.test_tui_screens import _open


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mock_vm_screen():
    """Mock the vm screen's whole read surface; returns the disk_info route."""
    mock_get("vm/info/", {"total_memory": 2048, "used_memory": 512,
                          "total_cpus": 2, "used_cpus": 1})
    mock_get(
        "vm/",
        [
            # Stored relative (no leading /) — the box does both forms.
            {"id": 1, "name": "vm-one", "status": "running", "os": "alpine",
             "vcpus": 1, "memory": 384, "disk_type": "qcow2",
             "disk_path": fspath.encode("Freebox/VMs/one.qcow2")[0:],
             "cd_path": "", "mac": "02:00:00:00:00:01", "enable_screen": False,
             "enable_cloudinit": True, "cloudinit_hostname": "one"},
            {"id": 2, "name": "vm-two", "status": "stopped", "os": "debian",
             "vcpus": 2, "memory": 1024, "disk_type": "qcow2",
             "disk_path": fspath.encode("/Freebox/VMs/two.qcow2"),
             "cd_path": "", "mac": "02:00:00:00:00:02", "enable_screen": True,
             "enable_cloudinit": False},
        ],
    )
    mock_get(
        f"fs/ls/{fspath.encode('/Freebox/VMs')}",
        [
            {"type": "file", "name": "one.qcow2", "size": 265682944},
            {"type": "file", "name": "two.qcow2", "size": 1073741824},
        ],
        startswith=True,
    )
    return mock_write(
        "POST", "vm/disk/info",
        result={"type": "qcow2", "actual_size": 1073741824, "virtual_size": 5368709120},
    )


def _detail(app: FbxApp) -> str:
    return str(app.screen.query_one("#vm-detail", Static).content)


@pytest.mark.anyio
@respx.mock
async def test_details_follow_the_cursor_and_use_fs_for_running_vms():
    authorize()
    _mock_dashboard_box()
    disk_info = _mock_vm_screen()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        # Row 0 = vm-one (running): disk size from fs, no disk_info call.
        await _settle(pilot, lambda: "02:00:00:00:00:01" in _detail(app))
        text = _detail(app)
        assert "Freebox/VMs/one.qcow2" in text
        assert "265.7 MB" in text  # 265682944 bytes on box, decimal units
        assert "unavailable while running" in text
        assert not disk_info.called

        await pilot.press("down")
        # Row 1 = vm-two (stopped): disk_info allowed, virtual size shown.
        await _settle(pilot, lambda: "02:00:00:00:00:02" in _detail(app))
        await _settle(pilot, lambda: "virtual" in _detail(app) and disk_info.called)
        assert "5" in _detail(app)  # 5368709120 → 5.0 GB-ish

        # The hypervisor banner shows MB counts as memory, not raw bytes.
        banner = str(app.screen.query_one("#vm-info", Static).content)
        assert "GB" in banner or "GiB" in banner


@pytest.mark.anyio
@respx.mock
async def test_vnc_key_opens_freebox_os_or_explains(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    authorize()
    _mock_dashboard_box()
    _mock_vm_screen()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        # vm-one: screen off — explains instead of opening.
        await pilot.press("v")
        await pilot.pause(0.1)
        assert opened == []

        await pilot.press("down")
        await pilot.press("v")
        await _settle(pilot, lambda: bool(opened))
        assert opened == ["http://mafreebox.freebox.fr/#Fbx.os.app.vm.app"]
