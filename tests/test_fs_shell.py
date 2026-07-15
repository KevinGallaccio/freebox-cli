"""The files shell as a terminal: inline prompt, completion, history, rich ls.

All data fictional; the box is respx-mocked per encoded path where the test
needs distinct directories.
"""

from __future__ import annotations

import pytest
import respx
from textual.widgets import Input, Label, Static

from fbx.core import fspath
from fbx.tui.app import FbxApp
from fbx.tui.prefs import Prefs
from tests.helpers import authorize, mock_get
from tests.test_tui import _mock_dashboard_box, _settle
from tests.test_tui_screens import _open


@pytest.fixture
def anyio_backend():
    return "asyncio"


ENTRIES = [
    {"type": "dir", "name": ".", "path": "x"},
    {"type": "dir", "name": "..", "path": "x"},
    {"type": "dir", "name": "Vidéos", "foldercount": 2, "filecount": 3,
     "modification": 1783944060},
    {"type": "dir", "name": "Documents", "foldercount": 0, "filecount": 1,
     "modification": 1783944060},
    {"type": "dir", "name": "Downloads", "foldercount": 0, "filecount": 0,
     "modification": 1783944060},
    {"type": "file", "name": "notes.txt", "size": 2048, "modification": 1783944060},
    {"type": "file", "name": "evil[/bold]", "size": 10, "modification": 1783944060},
]


def _out(app: FbxApp) -> str:
    return str(app.screen.query_one("#fs-scrollback", Static).content)


def _prompt(app: FbxApp) -> str:
    return str(app.screen.query_one("#fs-prompt", Label).content)


def _input(app: FbxApp) -> Input:
    return app.screen.query_one("#fs-input", Input)


async def _shell(pilot, app: FbxApp, line: str) -> None:
    await _settle(pilot, lambda: bool(app.screen.query("#fs-input")))
    await _settle(pilot, lambda: not _input(app).disabled)
    _input(app).value = line
    await pilot.press("enter")


@pytest.mark.anyio
@respx.mock
async def test_cd_bare_goes_home_and_cd_dash_goes_back():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", [], startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _shell(pilot, app, "cd Freebox")
        await _settle(pilot, lambda: _prompt(app) == "/Freebox > ")
        await _shell(pilot, app, "cd")
        await _settle(pilot, lambda: _prompt(app) == "/ > ")
        await _shell(pilot, app, "cd -")
        await _settle(pilot, lambda: _prompt(app) == "/Freebox > ")


@pytest.mark.anyio
@respx.mock
async def test_history_recalls_and_persists():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", [], startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _shell(pilot, app, "pwd")
        await _shell(pilot, app, "help")
        await _settle(pilot, lambda: not _input(app).disabled)

        await pilot.press("up")
        assert _input(app).value == "help"
        await pilot.press("up")
        assert _input(app).value == "pwd"
        await pilot.press("up")  # top of history: stays
        assert _input(app).value == "pwd"
        await pilot.press("down")
        assert _input(app).value == "help"
        await pilot.press("down")  # past the end: back to the draft
        assert _input(app).value == ""

        assert Prefs.load().get("screens.fs.history") == ["pwd", "help"]


@pytest.mark.anyio
@respx.mock
async def test_tab_completes_commands_and_paths():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", ENTRIES, startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _settle(pilot, lambda: bool(app.screen.query("#fs-input")))

        _input(app).value = "cl"
        await pilot.press("tab")
        await _settle(pilot, lambda: _input(app).value == "clear ")

        _input(app).value = "cd Vid"
        await pilot.press("tab")
        await _settle(pilot, lambda: _input(app).value == "cd Vidéos/")

        _input(app).value = "share note"
        await pilot.press("tab")
        await _settle(pilot, lambda: _input(app).value == "share notes.txt ")


@pytest.mark.anyio
@respx.mock
async def test_tab_lists_ambiguous_candidates():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", ENTRIES, startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _settle(pilot, lambda: bool(app.screen.query("#fs-input")))

        _input(app).value = "cd Do"
        await pilot.press("tab")
        await _settle(pilot, lambda: "Documents/" in _out(app) and "Downloads/" in _out(app))
        assert _input(app).value == "cd Do"


@pytest.mark.anyio
@respx.mock
async def test_ls_is_rich_dirs_first_and_markup_safe():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", ENTRIES, startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _shell(pilot, app, "ls")
        await _settle(pilot, lambda: "entries in /" in _out(app))
        out = _out(app)
        assert "Vidéos/" in out
        assert "5 items" in out  # foldercount 2 + filecount 3
        assert "2026-" in out  # modification date rendered
        assert out.index("Vidéos/") < out.index("notes.txt")  # dirs first
        # A bracketed name renders literally — no markup interpretation.
        assert "evil[/bold]" in out


@pytest.mark.anyio
@respx.mock
async def test_clear_wipes_the_scrollback():
    authorize()
    _mock_dashboard_box()
    mock_get("fs/ls/", ENTRIES, startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _shell(pilot, app, "ls")
        await _settle(pilot, lambda: "entries in /" in _out(app))
        await _shell(pilot, app, "clear")
        await _settle(pilot, lambda: _out(app) == "")


@pytest.mark.anyio
@respx.mock
async def test_tree_walks_dirs_and_respects_the_entry_budget(monkeypatch):
    authorize()
    _mock_dashboard_box()
    mock_get(f"fs/ls/{fspath.encode('/')}", [
        {"type": "dir", "name": "A"},
        {"type": "file", "name": "root.txt", "size": 1},
    ], startswith=True)
    mock_get(f"fs/ls/{fspath.encode('/A')}", [
        {"type": "dir", "name": "B"},
    ], startswith=True)
    mock_get(f"fs/ls/{fspath.encode('/A/B')}", [
        {"type": "file", "name": "deep.txt", "size": 1},
    ], startswith=True)
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "fs")
        await _shell(pilot, app, "tree")
        await _settle(pilot, lambda: "deep.txt" in _out(app))
        out = _out(app)
        assert "├── A/" in out or "└── A/" in out
        assert "root.txt" in out
        assert "truncated" not in out

        await _shell(pilot, app, "clear")
        await _settle(pilot, lambda: _out(app) == "")
        monkeypatch.setattr("fbx.tui.screens.fs.TREE_ENTRIES", 1)
        await _shell(pilot, app, "tree")
        await _settle(pilot, lambda: "truncated" in _out(app))
