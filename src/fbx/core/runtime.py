"""A shared, serialized connection to the box for long-lived adapters.

The MCP server and the interactive app both need the same thing: ONE lazy
`FbxClient` (created on first use, never at startup, so a dead box doesn't
kill the process), calls serialized under a lock (`FbxClient` is not
thread-safe, and the box is a home router — one request at a time is the
polite rate), and the client dropped on transport errors so the next call
rediscovers the box instead of reusing a possibly-stale base URL.

Never triggers the pairing flow: with no stored credential, calls raise
`FbxNotAuthenticated` — pairing needs a human at a terminal running
`fbx auth login` and a physical button press on the box.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from . import client as core_client
from .errors import FbxDiscoveryError, FbxHTTPError


class ClientRuntime:
    """One lazily-connected `FbxClient`, shared and serialized."""

    def __init__(self, *, profile: str = "default", host: str | None = None) -> None:
        self.profile = profile
        self.host = host
        self._client: Any = None
        self._lock = threading.Lock()

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run `fn(client, *args, **kwargs)` under the lock."""
        with self._lock:
            try:
                if self._client is None:
                    self._client = core_client.connect(self.profile, host=self.host)
                return fn(self._client, *args, **kwargs)
            except (FbxDiscoveryError, FbxHTTPError):
                self._close()
                raise

    def _close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def close(self) -> None:
        with self._lock:
            self._close()
