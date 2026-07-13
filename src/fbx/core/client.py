"""The authenticated Freebox client: one object every command talks through.

Responsibilities:
- hold the connection (base URL, TLS trust) and the app credential,
- open a session on demand and attach `X-Fbx-App-Auth` to every request,
- unwrap the Freebox envelope into data or typed errors,
- transparently re-open the session **once** on an auth failure, then fail loudly,
- answer "do we hold permission X?" from the session's permission map.

It knows nothing about the CLI. Construct one with `connect()`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from . import auth, credentials, discovery
from .certs import default_verify
from .envelope import unwrap
from .errors import (
    FbxAPIError,
    FbxNotAuthenticated,
    FbxPermissionError,
)
from .models.discovery import ApiVersion

log = logging.getLogger("fbx.client")

# Envelope error codes that mean "your session is gone" — re-login and retry.
_AUTH_RETRY_CODES = {"auth_required", "invalid_session"}


class FbxClient:
    """An authenticated connection to one box. Not thread-safe; use per task."""

    def __init__(
        self,
        base_url: str,
        *,
        app_id: str,
        app_token: str,
        verify: Any = True,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.app_id = app_id
        self.app_token = app_token
        self.session_token: str | None = None
        self.permissions: dict[str, bool] = {}
        self._http = http or httpx.Client(verify=verify, timeout=timeout)

    # -- session -----------------------------------------------------------

    def login(self) -> None:
        """Open a fresh session and attach it to subsequent requests."""
        result = auth.open_session(
            self._http, self.base_url, app_id=self.app_id, app_token=self.app_token
        )
        self.session_token = result.session_token
        self.permissions = dict(result.permissions)
        self._http.headers["X-Fbx-App-Auth"] = self.session_token
        log.debug("session opened; permissions: %s", sorted(self.permissions))

    def ensure_session(self) -> None:
        if self.session_token is None:
            self.login()

    # -- requests ----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        params: dict | None = None,
        _retry: bool = True,
    ) -> Any:
        """Make an authenticated call and return the unwrapped `result`.

        `path` is relative to the API base (e.g. "system/", "vm/"). Re-opens the
        session once on an auth-expiry error, then gives up.
        """
        self.ensure_session()
        rel = path.lstrip("/")
        url = f"{self.base_url}{rel}"
        try:
            resp = self._http.request(method.upper(), url, json=data, params=params)
            return unwrap(resp, method=method.upper(), path=rel)
        except FbxAPIError as exc:
            if _retry and exc.error_code in _AUTH_RETRY_CODES:
                log.debug("auth expired (%s); re-opening session once", exc.error_code)
                self.login()
                return self.request(
                    method, path, data=data, params=params, _retry=False
                )
            raise

    def get(self, path: str, *, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, data: Any = None) -> Any:
        return self.request("POST", path, data=data)

    def put(self, path: str, *, data: Any = None) -> Any:
        return self.request("PUT", path, data=data)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    # -- permissions -------------------------------------------------------

    def has_permission(self, scope: str) -> bool:
        self.ensure_session()
        return bool(self.permissions.get(scope, False))

    def require_permission(self, scope: str) -> None:
        """Raise `FbxPermissionError` if the app lacks `scope`."""
        if not self.has_permission(scope):
            raise FbxPermissionError(scope)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FbxClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def resolve_connection(
    host: str | None = None,
    *,
    timeout: float = 5.0,
) -> tuple[str, Any, ApiVersion]:
    """Probe the box and return `(base_url, verify, api_version)`.

    Local access is plain HTTP against `mafreebox.freebox.fr` (or `host`). We
    read `/api_version` first so the API major version comes from the box, never
    a constant. (Remote HTTPS via `api_domain` is wired through `default_verify`
    but not exercised on the LAN.)
    """
    resolved_host = host or discovery.DEFAULT_HOST
    apiver = discovery.probe(resolved_host, timeout=timeout)
    base_url = apiver.base_url(resolved_host, scheme="http")
    return base_url, default_verify(scheme="http"), apiver


def enroll(
    *,
    app_id: str,
    app_name: str,
    app_version: str,
    device_name: str,
    profile: str = "default",
    host: str | None = None,
    timeout: float = 10.0,
    on_pending: Any = None,
) -> FbxClient:
    """Run the one-time authorization, persist the app token, return a session.

    Discovers the box, requests authorization, waits for the physical ▶ press
    (calling `on_pending(elapsed)` each tick so the UI can nudge the user),
    saves the earned credential to `profile`, then opens a session. This is the
    only place that triggers the button-press flow — never call it from a
    non-interactive context.
    """
    resolved_host = host or discovery.DEFAULT_HOST
    base_url, verify, apiver = resolve_connection(resolved_host, timeout=timeout)
    http = httpx.Client(verify=verify, timeout=timeout)

    grant = auth.request_authorization(
        http,
        base_url,
        app_id=app_id,
        app_name=app_name,
        app_version=app_version,
        device_name=device_name,
    )
    auth.wait_for_authorization(http, base_url, grant.track_id, on_pending=on_pending)

    cred = credentials.Credential(
        app_id=app_id,
        app_token=grant.app_token,
        box_uid=apiver.uid,
        box_model=apiver.box_model,
        api_domain=apiver.api_domain,
        host=resolved_host,
        https_port=apiver.https_port,
    )
    credentials.save(cred, profile)

    client = FbxClient(
        base_url,
        app_id=app_id,
        app_token=grant.app_token,
        verify=verify,
        timeout=timeout,
        http=http,
    )
    client.login()
    return client


def connect(
    profile: str = "default",
    *,
    host: str | None = None,
    timeout: float = 10.0,
    login: bool = True,
) -> FbxClient:
    """Build a ready-to-use client for a stored profile.

    Raises `FbxNotAuthenticated` if the profile has no credential — callers in
    non-interactive contexts (MCP, scripts) must handle that rather than
    triggering the button-press flow.
    """
    cred = credentials.load(profile)
    if cred is None:
        raise FbxNotAuthenticated(
            f"no credentials for profile '{profile}'. Run `fbx auth login` first."
        )
    base_url, verify, _ = resolve_connection(host or cred.host, timeout=timeout)
    client = FbxClient(
        base_url,
        app_id=cred.app_id,
        app_token=cred.app_token,
        verify=verify,
        timeout=timeout,
    )
    if login:
        client.login()
    return client
