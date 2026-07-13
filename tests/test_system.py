"""`fbx system` — standby read + reboot/shutdown/standby writes."""

from __future__ import annotations

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

STANDBY = {
    "use_planning": False,
    "planning_mode": "wifi_off",
    "available_planning_modes": ["wifi_off", "suspend"],
    "next_change": 0,
}


@respx.mock
def test_standby_status_table():
    authorize()
    mock_login()
    mock_get("standby/status", STANDBY)
    result = runner.invoke(app, ["system", "standby"])
    assert result.exit_code == 0
    assert "wifi_off" in result.stdout


@respx.mock
def test_reboot_confirms_then_posts():
    authorize()
    mock_login()
    route = mock_write("post", "system/reboot/", envelope={"success": True})
    # decline → nothing sent
    declined = runner.invoke(app, ["system", "reboot"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    # --yes bypasses the prompt
    result = runner.invoke(app, ["system", "reboot", "--yes"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_shutdown_confirms():
    authorize()
    mock_login()
    route = mock_write("post", "system/shutdown/", envelope={"success": True})
    declined = runner.invoke(app, ["system", "shutdown"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called


@respx.mock
def test_standby_set_partial():
    authorize()
    mock_login()
    route = mock_write("put", "standby/config", result=STANDBY)
    result = runner.invoke(app, ["system", "standby-set", "--enabled", "--mode", "suspend"])
    assert result.exit_code == 0
    assert sent_json(route) == {"use_planning": True, "planning_mode": "suspend"}


@respx.mock
def test_reboot_needs_settings_permission():
    authorize()
    mock_login(permissions={"settings": False})
    result = runner.invoke(app, ["system", "reboot", "--yes"])
    assert result.exit_code == 4
