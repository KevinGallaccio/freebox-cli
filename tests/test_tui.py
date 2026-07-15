"""The interactive app: dashboard rendering, suggestions, confirm-gated writes.

Drives the real textual app headless (Pilot) against the respx-mocked box —
the same offline contract as the CLI and MCP suites: for writes, assert the
request the app sent, not just what it displayed.
"""

from __future__ import annotations

import re

import pytest
import respx
from textual.widgets import OptionList, Static

from fbx.tui.app import FbxApp
from fbx.tui.suggestions import suggest
from fbx.tui.widgets import ConfirmModal
from tests.helpers import authorize, mock_get, mock_login, mock_write


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mock_dashboard_box() -> None:
    """A small, fully fictional box (TEST-NET addresses, locally-administered MACs)."""
    mock_login()
    mock_get(
        "connection/",
        {"state": "up", "media": "ftth", "ipv4": "192.0.2.1", "rate_down": 1_000_000,
         "rate_up": 250_000},
    )
    mock_get(
        "system/",
        {"firmware_version": "4.12.2", "uptime": "3 days 2 hours",
         "model_info": {"pretty_name": "Freebox v9 (r1)"},
         "sensors": [{"name": "cpu", "value": 58}], "fans": [{"name": "fan0", "value": 2000}]},
    )
    mock_get(
        "wifi/ap/",
        [{"id": 10, "name": "2d4g", "status": {"state": "active", "primary_channel": 1},
          "config": {}}],
    )
    mock_get("wifi/wps/config/", {"enabled": True})
    mock_get(
        "lan/browser/pub/",
        [
            {
                "id": "ether-02:00:00:00:00:0a",
                "active": True,
                "primary_name": "host-a",
                "host_type": "laptop",
                "l2ident": {"id": "02:00:00:00:00:0a", "type": "mac_address"},
                "l3connectivities": [
                    {"addr": "192.0.2.10", "af": "ipv4", "active": True, "reachable": True}
                ],
                "last_activity": 1783944060,
            },
            {
                "id": "ether-02:00:00:00:00:0b",
                "active": True,
                "primary_name": "",
                "l2ident": {"id": "02:00:00:00:00:0b", "type": "mac_address"},
            },
        ],
    )
    mock_get(
        "vm/",
        [{"id": 0, "name": "vm-zero", "status": "running"},
         {"id": 1, "name": "vm-one", "status": "stopped"}],
    )
    mock_get(
        "storage/partition/",
        [{"id": 2, "label": "Disque dur", "used_bytes": 95, "total_bytes": 100}],
    )
    mock_get("downloads/", [{"id": 1, "name": "iso", "status": "done"}])
    mock_get("call/log/", [{"id": 1, "type": "missed", "new": True, "number": "0100000000"}])


async def _settle(pilot, condition, *, tries: int = 60) -> None:
    """Wait for a worker-driven UI condition (box I/O happens off-thread)."""
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition never became true")


def _tile_text(app: FbxApp, name: str) -> str:
    # textual 8: Static.update stores its argument on `.content`.
    return str(app.screen.query_one(f"#tile-{name}", Static).content)


# -- dashboard ----------------------------------------------------------------


@pytest.mark.anyio
@respx.mock
async def test_dashboard_renders_tiles_and_suggestions():
    authorize()
    _mock_dashboard_box()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "up" in _tile_text(app, "connection"))
        assert "ftth" in _tile_text(app, "connection")
        await _settle(pilot, lambda: "4.12.2" in _tile_text(app, "system"))
        # Slow-lane tiles (same first tick).
        await _settle(pilot, lambda: "2d4g" in _tile_text(app, "wifi"))
        assert "ch 1" in _tile_text(app, "wifi")
        assert "2 active" in _tile_text(app, "lan")
        assert "vm-zero" in _tile_text(app, "vm")
        assert "95%" in _tile_text(app, "storage")
        assert "1 new missed" in _tile_text(app, "calls")

        # Suggestions: wps on, stopped VM, done download, full partition,
        # missed call, unnamed device.
        suggestions = app.screen.query_one("#dash-suggestions", OptionList)
        assert suggestions.option_count >= 6


@pytest.mark.anyio
@respx.mock
async def test_dashboard_menu_opens_domain_screen():
    authorize()
    _mock_dashboard_box()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "up" in _tile_text(app, "connection"))
        app.open_domain("system")
        await _settle(
            pilot,
            lambda: bool(app.screen.query("#system-info"))
            and "4.12.2" in str(app.screen.query_one("#system-info", Static).content),
        )
        # Escape returns to the dashboard.
        await pilot.press("escape")
        await _settle(pilot, lambda: bool(app.screen.query("#tile-connection")))


# -- confirm-gated writes -------------------------------------------------------


@pytest.mark.anyio
@respx.mock
async def test_reboot_needs_confirmation_and_posts():
    authorize()
    _mock_dashboard_box()
    reboot = mock_write("POST", "system/reboot/")
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "up" in _tile_text(app, "connection"))
        app.open_domain("system")
        await _settle(pilot, lambda: bool(app.screen.query("#system-info")))

        # Declined → nothing sent.
        await pilot.press("b")
        await _settle(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("n")
        await _settle(pilot, lambda: not isinstance(app.screen, ConfirmModal))
        assert not reboot.called

        # Escape also declines.
        await pilot.press("b")
        await _settle(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("escape")
        await _settle(pilot, lambda: not isinstance(app.screen, ConfirmModal))
        assert not reboot.called

        # Confirmed → the POST goes out.
        await pilot.press("b")
        await _settle(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await _settle(pilot, lambda: reboot.called)


# -- entry points ---------------------------------------------------------------


def test_bare_fbx_without_tty_prints_help_like_before():
    """Piped bare `fbx` keeps the v0.5.2 no_args_is_help contract, verified
    empirically against that tag: help on STDOUT, exit 2. (Typer's rich help
    always rendered to stdout — only the rendering path changed here.)"""
    from typer.testing import CliRunner

    from fbx.cli.main import app as cli_app

    result = CliRunner().invoke(cli_app, [])
    assert result.exit_code == 2
    assert "Usage" in result.stdout


# -- suggestions rules ------------------------------------------------------------


def test_suggestions_cover_the_safe_rule_set():
    snap = {
        "connection": {"state": "down"},
        "wps": {"enabled": True},
        "downloads": [{"status": "done"}, {"status": "error"}],
        "vms": [{"id": 1, "name": "vm-one", "status": "stopped"}],
        "partitions": [{"id": 2, "label": "disk", "used_bytes": 95, "total_bytes": 100}],
        "calls": [{"type": "missed", "new": True}],
        "lan_devices": [{"active": True, "primary_name": ""}],
    }
    domains = {s.domain for s in suggest(snap)}
    assert domains == {
        "connection", "wifi", "downloads", "vm", "storage", "calls", "lan",
    }


def test_suggestions_never_second_guess_radio_config():
    """GUARDRAIL: deliberate radio tuning (pinned channel, he/eht off, a band
    disabled) must never generate a suggestion — see suggestions.py."""
    snap = {
        "connection": {"state": "up"},
        "wps": {"enabled": False},
        "aps": [
            {"id": 10, "name": "2d4g",
             "config": {"primary_channel": 1, "he": {"enabled": False},
                        "eht": {"enabled": False}},
             "status": {"state": "disabled"}},
        ],
    }
    texts = " · ".join(s.text.lower() for s in suggest(snap))
    assert not re.search(r"channel|wi-?fi ?[67]|802\.11|\bhe\b|\beht\b|radio|band", texts)


def test_suggestions_quiet_on_a_tidy_box():
    snap = {
        "connection": {"state": "up"},
        "wps": {"enabled": False},
        "downloads": [{"status": "downloading"}],
        "vms": [{"id": 0, "name": "vm-zero", "status": "running"}],
        "partitions": [{"id": 2, "label": "disk", "used_bytes": 10, "total_bytes": 100}],
        "calls": [{"type": "accepted", "new": False}],
        "lan_devices": [{"active": True, "primary_name": "host-a"}],
    }
    assert suggest(snap) == []


@pytest.mark.anyio
@respx.mock
async def test_dashboard_columns_follow_terminal_width():
    authorize()
    _mock_dashboard_box()
    for width, cols, klass in ((120, 2, "-w2"), (160, 3, "-w3"), (200, 4, "-w4")):
        app = FbxApp(splash=False)
        async with app.run_test(size=(width, 40)) as pilot:
            await _settle(pilot, lambda app=app: "up" in _tile_text(app, "connection"))
            assert app.screen.has_class(klass), f"width {width}: expected {klass}"
            grid = app.screen.query_one("#dash-tiles")
            assert grid.styles.grid_size_columns == cols
