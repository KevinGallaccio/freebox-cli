"""The MCP server's connection to the box: one client, serialized, typed errors.

Owns the single `FbxClient` the tools share (created lazily on the first call,
never at startup, so a dead box doesn't kill the handshake) and turns every
`FbxError` into an agent-facing message. `FbxClient` is not thread-safe and
tool calls arrive concurrently, so calls are serialized under a lock — the box
is a home router, not a database; one request at a time is the polite rate.

Never triggers the pairing flow: with no stored credential the tool call fails
with instructions to run `fbx auth login` at a terminal (it needs a physical
button press on the box).
"""

from __future__ import annotations

import threading
from typing import Any

from ..core import client as core_client
from ..core.errors import (
    FbxAPIError,
    FbxDiscoveryError,
    FbxError,
    FbxHTTPError,
    FbxNotAuthenticated,
    FbxPermissionError,
)
from .registry import ToolSpec


class FbxMcpToolError(Exception):
    """A tool failure with an agent-facing message (becomes an MCP tool error)."""


def error_message(exc: FbxError, *, profile: str) -> str:
    """One clean, actionable line per failure class — no stack traces."""
    if isinstance(exc, FbxNotAuthenticated):
        return (
            f"fbx is not paired with a Freebox (profile {profile!r}). Pairing is a "
            "one-time human step: run `fbx auth login` in a terminal on this "
            "machine and press the ▶ button on the Freebox's front panel. "
            "This tool cannot do it for you."
        )
    if isinstance(exc, FbxPermissionError):
        return (
            f"the fbx app token lacks the `{exc.scope}` permission. Grant it in "
            "Freebox OS (http://mafreebox.freebox.fr) → Paramètres → Gestion des "
            "accès → Applications → fbx, then retry."
        )
    if isinstance(exc, FbxAPIError):
        where = f" ({exc.method} {exc.path})" if exc.path else ""
        return f"the box refused the call{where}: {exc.error_code}: {exc.msg or 'API error'}"
    if isinstance(exc, (FbxDiscoveryError, FbxHTTPError)):
        return f"can't reach the box: {exc}"
    return str(exc)


class FbxRuntime:
    """Shared state for one server process: the client and its settings."""

    def __init__(self, *, profile: str = "default", host: str | None = None) -> None:
        self.profile = profile
        self.host = host
        self._client: Any = None
        self._lock = threading.Lock()

    def call(self, spec: ToolSpec, args: dict) -> Any:
        """Run one tool call synchronously (the server offloads to a thread)."""
        with self._lock:
            try:
                if self._client is None:
                    self._client = core_client.connect(self.profile, host=self.host)
                return spec.fn(self._client, **args)
            except (FbxDiscoveryError, FbxHTTPError) as exc:
                # Transport trouble: drop the client so the next call rediscovers
                # the box instead of reusing a possibly-stale base URL.
                self._close()
                raise FbxMcpToolError(error_message(exc, profile=self.profile)) from exc
            except FbxError as exc:
                raise FbxMcpToolError(error_message(exc, profile=self.profile)) from exc

    def _close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def close(self) -> None:
        with self._lock:
            self._close()
