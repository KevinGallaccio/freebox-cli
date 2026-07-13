"""`fbx vm` — VM lifecycle, disk ops, and the serial-console URL builder."""

from __future__ import annotations

import json
import tempfile

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from fbx.core import fspath
from fbx.core.vmconsole import serial_console_url, vnc_url
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

# Real box convention: VM disk_path is base64 of a RELATIVE path (no leading
# slash), e.g. "Freebox/VMs/plexi.qcow2" — verified live, distinct from fs paths.
def _vm_disk(rel: str) -> str:
    import base64

    return base64.b64encode(rel.encode()).decode()


VMS = [
    {
        "id": 0, "name": "Plexi", "status": "running", "os": "debian",
        "vcpus": 1, "memory": 1536, "disk_type": "qcow2",
        "disk_path": _vm_disk("Freebox/VMs/Plexi.qcow2"),
        "cd_path": "", "mac": "02:00:00:00:00:09", "enable_screen": False,
        "enable_cloudinit": True, "cloudinit_hostname": "plexi",
        "cloudinit_userdata": "#cloud-config\nssh_authorized_keys:\n  - ssh-ed25519 AAAA...secret",
    },
    {
        "id": 1, "name": "pihole", "status": "stopped", "os": "debian",
        "vcpus": 1, "memory": 256, "disk_type": "qcow2",
        "disk_path": _vm_disk("Freebox/VMs/pihole.qcow2"),
    },
]

INFO = {
    "total_cpus": 2, "used_cpus": 1, "total_memory": 2048, "used_memory": 1536,
    "usb_used": False, "usb_ports": ["usb-external-type-a"], "sata_ports": {},
}

DISTROS = [
    {"name": "Debian 12 (Bookworm)", "os": "debian",
     "url": "http://ftp.free.fr/.../debian-12-arm64.qcow2", "hash": "http://.../SHA512SUMS"},
]


# -- console URL builder (pure) --------------------------------------------


def test_serial_console_url_maps_http_to_ws():
    assert serial_console_url("http://mafreebox.freebox.fr/api/v16/", 2) == (
        "ws://mafreebox.freebox.fr/api/v16/vm/2/console"
    )


def test_serial_console_url_maps_https_to_wss_and_adds_slash():
    assert serial_console_url("https://x.fbxos.fr/api/v16", 3) == (
        "wss://x.fbxos.fr/api/v16/vm/3/console"
    )


def test_vnc_url_targets_the_vnc_endpoint():
    assert vnc_url("http://mafreebox.freebox.fr/api/v16/", 2) == (
        "ws://mafreebox.freebox.fr/api/v16/vm/2/vnc"
    )


# -- reads -----------------------------------------------------------------


@respx.mock
def test_list_table_and_json():
    authorize()
    mock_login()
    mock_get("vm/", VMS)
    table = runner.invoke(app, ["vm", "list"])
    assert table.exit_code == 0
    assert "Plexi" in table.stdout and "pihole" in table.stdout
    js = runner.invoke(app, ["--json", "vm", "list"])
    assert json.loads(js.stdout) == VMS  # whole object, incl. cloudinit_userdata


@respx.mock
def test_show_hides_cloudinit_userdata_in_table_but_json_keeps_it():
    authorize()
    mock_login()
    mock_get("vm/0", VMS[0])
    table = runner.invoke(app, ["vm", "show", "0"])
    assert table.exit_code == 0
    assert "secret" not in table.stdout  # userdata (SSH keys/passwords) never in a table
    assert "hidden" in table.stdout
    assert "Freebox/VMs/Plexi.qcow2" in table.stdout  # relative disk path decoded for display
    mock_get("vm/0", VMS[0])
    js = runner.invoke(app, ["--json", "vm", "show", "0"])
    assert "secret" in js.stdout  # --json is the whole object


@respx.mock
def test_info_shows_free_headroom():
    authorize()
    mock_login()
    mock_get("vm/info/", INFO)
    result = runner.invoke(app, ["vm", "info"])
    assert result.exit_code == 0
    assert "1 free" in result.stdout  # 2 total - 1 used vCPU
    assert "512 MB free" in result.stdout


@respx.mock
def test_distros_table():
    authorize()
    mock_login()
    mock_get("vm/distros/", DISTROS)
    result = runner.invoke(app, ["vm", "distros"])
    assert result.exit_code == 0
    assert "Debian 12 (Bookworm)" in result.stdout


# -- lifecycle writes ------------------------------------------------------


@respx.mock
def test_create_encodes_disk_path():
    authorize()
    mock_login()
    route = mock_write("post", "vm/", result={"id": 2, "name": "fbx-test"})
    result = runner.invoke(
        app,
        ["vm", "create", "--name", "fbx-test", "--disk", "/Freebox/VMs/test.qcow2",
         "--memory", "256", "--vcpus", "1"],
    )
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["disk_path"] == fspath.encode("/Freebox/VMs/test.qcow2")
    assert body["memory"] == 256
    assert body["name"] == "fbx-test"


@respx.mock
def test_create_reads_cloudinit_file():
    authorize()
    mock_login()
    route = mock_write("post", "vm/", result={"id": 2})
    fd = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    fd.write("#cloud-config\npackages: [adguardhome]\n")
    fd.close()
    result = runner.invoke(
        app,
        ["vm", "create", "--name", "x", "--disk", "/Freebox/x.qcow2", "--memory", "256",
         "--cloudinit-file", fd.name],
    )
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["enable_cloudinit"] is True
    assert "adguardhome" in body["cloudinit_userdata"]


@respx.mock
def test_set_partial_encodes_disk():
    authorize()
    mock_login()
    route = mock_write("put", "vm/2", result={"id": 2})
    result = runner.invoke(app, ["vm", "set", "2", "--memory", "512"])
    assert result.exit_code == 0
    assert sent_json(route) == {"memory": 512}


@respx.mock
def test_start_no_confirm():
    authorize()
    mock_login()
    route = mock_write("post", "vm/2/start", envelope={"success": True})
    result = runner.invoke(app, ["vm", "start", "2"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_stop_confirms_hard_off():
    authorize()
    mock_login()
    route = mock_write("post", "vm/2/stop", envelope={"success": True})
    declined = runner.invoke(app, ["vm", "stop", "2"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    ok = runner.invoke(app, ["vm", "stop", "2", "--yes"])
    assert ok.exit_code == 0
    assert route.called


@respx.mock
def test_shutdown_is_graceful_no_confirm():
    authorize()
    mock_login()
    route = mock_write("post", "vm/2/powerbutton", envelope={"success": True})
    result = runner.invoke(app, ["vm", "shutdown", "2"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_rm_confirms():
    authorize()
    mock_login()
    route = mock_write("delete", "vm/2", envelope={"success": True})
    declined = runner.invoke(app, ["vm", "rm", "2"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    ok = runner.invoke(app, ["vm", "rm", "2", "--yes"])
    assert ok.exit_code == 0
    assert route.called


# -- disk management -------------------------------------------------------


@respx.mock
def test_disk_create_parses_size_encodes_path_and_polls():
    authorize()
    mock_login()
    # Disk tasks use boolean done/error (verified live), NOT fs-style state.
    route = mock_write("post", "vm/disk/create", result={"id": 9, "type": "create", "done": False})
    mock_get("vm/disk/task/9", {"id": 9, "type": "create", "error": False, "done": True})
    result = runner.invoke(app, ["vm", "disk-create", "/Freebox/VMs/test.qcow2", "2G"])
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["disk_path"] == fspath.encode("/Freebox/VMs/test.qcow2")
    assert body["size"] == 2 * 1024**3  # 2G parsed to bytes
    assert body["disk_type"] == "qcow2"


@respx.mock
def test_disk_resize_shrink_confirms_and_flags():
    authorize()
    mock_login()
    done = {"id": 10, "type": "resize", "error": False, "done": True}
    route = mock_write("post", "vm/disk/resize", result=done)
    mock_get("vm/disk/task/10", done)
    declined = runner.invoke(app, ["vm", "disk-resize", "/Freebox/x.qcow2", "1G", "--shrink"],
                             input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    ok = runner.invoke(app, ["vm", "disk-resize", "/Freebox/x.qcow2", "1G", "--shrink", "--yes"])
    assert ok.exit_code == 0
    assert sent_json(route)["shrink_allow"] is True


@respx.mock
def test_disk_create_failed_task_exits_1():
    authorize()
    mock_login()
    mock_write("post", "vm/disk/create", result={"id": 11, "type": "create", "done": False})
    mock_get("vm/disk/task/11", {"id": 11, "type": "create", "error": True, "done": True})
    result = runner.invoke(app, ["vm", "disk-create", "/Freebox/x.qcow2", "9999G"])
    assert result.exit_code == 1


@respx.mock
def test_vm_write_needs_vm_permission():
    authorize()
    mock_login(permissions={"vm": False})
    result = runner.invoke(app, ["vm", "start", "2"])
    assert result.exit_code == 4  # EXIT_PERMISSION


def test_bad_size_exits_1():
    authorize()
    mock_login()
    result = runner.invoke(app, ["vm", "disk-create", "/Freebox/x.qcow2", "notasize"])
    assert result.exit_code == 1
