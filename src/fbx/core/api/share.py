"""Public share links — map a filesystem path to a token-based public URL.

Part of the filesystem surface (gated by the `explorer` permission). Paths are
base64-encoded like the rest of the fs API; `expire` is an absolute Unix
timestamp (0 = never).
"""

from __future__ import annotations

from typing import Any

from .. import fspath
from . import as_list


def list_links(client: Any) -> list:
    """GET /share_link/ — every public share link (empty → [])."""
    return as_list(client.get("share_link/"))


def create(client: Any, path: str, *, expire: int = 0, fullurl: str = "") -> dict:
    """POST /share_link/ — publish `path`. `expire` is an absolute epoch (0 = never)."""
    client.require_permission("explorer")
    body = {"path": fspath.encode(path), "expire": expire, "fullurl": fullurl}
    return client.post("share_link/", data=body)


def delete(client: Any, token: str) -> Any:
    """DELETE /share_link/{token} — revoke a share link."""
    client.require_permission("explorer")
    return client.delete(f"share_link/{token}")
