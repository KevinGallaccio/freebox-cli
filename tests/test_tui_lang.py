"""The app in French: saved-pref startup, the in-app switcher, persistence.

Same offline contract as the rest of the TUI suite: the real app, driven by
keys, against the respx-mocked box.
"""

from __future__ import annotations

import pytest
import respx
from textual.widgets import OptionList, Static

from fbx.core import credentials
from fbx.tui import i18n
from fbx.tui.app import FbxApp
from fbx.tui.widgets import LanguageModal
from tests.test_tui import _mock_dashboard_box, _settle, _tile_text, authorize


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _menu_text(app: FbxApp) -> str:
    menu = app.screen.query_one("#dash-menu", OptionList)
    return " | ".join(str(menu.get_option_at_index(i).prompt) for i in range(menu.option_count))


@pytest.mark.anyio
@respx.mock
async def test_saved_french_pref_renders_the_dashboard_in_french():
    authorize()
    _mock_dashboard_box()
    (credentials.config_dir() / "app.toml").write_text('[app]\nlang = "fr"\n')
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "connecté" in _tile_text(app, "connection"))
        # Menu speaks Freebox OS's French, translated at render time.
        menu = _menu_text(app)
        assert "Gestion des ports" in menu
        assert "Périphériques réseau" in menu
        assert "Explorateur de fichiers" in menu
        # Units localize too: octets, not bytes (1 MB/s mocked rate_down).
        assert "Mo/s" in _tile_text(app, "connection")
        # Binding descriptions were translated per instance.
        descriptions = {
            binding.description for _, binding, *_ in app.screen.active_bindings.values()
        }
        assert "Quitter" in descriptions


@pytest.mark.anyio
@respx.mock
async def test_language_switcher_persists_and_rebuilds_live():
    authorize()
    _mock_dashboard_box()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "up" in _tile_text(app, "connection"))
        assert "Port forwarding" in _menu_text(app)

        await pilot.press("l")
        await _settle(pilot, lambda: isinstance(app.screen, LanguageModal))
        await pilot.press("down", "enter")  # English is highlighted; below: Français

        # The whole UI rebuilt in French — no restart.
        await _settle(pilot, lambda: "connecté" in _tile_text(app, "connection"))
        assert i18n.lang() == "fr"
        assert "Gestion des ports" in _menu_text(app)
        assert "Navigation" in str(app.screen.query_one("#dash-menu-pane Static", Static).content)
        # And the choice survives the next launch.
        assert 'lang = "fr"' in (credentials.config_dir() / "app.toml").read_text()


@pytest.mark.anyio
@respx.mock
async def test_language_modal_escape_changes_nothing():
    authorize()
    _mock_dashboard_box()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: "up" in _tile_text(app, "connection"))
        await pilot.press("l")
        await _settle(pilot, lambda: isinstance(app.screen, LanguageModal))
        await pilot.press("escape")
        await _settle(pilot, lambda: not isinstance(app.screen, LanguageModal))
        assert i18n.lang() == "en"
        assert not (credentials.config_dir() / "app.toml").exists()
