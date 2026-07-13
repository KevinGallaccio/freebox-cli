"""`fbx connection` — status, config, ipv6, logs, ftth against captured shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

STATUS = {
    "type": "ethernet",
    "rate_down": 150150,
    "bytes_up": 4415893546,
    "ipv4_port_range": [16384, 32767],
    "rate_up": 7842,
    "bandwidth_up": 8000000000,
    "ipv6": "2001:db8::1",
    "bandwidth_down": 8000000000,
    "media": "ftth",
    "state": "up",
    "bytes_down": 50282834883,
    "ipv4": "203.0.113.1",
}

CONFIG = {
    "remote_access": False,
    "api_remote_access": True,
    "api_domain": "fake-1.fbxos.fr",
    "https_port": 34567,
    "https_available": True,
    "wol": False,
    "ping": True,
    "adblock": False,
    "sip_alg": "direct_media",
    "disable_guest": False,
}

IPV6 = {
    "ipv6_enabled": True,
    "ipv6ll": "fe80::1",
    "ipv6_firewall": False,
    "ipv6_prefix_firewall": False,
    "delegations": [
        {"prefix": "2001:db8:0:1::/64", "next_hop": ""},
        {"prefix": "2001:db8:0:2::/64", "next_hop": ""},
    ],
}

LOGS = [
    {
        "state": "up",
        "type": "link",
        "bw_down": 8000000000,
        "link": "ftth",
        "id": 1,
        "bw_up": 8000000000,
        "date": 1783860748,
    },
    {"conn": "ftth_pub", "type": "conn", "id": 3, "state": "up", "date": 1783860753},
]

FTTH = {
    "link": True,
    "link_type": "pon",
    "has_sfp": True,
    "sfp_present": True,
    "sfp_alim_ok": True,
    "sfp_model": "SFP-X1",
    "sfp_vendor": "ACME",
    "sfp_serial": "scrubbed-serial-1",
    "sfp_pwr_rx": -1838,
    "sfp_pwr_tx": 642,
    "sfp_has_power_report": True,
    "sfp_has_signal": True,
}


@respx.mock
def test_status_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("connection/", STATUS)
    result = runner.invoke(app, ["--json", "connection", "status"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == STATUS


@respx.mock
def test_status_table_shows_state_and_addresses():
    authorize()
    mock_login()
    mock_get("connection/", STATUS)
    result = runner.invoke(app, ["connection", "status"])
    assert result.exit_code == 0
    assert "up" in result.stdout
    assert "ftth" in result.stdout
    assert "203.0.113.1" in result.stdout


@respx.mock
def test_config_table_shows_remote_access():
    authorize()
    mock_login()
    mock_get("connection/config/", CONFIG)
    result = runner.invoke(app, ["connection", "config"])
    assert result.exit_code == 0
    assert "fake-1.fbxos.fr" in result.stdout
    assert "direct_media" in result.stdout


@respx.mock
def test_ipv6_table_lists_delegations():
    authorize()
    mock_login()
    mock_get("connection/ipv6/config/", IPV6)
    result = runner.invoke(app, ["connection", "ipv6"])
    assert result.exit_code == 0
    assert "2001:db8:0:1::/64" in result.stdout
    assert "2001:db8:0:2::/64" in result.stdout


@respx.mock
def test_logs_table_and_json():
    authorize()
    mock_login()
    mock_get("connection/logs/", LOGS)
    result = runner.invoke(app, ["--json", "connection", "logs"])
    assert json.loads(result.stdout) == LOGS
    result = runner.invoke(app, ["connection", "logs"])
    assert result.exit_code == 0
    assert "link" in result.stdout
    assert "ftth_pub" in result.stdout


@respx.mock
def test_ftth_table_scales_optical_power_to_dbm():
    authorize()
    mock_login()
    mock_get("connection/ftth/", FTTH)
    result = runner.invoke(app, ["connection", "ftth"])
    assert result.exit_code == 0
    # sfp_pwr_* are hundredths of a dBm: -1838 → -18.38 dBm
    assert "-18.38 dBm" in result.stdout
    assert "6.42 dBm" in result.stdout
    assert "ACME" in result.stdout


@respx.mock
def test_dict_command_survives_missing_result():
    # Bare {"success": true} with no `result` → emit falls back to JSON null;
    # the table renderer must never see None (it would crash on .get()).
    authorize()
    mock_login()
    mock_get("connection/config/", envelope={"success": True})
    result = runner.invoke(app, ["connection", "config"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) is None


# -- writes ----------------------------------------------------------------


@respx.mock
def test_config_set_partial_body():
    authorize()
    mock_login()
    route = mock_write("put", "connection/config/", result={"ping": True})
    result = runner.invoke(app, ["connection", "config-set", "--ping", "--no-wol"])
    assert result.exit_code == 0
    assert sent_json(route) == {"ping": True, "wol": False}


@respx.mock
def test_config_set_needs_an_option():
    authorize()
    mock_login()
    result = runner.invoke(app, ["connection", "config-set"])
    assert result.exit_code == 1


@respx.mock
def test_ipv6_set_maps_flags():
    authorize()
    mock_login()
    route = mock_write("put", "connection/ipv6/config/", result={"ipv6_enabled": True})
    result = runner.invoke(app, ["connection", "ipv6-set", "--enabled", "--no-firewall"])
    assert result.exit_code == 0
    assert sent_json(route) == {"ipv6_enabled": True, "ipv6_firewall": False}
