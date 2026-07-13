"""FbxClient: envelope handling, session renewal, permissions."""

from __future__ import annotations

import httpx
import pytest
import respx

from fbx.core.client import FbxClient
from fbx.core.errors import FbxAPIError, FbxHTTPError, FbxPermissionError

BASE = "http://mafreebox.freebox.fr/api/v16/"


def _login_routes(permissions: dict | None = None) -> None:
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"challenge": "c"}})
    )
    respx.post(f"{BASE}login/session/").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": {"session_token": "S1", "permissions": permissions or {}},
            },
        )
    )


def _client() -> FbxClient:
    return FbxClient(BASE, app_id="app", app_token="tok")


@respx.mock
def test_request_returns_unwrapped_result():
    _login_routes()
    respx.get(f"{BASE}system/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"firmware_version": "4.12.2"}})
    )
    with _client() as fbx:
        assert fbx.get("system/") == {"firmware_version": "4.12.2"}
    # The session token rode along on the authenticated call.
    assert respx.calls.last.request.headers.get("X-Fbx-App-Auth") == "S1"


@respx.mock
def test_api_error_surfaces_error_code():
    _login_routes()
    respx.get(f"{BASE}vm/").mock(
        return_value=httpx.Response(
            200, json={"success": False, "error_code": "noent", "msg": "no such object"}
        )
    )
    with _client() as fbx:
        with pytest.raises(FbxAPIError) as ei:
            fbx.get("vm/")
    assert ei.value.error_code == "noent"


@respx.mock
def test_expired_session_reopens_once_then_succeeds():
    _login_routes()
    # First data call: auth_required. Client should re-login and retry.
    respx.get(f"{BASE}system/").mock(
        side_effect=[
            httpx.Response(403, json={"success": False, "error_code": "auth_required"}),
            httpx.Response(200, json={"success": True, "result": {"ok": True}}),
        ]
    )
    with _client() as fbx:
        assert fbx.get("system/") == {"ok": True}


@respx.mock
def test_persistent_auth_failure_does_not_loop():
    _login_routes()
    # Always auth_required — must retry exactly once, then raise (no infinite loop).
    route = respx.get(f"{BASE}system/").mock(
        return_value=httpx.Response(403, json={"success": False, "error_code": "auth_required"})
    )
    with _client() as fbx:
        with pytest.raises(FbxAPIError):
            fbx.get("system/")
    assert route.call_count == 2  # original + one retry, then give up


@respx.mock
def test_non_json_body_raises_http_error():
    _login_routes()
    respx.get(f"{BASE}system/").mock(return_value=httpx.Response(500, text="<html>oops</html>"))
    with _client() as fbx:
        with pytest.raises(FbxHTTPError):
            fbx.get("system/")


@respx.mock
def test_permissions_from_session():
    _login_routes({"vm": True, "settings": False})
    with _client() as fbx:
        assert fbx.has_permission("vm") is True
        assert fbx.has_permission("settings") is False
        fbx.require_permission("vm")  # no raise
        with pytest.raises(FbxPermissionError) as ei:
            fbx.require_permission("settings")
    assert ei.value.scope == "settings"
