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
from .i18n import _


class BoxCallError(Exception):
    """A box call failed and the user has already seen the toast.

    Screens catch this to keep their last good data; they never need to
    re-report it.
    """


def human_error(exc: FbxError) -> str:
    """One short, human line per failure class (shown as a notification)."""
    if isinstance(exc, FbxNotAuthenticated):
        return _("Not paired with the box — quit and run `fbx auth login` in a terminal.")
    if isinstance(exc, FbxPermissionError):
        return _(
            "Missing the '{scope}' permission — grant it in Freebox OS → "
            "Gestion des accès → Applications → fbx."
        ).format(scope=exc.scope)
    if isinstance(exc, FbxAPIError):
        return _("The box refused: {code}: {msg}").format(
            code=exc.error_code, msg=exc.msg or _("API error")
        )
    if isinstance(exc, (FbxDiscoveryError, FbxHTTPError)):
        return _("Can't reach the box: {error}").format(error=exc)
    return str(exc)
