"""The splash: a fixed beat over the already-fetching dashboard, any key skips."""

from __future__ import annotations

import pytest
import respx
from textual.widgets import Static

from fbx.tui.app import FbxApp
from fbx.tui.screens.dashboard import DashboardScreen
from fbx.tui.screens.splash import SplashScreen
from tests.helpers import authorize
from tests.test_tui import _mock_dashboard_box, _settle


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@respx.mock
async def test_the_timer_gives_way_to_a_fetched_dashboard(monkeypatch):
    # Timer-path only: under load the 0.05 s beat can elapse before any
    # assertion runs, so splash *visibility* is asserted in the key-skip test
    # (where a 30 s DURATION makes it deterministic), not here.
    monkeypatch.setattr(SplashScreen, "DURATION", 0.05)
    authorize()
    _mock_dashboard_box()
    app = FbxApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: isinstance(app.screen, DashboardScreen))
        # The dashboard was fetching underneath the whole time.
        await _settle(
            pilot,
            lambda: "up" in str(app.screen.query_one("#tile-connection", Static).content),
        )


@pytest.mark.anyio
@respx.mock
async def test_splash_shows_any_key_skips_and_q_does_not_quit(monkeypatch):
    monkeypatch.setattr(SplashScreen, "DURATION", 30.0)  # only the key can end it
    authorize()
    _mock_dashboard_box()
    app = FbxApp()
    async with app.run_test(size=(120, 40)) as pilot:
        assert isinstance(app.screen, SplashScreen)
        assert "fbx" in str(app.screen.query_one("#splash-title", Static).content)
        await pilot.press("q")
        await _settle(pilot, lambda: isinstance(app.screen, DashboardScreen))
        assert app.is_running
        # Back never pops past the dashboard floor, splash or not.
        await pilot.press("escape")
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.anyio
@respx.mock
async def test_breakpoints_apply_even_when_launch_is_covered_by_the_splash(monkeypatch):
    monkeypatch.setattr(SplashScreen, "DURATION", 0.05)
    authorize()
    _mock_dashboard_box()
    app = FbxApp()
    async with app.run_test(size=(200, 40)) as pilot:
        await _settle(pilot, lambda: isinstance(app.screen, DashboardScreen))
        await _settle(pilot, lambda: app.screen.has_class("-w4"))
