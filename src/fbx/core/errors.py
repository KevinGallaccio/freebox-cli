"""Typed errors for the Freebox core.

Every failure the core can produce is one of these, so adapters (CLI, MCP) can
map them to exit codes / tool errors without parsing strings. Each carries
enough context to render a helpful message; none carry secrets.
"""

from __future__ import annotations


class FbxError(Exception):
    """Base class for every error raised by the fbx core."""


class FbxDiscoveryError(FbxError):
    """The box could not be found or reached (DNS, network, or bad response)."""


class FbxAuthError(FbxError):
    """Authentication or authorization failed."""


class FbxAuthorizationDenied(FbxAuthError):
    """The user pressed reject (or the box denied) during app authorization."""


class FbxAuthorizationTimeout(FbxAuthError):
    """The app-authorization prompt on the box expired before it was granted."""


class FbxNotAuthenticated(FbxAuthError):
    """No stored credentials for this profile — run `fbx auth login` first.

    Raised in non-interactive contexts (the MCP server, scripts) so they never
    trigger the button-press flow, which needs a human at the box.
    """


class FbxPermissionError(FbxError):
    """The app token lacks a permission the requested call needs.

    `scope` is the missing Freebox permission (e.g. "vm", "settings"). Some
    scopes can only be granted by hand in Freebox OS.
    """

    def __init__(self, scope: str, message: str | None = None) -> None:
        self.scope = scope
        super().__init__(message or f"missing the `{scope}` permission")


class FbxAPIError(FbxError):
    """The box returned `{"success": false, ...}`.

    `error_code` is the machine-readable Freebox code (e.g. "invalid_request",
    "noent", "insufficient_rights"); `msg` is the box's human message.
    """

    def __init__(
        self,
        error_code: str,
        msg: str | None = None,
        *,
        method: str | None = None,
        path: str | None = None,
        status: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.msg = msg
        self.method = method
        self.path = path
        self.status = status
        where = f" ({method} {path})" if path else ""
        super().__init__(f"{error_code}: {msg or 'API error'}{where}")


class FbxHTTPError(FbxError):
    """A transport-level failure (timeout, connection refused, TLS, non-JSON)."""
