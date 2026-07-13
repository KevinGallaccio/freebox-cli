"""The auth state machine — the part implementations get wrong (§4)."""

from __future__ import annotations

import httpx
import pytest
import respx

from fbx.core import auth
from fbx.core.errors import (
    FbxAuthError,
    FbxAuthorizationDenied,
    FbxAuthorizationTimeout,
)
from fbx.core.models.auth import TrackStatus

BASE = "http://mafreebox.freebox.fr/api/v16/"


def _client() -> httpx.Client:
    return httpx.Client(base_url="")


def test_sign_challenge_is_hmac_sha1():
    # Locks in algorithm (SHA1), key/message order, and hex encoding.
    assert (
        auth.sign_challenge("app_token_xyz", "challenge_abc")
        == "be7b5e38f88c5c286deaa71b6de3c38f11765f3e"
    )


@respx.mock
def test_open_session_happy_path():
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"challenge": "chal"}})
    )
    session_route = respx.post(f"{BASE}login/session/").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": {"session_token": "sess123", "permissions": {"settings": True}},
            },
        )
    )
    with _client() as http:
        result = auth.open_session(http, BASE, app_id="fr.kgallaccio.fbx", app_token="tok")
    assert result.session_token == "sess123"
    assert result.permissions == {"settings": True}
    # The signed password must be HMAC-SHA1(app_token, challenge), not the raw token.
    sent = session_route.calls.last.request
    assert b"sess123" not in sent.content
    assert b"tok" not in sent.content


@respx.mock
def test_open_session_bad_token_becomes_auth_error():
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"challenge": "chal"}})
    )
    respx.post(f"{BASE}login/session/").mock(
        return_value=httpx.Response(
            403, json={"success": False, "error_code": "invalid_token", "msg": "bad token"}
        )
    )
    with _client() as http:
        with pytest.raises(FbxAuthError):
            auth.open_session(http, BASE, app_id="app", app_token="stale")


@respx.mock
def test_challenge_wrong_shape_raises():
    # The web-UI login returns an obfuscated array, not a plain string; guard it.
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"challenge": ["obfuscated"]}}
        )
    )
    with _client() as http:
        with pytest.raises(FbxAuthError):
            auth.get_challenge(http, BASE)


def _track_response(status: str) -> httpx.Response:
    return httpx.Response(200, json={"success": True, "result": {"status": status}})


@respx.mock
def test_wait_for_authorization_granted():
    respx.get(f"{BASE}login/authorize/42").mock(return_value=_track_response("granted"))
    with _client() as http:
        auth.wait_for_authorization(http, BASE, 42, sleep=lambda _s: None)  # returns cleanly


@respx.mock
def test_wait_for_authorization_denied():
    respx.get(f"{BASE}login/authorize/42").mock(return_value=_track_response("denied"))
    with _client() as http:
        with pytest.raises(FbxAuthorizationDenied):
            auth.wait_for_authorization(http, BASE, 42, sleep=lambda _s: None)


@respx.mock
def test_wait_for_authorization_box_timeout():
    respx.get(f"{BASE}login/authorize/42").mock(return_value=_track_response("timeout"))
    with _client() as http:
        with pytest.raises(FbxAuthorizationTimeout):
            auth.wait_for_authorization(http, BASE, 42, sleep=lambda _s: None)


@respx.mock
def test_wait_for_authorization_pending_then_granted():
    responses = [_track_response("pending"), _track_response("pending"), _track_response("granted")]
    respx.get(f"{BASE}login/authorize/42").mock(side_effect=responses)
    ticks = []
    with _client() as http:
        auth.wait_for_authorization(
            http, BASE, 42, on_pending=ticks.append, sleep=lambda _s: None
        )
    assert len(ticks) == 2  # nudged the user while pending


@respx.mock
def test_wait_for_authorization_polls_out():
    respx.get(f"{BASE}login/authorize/42").mock(return_value=_track_response("pending"))
    with _client() as http:
        with pytest.raises(FbxAuthorizationTimeout):
            auth.wait_for_authorization(
                http, BASE, 42, poll_seconds=3, interval=1, sleep=lambda _s: None
            )


@respx.mock
def test_poll_track_unknown_status():
    respx.get(f"{BASE}login/authorize/7").mock(return_value=_track_response("weird"))
    with _client() as http:
        assert auth.poll_track(http, BASE, 7) is TrackStatus.UNKNOWN
