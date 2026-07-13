"""The Freebox authorization + session flow — the part implementations get wrong.

Two phases:
- **Authorization** (once per box, needs a human): register the app, then wait
  for the user to press ▶ on the box's front panel. Yields a long-lived
  `app_token`.
- **Session** (every run, expires): sign the box's challenge with the app_token
  (HMAC-SHA1) to obtain a short-lived `session_token`.

These are plain functions over an `httpx.Client` + base URL so they're trivial
to test and don't depend on the higher-level client (which depends on them).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections.abc import Callable

import httpx

from .envelope import unwrap
from .errors import (
    FbxAPIError,
    FbxAuthError,
    FbxAuthorizationDenied,
    FbxAuthorizationTimeout,
    FbxHTTPError,
)
from .models.auth import AuthorizeResult, SessionResult, TrackStatus

log = logging.getLogger("fbx.auth")

# How long the box keeps the front-panel prompt up. We poll a little past this
# before declaring a timeout so we don't beat the box to the verdict.
_AUTHORIZE_POLL_SECONDS = 90
_AUTHORIZE_POLL_INTERVAL = 1.0


def sign_challenge(app_token: str, challenge: str) -> str:
    """`password = HMAC-SHA1(app_token, challenge)`, hex-encoded."""
    return hmac.new(app_token.encode(), challenge.encode(), hashlib.sha1).hexdigest()


def request_authorization(
    http: httpx.Client,
    base_url: str,
    *,
    app_id: str,
    app_name: str,
    app_version: str,
    device_name: str,
) -> AuthorizeResult:
    """`POST /login/authorize/` — register the app; returns app_token + track_id.

    The box now shows a prompt on its front display; the user must accept it.
    Only works from the LAN.
    """
    resp = http.post(
        f"{base_url}login/authorize/",
        json={
            "app_id": app_id,
            "app_name": app_name,
            "app_version": app_version,
            "device_name": device_name,
        },
    )
    result = unwrap(resp, method="POST", path="login/authorize/")
    return AuthorizeResult.model_validate(result)


def poll_track(http: httpx.Client, base_url: str, track_id: int) -> TrackStatus:
    """`GET /login/authorize/{track_id}` — current authorization status."""
    resp = http.get(f"{base_url}login/authorize/{track_id}")
    result = unwrap(resp, method="GET", path=f"login/authorize/{track_id}")
    raw = (result or {}).get("status", "unknown")
    try:
        return TrackStatus(raw)
    except ValueError:
        return TrackStatus.UNKNOWN


def wait_for_authorization(
    http: httpx.Client,
    base_url: str,
    track_id: int,
    *,
    on_pending: Callable[[int], None] | None = None,
    poll_seconds: int = _AUTHORIZE_POLL_SECONDS,
    interval: float = _AUTHORIZE_POLL_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll until the user accepts. Raises on denial or timeout.

    `on_pending(elapsed)` is called each tick so the UI can nudge the user to
    the box ("go press ▶") — the #1 reason these flows fail is a missed prompt.
    """
    elapsed = 0
    while elapsed < poll_seconds:
        status = poll_track(http, base_url, track_id)
        if status is TrackStatus.GRANTED:
            return
        if status is TrackStatus.DENIED:
            raise FbxAuthorizationDenied("authorization was rejected on the box")
        if status is TrackStatus.TIMEOUT:
            raise FbxAuthorizationTimeout("the box's authorization prompt expired")
        if on_pending is not None:
            on_pending(elapsed)
        sleep(interval)
        elapsed += int(interval) or 1
    raise FbxAuthorizationTimeout(
        f"authorization not granted within {poll_seconds}s"
    )


def get_challenge(http: httpx.Client, base_url: str) -> str:
    """`GET /login/` — a fresh challenge to sign for a new session.

    Note: this is the *app-token* login endpoint, whose `result.challenge` is a
    plain string. (The web UI's own password login returns an obfuscated form;
    that path is not used here — see docs/api-notes.md.)
    """
    resp = http.get(f"{base_url}login/")
    result = unwrap(resp, method="GET", path="login/")
    challenge = (result or {}).get("challenge")
    if not isinstance(challenge, str):
        raise FbxAuthError(
            f"login challenge was not a string (got {type(challenge).__name__}); "
            "the box may be using the web-UI login shape — see docs/api-notes.md"
        )
    return challenge


def open_session(
    http: httpx.Client,
    base_url: str,
    *,
    app_id: str,
    app_token: str,
) -> SessionResult:
    """`GET /login/` then `POST /login/session/` — obtain a session token.

    Maps the login-specific failure codes to `FbxAuthError` so callers can tell
    "bad/stale app token" apart from a generic API error.
    """
    challenge = get_challenge(http, base_url)
    password = sign_challenge(app_token, challenge)
    try:
        resp = http.post(
            f"{base_url}login/session/",
            json={"app_id": app_id, "password": password},
        )
        result = unwrap(resp, method="POST", path="login/session/")
    except FbxAPIError as exc:
        if exc.error_code in {"invalid_token", "insufficient_rights", "denied"}:
            raise FbxAuthError(
                f"the box rejected our app token ({exc.error_code}). "
                "Re-run `fbx auth login` to re-authorize."
            ) from exc
        raise
    return SessionResult.model_validate(result)


def fetch_permissions(http: httpx.Client, base_url: str) -> dict:
    """`GET /login/perms/` — the richer `{scope: {granted, desc}}` map.

    Requires an active session (the `X-Fbx-App-Auth` header must be set on
    `http`). Returns `{}` if the box doesn't expose it.
    """
    try:
        resp = http.get(f"{base_url}login/perms/")
        return unwrap(resp, method="GET", path="login/perms/") or {}
    except (FbxAPIError, FbxHTTPError) as exc:
        log.debug("login/perms/ unavailable: %s", exc)
        return {}
