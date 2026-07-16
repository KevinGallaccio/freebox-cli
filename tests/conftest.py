from __future__ import annotations

import pytest

from fbx.core import credentials
from fbx.tui import i18n


@pytest.fixture(autouse=True)
def _isolate_credentials(tmp_path, monkeypatch):
    """Never let a test read or write the user's real credential store."""
    monkeypatch.setattr(credentials, "config_dir", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _isolate_language(monkeypatch):
    """Tests assert English UI; the host's locale (or a previous test's
    set_lang) must not leak in. French tests opt in via i18n.set_lang."""
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setenv("LC_ALL", "C")
    i18n.set_lang("en")
    yield
    i18n.set_lang("en")
