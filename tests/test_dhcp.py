"""`fbx dhcp` — leases, static reservations, config against captured shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

LEASES = [
    {
        "mac": "02:00:00:00:00:05",
        "ip": "192.168.1.6",
        "hostname": "host-10",
        "assign_time": 1783897654,
        "refresh_time": 1783940855,
        "lease_remaining": 40408,
        "is_static": False,
        "host": {"id": "ether-02:00:00:00:00:05", "active": True},
    },
    {
        "mac": "02:00:00:00:00:01",
        "ip": "192.168.1.24",
        "hostname": "host-7",
        "assign_time": 1783897000,
        "refresh_time": 1783940000,
        "lease_remaining": 0,
        "is_static": True,
        "host": {"id": "ether-02:00:00:00:00:01", "active": True},
    },
]

STATIC = [
    {
        "id": "02:00:00:00:00:01",
        "mac": "02:00:00:00:00:01",
        "hostname": "host-7",
        "ip": "192.168.1.24",
        "comment": "pinned",
        "options": {},
        "host": {"id": "ether-02:00:00:00:00:01", "active": False},
    }
]

CONFIG = {
    "enabled": True,
    "sticky_assign": True,
    "netmask": "255.255.255.0",
    "ip_range_start": "192.168.1.2",
    "ip_range_end": "192.168.1.200",
    "gateway": "192.168.1.254",
    "dns": ["192.168.1.24", "", "", "", "", ""],
    "always_broadcast": False,
    "options": {},
}


@respx.mock
def test_leases_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("dhcp/dynamic_lease/", LEASES)
    result = runner.invoke(app, ["--json", "dhcp", "leases"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == LEASES


@respx.mock
def test_leases_table_shows_remaining_duration():
    authorize()
    mock_login()
    mock_get("dhcp/dynamic_lease/", LEASES)
    result = runner.invoke(app, ["dhcp", "leases"])
    assert result.exit_code == 0
    assert "host-10" in result.stdout
    assert "192.168.1.6" in result.stdout
    assert "11h 13m" in result.stdout  # lease_remaining 40408s


@respx.mock
def test_empty_leases_normalize_to_empty_list():
    authorize()
    mock_login()
    # The box omits `result` entirely for an empty collection.
    mock_get("dhcp/dynamic_lease/", envelope={"success": True})
    result = runner.invoke(app, ["--json", "dhcp", "leases"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


@respx.mock
def test_static_table_shows_reservation():
    authorize()
    mock_login()
    mock_get("dhcp/static_lease/", STATIC)
    result = runner.invoke(app, ["dhcp", "static"])
    assert result.exit_code == 0
    assert "host-7" in result.stdout
    assert "192.168.1.24" in result.stdout
    assert "pinned" in result.stdout


@respx.mock
def test_config_table_shows_range_and_dns():
    authorize()
    mock_login()
    mock_get("dhcp/config/", CONFIG)
    result = runner.invoke(app, ["dhcp", "config"])
    assert result.exit_code == 0
    assert "192.168.1.2" in result.stdout
    assert "192.168.1.200" in result.stdout
    assert "192.168.1.24" in result.stdout  # empty DNS slots dropped, real one kept


# -- writes ----------------------------------------------------------------


@respx.mock
def test_static_add_posts_mac_and_ip():
    authorize()
    mock_login()
    route = mock_write(
        "post",
        "dhcp/static_lease/",
        result={"id": "02:00:00:00:00:99", "mac": "02:00:00:00:00:99", "ip": "192.168.1.222"},
    )
    result = runner.invoke(
        app, ["--json", "dhcp", "static-add", "02:00:00:00:00:99", "192.168.1.222"]
    )
    assert result.exit_code == 0
    assert sent_json(route) == {"mac": "02:00:00:00:00:99", "ip": "192.168.1.222"}


@respx.mock
def test_static_add_includes_comment_when_given():
    authorize()
    mock_login()
    route = mock_write("post", "dhcp/static_lease/", result={"id": "02:00:00:00:00:99"})
    result = runner.invoke(
        app, ["dhcp", "static-add", "02:00:00:00:00:99", "192.168.1.222", "-c", "printer"]
    )
    assert result.exit_code == 0
    assert sent_json(route)["comment"] == "printer"


@respx.mock
def test_static_edit_puts_only_changed_fields():
    authorize()
    mock_login()
    route = mock_write("put", "dhcp/static_lease/", startswith=True, result={"ok": True})
    result = runner.invoke(app, ["dhcp", "static-edit", "02:00:00:00:00:99", "--comment", "x"])
    assert result.exit_code == 0
    assert sent_json(route) == {"comment": "x"}


@respx.mock
def test_static_edit_requires_a_field():
    authorize()
    mock_login()
    result = runner.invoke(app, ["dhcp", "static-edit", "02:00:00:00:00:99"])
    assert result.exit_code == 1


@respx.mock
def test_static_rm_deletes():
    authorize()
    mock_login()
    route = mock_write("delete", "dhcp/static_lease/", startswith=True, envelope={"success": True})
    result = runner.invoke(app, ["--json", "dhcp", "static-rm", "02:00:00:00:00:99"])
    assert result.exit_code == 0
    assert route.called
    # a bodiless mutation still emits a truthy object on stdout
    assert json.loads(result.stdout) == {"success": True}


@respx.mock
def test_config_set_sends_partial_body_with_disabled():
    authorize()
    mock_login()
    route = mock_write("put", "dhcp/config/", result={"enabled": False})
    result = runner.invoke(app, ["dhcp", "config-set", "--disabled", "--gateway", "192.168.1.254"])
    assert result.exit_code == 0
    assert sent_json(route) == {"enabled": False, "gateway": "192.168.1.254"}


@respx.mock
def test_config_set_dns_is_repeatable_list():
    authorize()
    mock_login()
    route = mock_write("put", "dhcp/config/", result={})
    result = runner.invoke(
        app, ["dhcp", "config-set", "--dns", "1.1.1.1", "--dns", "9.9.9.9"]
    )
    assert result.exit_code == 0
    assert sent_json(route) == {"dns": ["1.1.1.1", "9.9.9.9"]}


@respx.mock
def test_write_without_settings_permission_exits_4():
    authorize()
    mock_login(permissions={"settings": False})
    result = runner.invoke(app, ["dhcp", "static-rm", "02:00:00:00:00:99"])
    assert result.exit_code == 4  # EXIT_PERMISSION
