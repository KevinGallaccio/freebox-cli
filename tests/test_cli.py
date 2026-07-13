"""CLI-level tests: the stdout/stderr contract and command wiring.

These drive the real Typer app with the box fully mocked (respx) and the
credential store redirected to a tmp dir, so they need no Freebox.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from fbx.core import credentials

BASE = "http://mafreebox.freebox.fr/api/v16/"
# click ≥8.2 separates stdout/stderr by default (result.stdout / result.stderr).
runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "config_dir", lambda: tmp_path)


def _authorized():
    credentials.save(credentials.Credential(app_id="app", app_token="tok", box_model="fbxgw9-r1"))


def _mock_box(*, system_result=None):
    respx.get("http://mafreebox.freebox.fr/api_version").mock(
        return_value=httpx.Response(
            200,
            json={"api_version": "16.0", "api_base_url": "/api/", "box_model": "fbxgw9-r1"},
        )
    )
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"challenge": "c"}})
    )
    respx.post(f"{BASE}login/session/").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"session_token": "S1", "permissions": {"settings": True}}},
        )
    )
    if system_result is not None:
        respx.get(f"{BASE}system/").mock(
            return_value=httpx.Response(200, json={"success": True, "result": system_result})
        )


@respx.mock
def test_system_info_json_goes_to_stdout_only():
    _authorized()
    _mock_box(system_result={"firmware_version": "4.12.2", "serial": "XYZ"})
    result = runner.invoke(app, ["--json", "system", "info"])
    assert result.exit_code == 0
    # stdout is pure, parseable JSON — the whole result object (rule #5).
    payload = json.loads(result.stdout)
    assert payload["firmware_version"] == "4.12.2"
    assert payload["serial"] == "XYZ"


@respx.mock
def test_status_messages_never_pollute_stdout():
    _authorized()
    _mock_box(system_result={"firmware_version": "4.12.2"})
    result = runner.invoke(app, ["--json", "system", "info"])
    # Whatever chatter exists must be on stderr; stdout parses cleanly as JSON.
    json.loads(result.stdout)  # would raise if a message leaked into stdout


@respx.mock
def test_api_raw_call_strips_pasted_prefix():
    _authorized()
    _mock_box()
    respx.get(f"{BASE}connection/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"state": "up"}})
    )
    # A path pasted straight from the docs (with /api/latest/) should still work.
    result = runner.invoke(app, ["api", "GET", "/api/latest/connection/"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"state": "up"}


def test_not_authenticated_exits_3_with_clean_stdout():
    # No credential saved.
    result = runner.invoke(app, ["system", "info"])
    assert result.exit_code == 3
    assert "auth login" in result.stderr
    assert result.stdout.strip() == ""  # nothing bogus on stdout


def test_auth_status_reports_unauthenticated_as_data():
    result = runner.invoke(app, ["--json", "auth", "status"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["authenticated"] is False


@respx.mock
def test_api_bad_json_data_exits_1():
    _authorized()
    result = runner.invoke(app, ["api", "POST", "vm/1/start", "--data", "{not json}"])
    assert result.exit_code == 1
    assert "valid JSON" in result.stderr
