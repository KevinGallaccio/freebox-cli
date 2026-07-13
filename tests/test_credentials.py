"""Credential store: round-trip, profiles, and 0600 permissions."""

from __future__ import annotations

import stat

import pytest

from fbx.core import credentials


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    # Redirect the config dir so tests never touch a real ~/.config/fbx.
    monkeypatch.setattr(credentials, "config_dir", lambda: tmp_path)


def test_round_trip():
    cred = credentials.Credential(app_id="app", app_token="tok", box_model="fbxgw9-r1")
    credentials.save(cred)
    loaded = credentials.load()
    assert loaded is not None
    assert loaded.app_token == "tok"
    assert loaded.box_model == "fbxgw9-r1"


def test_missing_profile_returns_none():
    assert credentials.load("nope") is None


def test_profiles_are_isolated():
    credentials.save(credentials.Credential(app_id="a", app_token="t1"), profile="home")
    credentials.save(credentials.Credential(app_id="a", app_token="t2"), profile="work")
    assert credentials.load("home").app_token == "t1"
    assert credentials.load("work").app_token == "t2"
    assert set(credentials.list_profiles()) == {"home", "work"}


def test_delete():
    credentials.save(credentials.Credential(app_id="a", app_token="t"))
    assert credentials.delete() is True
    assert credentials.load() is None
    assert credentials.delete() is False  # already gone


def test_file_is_0600():
    credentials.save(credentials.Credential(app_id="a", app_token="t"))
    mode = stat.S_IMODE(credentials.credentials_path().stat().st_mode)
    assert mode == 0o600


def test_overwriting_wider_mode_file_ends_at_0600():
    # Simulate a pre-existing, world-readable credentials file (e.g. restored
    # from a backup). After a save it must be 0600, never briefly wider.
    path = credentials.credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    path.chmod(0o644)
    credentials.save(credentials.Credential(app_id="a", app_token="t"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_torn_write_preserves_existing_file(monkeypatch):
    # A crash mid-serialize must leave the previously stored token intact and
    # leave no stray temp file behind.
    credentials.save(credentials.Credential(app_id="a", app_token="original"))

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(credentials.json, "dump", boom)
    with pytest.raises(RuntimeError):
        credentials.save(credentials.Credential(app_id="a", app_token="new"))

    # load() uses json.loads, not the patched json.dump — no undo needed (and
    # calling monkeypatch.undo() here would also revert the config-dir isolation
    # and read the real credentials file).
    assert credentials.load().app_token == "original"  # old data survived
    leftovers = list(credentials.config_dir().glob("*.tmp"))
    assert leftovers == []  # temp cleaned up


def test_unknown_fields_ignored_on_load():
    # Forward-compat: a newer fbx may have written extra keys.
    credentials.save(credentials.Credential(app_id="a", app_token="t"))
    path = credentials.credentials_path()
    data = path.read_text().replace('"app_token": "t"', '"app_token": "t", "future_field": 1')
    path.write_text(data)
    loaded = credentials.load()
    assert loaded is not None and loaded.app_token == "t"
