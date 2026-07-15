"""The MCP server's connection to the box: one client, serialized, typed errors.

The client lifecycle (lazy connect, lock, drop-on-transport-error) lives in
`core.runtime.ClientRuntime`, shared with the interactive app; this module
adds the agent-facing error translation. Never triggers the pairing flow:
with no stored credential the tool call fails with instructions to run
`fbx auth login` at a terminal (it needs a physical button press on the box).
"""

from __future__ import annotations

from typing import Any

from ..core.errors import (
    FbxAPIError,
    FbxDiscoveryError,
    FbxError,
    FbxHTTPError,
    FbxNotAuthenticated,
    FbxPermissionError,
)
from ..core.runtime import ClientRuntime
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
        self._runtime = ClientRuntime(profile=profile, host=host)

    def call(self, spec: ToolSpec, args: dict) -> Any:
        """Run one tool call synchronously (the server offloads to a thread)."""
        try:
            return self._runtime.call(spec.fn, **args)
        except FbxError as exc:
            raise FbxMcpToolError(error_message(exc, profile=self.profile)) from exc

    def close(self) -> None:
        self._runtime.close()
