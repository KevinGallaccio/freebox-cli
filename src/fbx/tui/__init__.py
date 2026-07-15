"""The interactive app (`fbx` / `fbx app`) — the third thin adapter over core.

Open once, land on the dashboard, navigate domains, act (destructive actions
gated behind confirm modals), quit. The CLI and the MCP server are the other
two adapters; all three share `core.api.*` so behavior stays identical.
"""

from __future__ import annotations


def run_app(*, profile: str = "default", host: str | None = None) -> None:
    """Launch the app; blocks until the user quits."""
    from .app import FbxApp

    FbxApp(profile=profile, host=host).run()
