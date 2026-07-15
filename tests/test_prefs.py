"""App preferences: the TOML store and what the app persists through it.

The autouse `_isolate_credentials` fixture redirects `credentials.config_dir`
to a tmp dir, and prefs resolves its path through that same function — no test
here can touch the real `~/.config/fbx`.
"""

from __future__ import annotations

import tomllib

import pytest
import respx
from textual.widgets import Label

from fbx.tui.app import FbxApp
from fbx.tui.prefs import Prefs, prefs_path
from tests.helpers import authorize, mock_get
from tests.test_tui import _mock_dashboard_box, _settle
from tests.test_tui_screens import _open


@pytest.fixture
def anyio_backend():
    return "asyncio"


# -- the store itself ----------------------------------------------------------


def test_roundtrip_and_valid_toml():
    prefs = Prefs()
    prefs.set("app.theme", "nord")
    prefs.set("screens.fs.last_dir", "/Freebox/Vidéos")

    with open(prefs_path(), "rb") as fh:
        on_disk = tomllib.load(fh)
    assert on_disk == {"app": {"theme": "nord"}, "screens": {"fs": {"last_dir": "/Freebox/Vidéos"}}}

    reloaded = Prefs.load()
    assert reloaded.get("app.theme") == "nord"
    assert reloaded.get("screens.fs.last_dir") == "/Freebox/Vidéos"
    assert reloaded.get("screens.fs.missing", "fallback") == "fallback"


def test_missing_and_corrupt_files_mean_defaults():
    assert Prefs.load().get("app.theme") is None

    prefs_path().parent.mkdir(parents=True, exist_ok=True)
    prefs_path().write_text("this is [not TOML")
    assert Prefs.load().get("app.theme", "textual-dark") == "textual-dark"


def test_set_preserves_keys_it_does_not_know():
    prefs_path().parent.mkdir(parents=True, exist_ok=True)
    prefs_path().write_text('[future]\nflag = true\n')
    prefs = Prefs.load()
    prefs.set("app.theme", "nord")
    assert Prefs.load().get("future.flag") is True


# -- what the app persists -----------------------------------------------------


@pytest.mark.anyio
@respx.mock
async def test_theme_survives_relaunch():
    authorize()
    _mock_dashboard_box()
    app = FbxApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.theme = "textual-light"
        await _settle(pilot, lambda: Prefs.load().get("app.theme") == "textual-light")

    assert FbxApp().theme == "textual-light"


@pytest.mark.anyio
@respx.mock
async def test_lan_all_active_choice_survives_relaunch():
    authorize()
    _mock_dashboard_box()
    app = FbxApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "lan", "hosts")
        await pilot.press("a")
        await _settle(pilot, lambda: Prefs.load().get("screens.lan.show") == "all")

    relaunched = FbxApp()
    async with relaunched.run_test(size=(120, 40)) as pilot:
        await _open(pilot, relaunched, "lan", "hosts")
        await _settle(pilot, lambda: "all known" in str(relaunched.screen.sub_title))


@pytest.mark.anyio
@respx.mock
async def test_fs_last_dir_survives_relaunch():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", [], startswith=True)
    from textual.widgets import Input

    app = FbxApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _settle(pilot, lambda: bool(app.screen.query("#fs-input")))
        app.screen.query_one("#fs-input", Input).value = "cd Freebox"
        await pilot.press("enter")
        await _settle(pilot, lambda: Prefs.load().get("screens.fs.last_dir") == "/Freebox")

    relaunched = FbxApp()
    async with relaunched.run_test(size=(120, 40)) as pilot:
        await _open(pilot, relaunched, "fs")
        await _settle(pilot, lambda: bool(relaunched.screen.query("#fs-prompt")))
        prompt = str(relaunched.screen.query_one("#fs-prompt", Label).content)
        assert prompt == "/Freebox > "
