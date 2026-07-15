"""Shared app plumbing: error translation and the failure sentinel."""

from __future__ import annotations

from ..core.errors import (
    FbxAPIError,
    FbxDiscoveryError,
    FbxError,
    FbxHTTPError,
    FbxNotAuthenticated,
    FbxPermissionError,
)


class BoxCallError(Exception):
    """A box call failed and the user has already seen the toast.

    Screens catch this to keep their last good data; they never need to
    re-report it.
    """


def human_error(exc: FbxError) -> str:
    """One short, human line per failure class (shown as a notification)."""
    if isinstance(exc, FbxNotAuthenticated):
        return "Not paired with the box — quit and run `fbx auth login` in a terminal."
    if isinstance(exc, FbxPermissionError):
        return (
            f"Missing the '{exc.scope}' permission — grant it in Freebox OS → "
            "Gestion des accès → Applications → fbx."
        )
    if isinstance(exc, FbxAPIError):
        return f"The box refused: {exc.error_code}: {exc.msg or 'API error'}"
    if isinstance(exc, (FbxDiscoveryError, FbxHTTPError)):
        return f"Can't reach the box: {exc}"
    return str(exc)
