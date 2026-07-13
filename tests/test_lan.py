"""`fbx lan` — device browser, interfaces, config against captured shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

ACTIVE_HOST = {
    "l2ident": {"id": "02:00:00:00:00:0a", "type": "mac_address"},
    "active": True,
    "persistent": True,
    "names": [{"name": "host-20", "source": "dhcp"}],
    "vendor_name": "ACME Corp.",
    "host_type": "other",
    "id": "ether-02:00:00:00:00:0a",
    "interface": "pub",
    "default_name": "host-20",
    "primary_name": "host-22",
    "primary_name_manual": True,
    "first_activity": 1719762509,
    "last_activity": 1783941970,
    "last_time_reachable": 1783941970,
    "reachable": True,
    "l3connectivities": [
        {
            "addr": "192.168.1.75",
            "af": "ipv4",
            "active": True,
            "reachable": True,
            "last_activity": 1783941970,
        }
    ],
    "access_point": {
        "connectivity_type": "wifi",
        "mac": "02:00:00:00:00:04",
        "wifi_information": {"band": "2d4g", "ssid": "scrubbed-ssid-1", "signal": -34},
    },
}

INACTIVE_HOST = {
    "l2ident": {"id": "02:00:00:00:00:0b", "type": "mac_address"},
    "active": False,
    "persistent": False,
    "host_type": "workstation",
    "id": "ether-02:00:00:00:00:0b",
    "primary_name": "host-99",
    "reachable": False,
    "l3connectivities": [
        {"addr": "192.168.1.141", "af": "ipv4", "active": False, "reachable": False}
    ],
}

INTERFACES = [{"name": "pub", "host_count": 127}, {"name": "wifiguest", "host_count": 0}]

CONFIG = {
    "name_dns": "freebox-server",
    "name": "Freebox Server",
    "name_mdns": "Freebox-Server",
    "mode": "router",
    "name_netbios": "host-3",
    "ip": "192.168.1.254",
}


@respx.mock
def test_devices_json_is_whole_host_list():
    authorize()
    mock_login()
    mock_get("lan/browser/pub/", [ACTIVE_HOST, INACTIVE_HOST])
    result = runner.invoke(app, ["--json", "lan", "devices"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [ACTIVE_HOST, INACTIVE_HOST]  # JSON is never filtered


@respx.mock
def test_devices_table_hides_inactive_by_default():
    authorize()
    mock_login()
    mock_get("lan/browser/pub/", [ACTIVE_HOST, INACTIVE_HOST])
    result = runner.invoke(app, ["lan", "devices"])
    assert result.exit_code == 0
    assert "host-22" in result.stdout
    assert "192.168.1.75" in result.stdout
    assert "host-99" not in result.stdout
    assert "1 inactive hidden" in result.stdout


@respx.mock
def test_devices_all_includes_inactive():
    authorize()
    mock_login()
    mock_get("lan/browser/pub/", [ACTIVE_HOST, INACTIVE_HOST])
    result = runner.invoke(app, ["lan", "devices", "--all"])
    assert result.exit_code == 0
    assert "host-99" in result.stdout


@respx.mock
def test_devices_honors_interface_option():
    authorize()
    mock_login()
    route = mock_get("lan/browser/wifiguest/", [])
    result = runner.invoke(app, ["--json", "lan", "devices", "-i", "wifiguest"])
    assert result.exit_code == 0
    assert route.called
    assert json.loads(result.stdout) == []


@respx.mock
def test_device_names_are_never_parsed_as_markup():
    # Hostnames are set by the devices themselves (DHCP/mDNS) — hostile input.
    # Unescaped, "evil[/]" crashes Rich and "[red]x" spoofs table styling.
    authorize()
    mock_login()
    hostile = dict(ACTIVE_HOST, primary_name="evil[/]name")
    hostile2 = dict(ACTIVE_HOST, id="ether-x", primary_name="[red]x")
    mock_get("lan/browser/pub/", [hostile, hostile2])
    result = runner.invoke(app, ["lan", "devices"])
    assert result.exit_code == 0
    assert "evil[/]name" in result.stdout  # rendered literally, not as markup
    assert "[red]x" in result.stdout


@respx.mock
def test_interfaces_table():
    authorize()
    mock_login()
    mock_get("lan/browser/interfaces/", INTERFACES)
    result = runner.invoke(app, ["lan", "interfaces"])
    assert result.exit_code == 0
    assert "pub" in result.stdout
    assert "127" in result.stdout


@respx.mock
def test_config_table_shows_mode():
    authorize()
    mock_login()
    mock_get("lan/config/", CONFIG)
    result = runner.invoke(app, ["lan", "config"])
    assert result.exit_code == 0
    assert "router" in result.stdout
    assert "192.168.1.254" in result.stdout


# -- writes ----------------------------------------------------------------


@respx.mock
def test_wol_posts_mac_and_password():
    authorize()
    mock_login()
    route = mock_write("post", "lan/wol/pub/", envelope={"success": True})
    result = runner.invoke(app, ["wol", "02:00:00:00:00:0a"])
    assert result.exit_code == 0
    assert sent_json(route) == {"mac": "02:00:00:00:00:0a", "password": ""}


@respx.mock
def test_wol_honors_interface_option():
    authorize()
    mock_login()
    route = mock_write("post", "lan/wol/eth0/", envelope={"success": True})
    result = runner.invoke(app, ["wol", "02:00:00:00:00:0a", "-i", "eth0"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_rename_puts_primary_name_with_echoed_id():
    authorize()
    mock_login()
    route = mock_write("put", "lan/browser/pub/", startswith=True, result={"ok": True})
    result = runner.invoke(
        app, ["lan", "rename", "ether-02:00:00:00:00:0a", "Living Room TV"]
    )
    assert result.exit_code == 0
    assert sent_json(route) == {
        "id": "ether-02:00:00:00:00:0a",
        "primary_name": "Living Room TV",
    }


@respx.mock
def test_set_type_puts_host_type():
    authorize()
    mock_login()
    route = mock_write("put", "lan/browser/pub/", startswith=True, result={"ok": True})
    result = runner.invoke(
        app, ["lan", "set-type", "ether-02:00:00:00:00:0a", "workstation"]
    )
    assert result.exit_code == 0
    assert sent_json(route)["host_type"] == "workstation"


@respx.mock
def test_lan_config_set_sends_only_changed_fields():
    authorize()
    mock_login()
    route = mock_write("put", "lan/config/", result={"mode": "router"})
    result = runner.invoke(app, ["lan", "config-set", "--name", "Home Box"])
    assert result.exit_code == 0
    assert sent_json(route) == {"name": "Home Box"}
