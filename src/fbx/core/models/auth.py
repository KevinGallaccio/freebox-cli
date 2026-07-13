"""Models for the authorization + session flow."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AuthorizeResult(BaseModel):
    """Response to `POST /login/authorize/` — the one-time app registration."""

    app_token: str
    track_id: int


class TrackStatus(str, Enum):
    """Status values from `GET /login/authorize/{track_id}`."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class Permission(BaseModel):
    granted: bool = False
    desc: str | None = None


class SessionResult(BaseModel):
    """Response to `POST /login/session/`."""

    model_config = {"extra": "allow"}

    session_token: str
    # Permissions come back as a flat {scope: bool} map on session open; the
    # richer {scope: {granted, desc}} shape is available from /login/perms/.
    permissions: dict[str, bool] = {}
