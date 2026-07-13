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


def test_unknown_fields_ignored_on_load():
    # Forward-compat: a newer fbx may have written extra keys.
    credentials.save(credentials.Credential(app_id="a", app_token="t"))
    path = credentials.credentials_path()
    data = path.read_text().replace('"app_token": "t"', '"app_token": "t", "future_field": 1')
    path.write_text(data)
    loaded = credentials.load()
    assert loaded is not None and loaded.app_token == "t"
