"""`fbx fw` — port forwarding, DMZ, incoming ports, UPnP IGD (reads + writes)."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

REDIRS = [
    {
        "id": 1,
        "enabled": True,
        "comment": "web",
        "lan_port": 8080,
        "wan_port_start": 8080,
        "wan_port_end": 8080,
        "lan_ip": "192.168.1.42",
        "ip_proto": "tcp",
        "src_ip": "0.0.0.0",
        "hostname": "host-5",
    }
]

INCOMING = [
    {
        "id": "http",
        "type": "tcp",
        "enabled": True,
        "active": True,
        "in_port": 21252,
        "min_port": 16384,
        "max_port": 32767,
        "readonly": False,
    }
]

UPNP_REDIRS = [
    {
        "id": "0.0.0.0-26476-tcp",
        "enabled": True,
        "proto": "tcp",
        "desc": "Plex Media Server",
        "ext_port": 26476,
        "int_ip": "192.168.1.49",
        "int_port": 32400,
    }
]


# -- reads -----------------------------------------------------------------


@respx.mock
def test_redirs_empty_normalizes_to_list():
    authorize()
    mock_login()
    mock_get("fw/redir/", envelope={"success": True})  # box omits result when empty
    result = runner.invoke(app, ["--json", "fw", "redirs"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


@respx.mock
def test_redirs_table_shows_mapping():
    authorize()
    mock_login()
    mock_get("fw/redir/", REDIRS)
    result = runner.invoke(app, ["fw", "redirs"])
    assert result.exit_code == 0
    assert "192.168.1.42:8080" in result.stdout
    assert "web" in result.stdout


@respx.mock
def test_dmz_table():
    authorize()
    mock_login()
    mock_get("fw/dmz/", {"enabled": False, "ip": ""})
    result = runner.invoke(app, ["fw", "dmz"])
    assert result.exit_code == 0
    assert "Enabled" in result.stdout


@respx.mock
def test_incoming_table():
    authorize()
    mock_login()
    mock_get("fw/incoming/", INCOMING)
    result = runner.invoke(app, ["fw", "incoming"])
    assert result.exit_code == 0
    assert "http" in result.stdout
    assert "21252" in result.stdout


@respx.mock
def test_upnp_config_table():
    authorize()
    mock_login()
    mock_get("upnpigd/config/", {"enabled": True, "version": 1})
    result = runner.invoke(app, ["fw", "upnp"])
    assert result.exit_code == 0
    assert "Enabled" in result.stdout


@respx.mock
def test_upnp_redirs_table_escapes_desc():
    # `desc` is supplied by the LAN app — treat as hostile markup.
    authorize()
    mock_login()
    hostile = dict(UPNP_REDIRS[0], desc="[red]evil[/]")
    mock_get("upnpigd/redir/", [hostile])
    result = runner.invoke(app, ["fw", "upnp-redirs"])
    assert result.exit_code == 0
    assert "[red]evil[/]" in result.stdout


# -- writes ----------------------------------------------------------------


@respx.mock
def test_redir_add_builds_full_body():
    authorize()
    mock_login()
    route = mock_write("post", "fw/redir/", result={"id": 3})
    result = runner.invoke(
        app,
        ["fw", "redir-add", "192.168.1.42", "8080", "--wan-port", "9090", "--comment", "web"],
    )
    assert result.exit_code == 0
    assert sent_json(route) == {
        "enabled": True,
        "comment": "web",
        "lan_ip": "192.168.1.42",
        "lan_port": 8080,
        "wan_port_start": 9090,
        "wan_port_end": 9090,  # defaults to wan_port when no --wan-port-end
        "ip_proto": "tcp",
        "src_ip": "0.0.0.0",
    }


@respx.mock
def test_redir_add_range_uses_distinct_end():
    authorize()
    mock_login()
    route = mock_write("post", "fw/redir/", result={"id": 4})
    result = runner.invoke(
        app,
        ["fw", "redir-add", "192.168.1.42", "8080",
         "--wan-port", "9000", "--wan-port-end", "9010", "--proto", "udp"],
    )
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["wan_port_start"] == 9000
    assert body["wan_port_end"] == 9010
    assert body["ip_proto"] == "udp"


@respx.mock
def test_redir_edit_partial_body():
    authorize()
    mock_login()
    route = mock_write("put", "fw/redir/", startswith=True, result={"id": 1})
    result = runner.invoke(app, ["fw", "redir-edit", "1", "--disabled"])
    assert result.exit_code == 0
    assert sent_json(route) == {"enabled": False}


@respx.mock
def test_redir_rm():
    authorize()
    mock_login()
    route = mock_write("delete", "fw/redir/", startswith=True, envelope={"success": True})
    result = runner.invoke(app, ["fw", "redir-rm", "3"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_dmz_set_and_off():
    authorize()
    mock_login()
    route = mock_write("put", "fw/dmz/", result={"enabled": True, "ip": "192.168.1.50"})
    result = runner.invoke(app, ["fw", "dmz-set", "192.168.1.50"])
    assert result.exit_code == 0
    assert sent_json(route) == {"enabled": True, "ip": "192.168.1.50"}

    route_off = mock_write("put", "fw/dmz/", result={"enabled": False})
    result = runner.invoke(app, ["fw", "dmz-off"])
    assert result.exit_code == 0
    assert sent_json(route_off) == {"enabled": False}


@respx.mock
def test_incoming_set():
    authorize()
    mock_login()
    route = mock_write("put", "fw/incoming/", startswith=True, result={"id": "http"})
    result = runner.invoke(app, ["fw", "incoming-set", "http", "--in-port", "30000"])
    assert result.exit_code == 0
    assert sent_json(route) == {"in_port": 30000}


@respx.mock
def test_upnp_set():
    authorize()
    mock_login()
    route = mock_write("put", "upnpigd/config/", result={"enabled": False, "version": 1})
    result = runner.invoke(app, ["fw", "upnp-set", "--disabled"])
    assert result.exit_code == 0
    assert sent_json(route) == {"enabled": False}


@respx.mock
def test_upnp_rm():
    authorize()
    mock_login()
    route = mock_write("delete", "upnpigd/redir/", startswith=True, envelope={"success": True})
    result = runner.invoke(app, ["fw", "upnp-rm", "0.0.0.0-26476-tcp"])
    assert result.exit_code == 0
    assert route.called
