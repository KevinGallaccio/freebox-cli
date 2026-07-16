"""Chat-guided pairing: the one-time ▶-button flow as a pair of MCP tools.

`fbx auth login` assumes a terminal; a Claude Desktop chat user who installed
the .mcpb extension has none (uvx's env is isolated, `fbx` isn't on their
PATH). These tools run the same authorization flow with the model narrating:
`start` registers the app and tells the user to press the button, `status`
awaits the verdict and persists the credential.

The physical button press remains the sole consent gate — starting the flow
grants nothing by itself, and the box's front-panel prompt expires on its own
(~90 s). The `app_token` earned is held only in this process's memory between
the two calls and is NEVER included in a tool result; on grant it goes
straight to the 0600 credential store (`core.credentials`).
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

import httpx

from .. import APP_ID, APP_NAME, __version__
from ..core import auth, credentials, discovery
from ..core import client as core_client
from ..core.errors import FbxError
from ..core.models.auth import TrackStatus

# The box keeps its prompt up ~90 s; cap one status call well under that so a
# single MCP call never looks hung to the client.
_MAX_WAIT_SECONDS = 60
_POLL_INTERVAL = 1.0

_PRESS_THE_BUTTON = (
    "Tell the user to go to their Freebox and press the ▶ (right-arrow) button "
    "on its front display within ~90 seconds."
)


@dataclasses.dataclass
class PendingEnrollment:
    """One authorization awaiting its button press — process-memory only."""

    app_token: str  # the secret; dies with the process unless granted
    base_url: str
    verify: Any
    host: str
    box_uid: str | None
    box_model: str | None
    api_domain: str | None
    https_port: int | None


def _device_label(cred: credentials.Credential) -> str:
    return cred.box_model or cred.host


def start(rt: Any, device_name: str | None = None, replace: bool = False) -> dict:
    """Register fbx on the box and hand the user to the front panel."""
    existing = credentials.load(rt.profile)
    if existing is not None and not replace:
        return {
            "status": "already_paired",
            "profile": rt.profile,
            "box": _device_label(existing),
            "note": (
                "A credential already exists; the other fbx tools should work as-is. "
                "Re-pair (replace=true) only if the user explicitly asks for it."
            ),
        }

    resolved_host = rt.host or discovery.DEFAULT_HOST
    base_url, verify, apiver = core_client.resolve_connection(resolved_host)
    if not device_name:
        import socket

        device_name = socket.gethostname() or "fbx-mcp"

    with httpx.Client(verify=verify, timeout=10.0) as http:
        grant = auth.request_authorization(
            http,
            base_url,
            app_id=APP_ID,
            app_name=APP_NAME,
            app_version=__version__,
            device_name=device_name,
        )

    with rt.enroll_lock:
        rt.pending_enrollments[grant.track_id] = PendingEnrollment(
            app_token=grant.app_token,
            base_url=base_url,
            verify=verify,
            host=resolved_host,
            box_uid=apiver.uid,
            box_model=apiver.box_model,
            api_domain=apiver.api_domain,
            https_port=apiver.https_port,
        )

    return {
        "status": "pending",
        "track_id": grant.track_id,
        "box": apiver.box_model or resolved_host,
        "action_required": _PRESS_THE_BUTTON,
        "next": "Then call fbx_auth_enroll_status with this track_id for the verdict.",
    }


def status(rt: Any, track_id: int, wait_seconds: int = 25) -> dict:
    """Poll one pending authorization; on grant, persist and go live."""
    with rt.enroll_lock:
        pending = rt.pending_enrollments.get(track_id)
    if pending is None:
        return {
            "status": "unknown_track",
            "note": (
                f"No pairing in progress for track_id {track_id} in this server "
                "process (it may have restarted). Start over with fbx_auth_enroll."
            ),
        }

    deadline = time.monotonic() + max(0, min(wait_seconds, _MAX_WAIT_SECONDS))
    with httpx.Client(verify=pending.verify, timeout=10.0) as http:
        while True:
            verdict = auth.poll_track(http, pending.base_url, track_id)
            if verdict is TrackStatus.GRANTED:
                return _finish(rt, track_id, pending)
            if verdict is TrackStatus.DENIED:
                with rt.enroll_lock:
                    rt.pending_enrollments.pop(track_id, None)
                return {
                    "status": "denied",
                    "note": "The authorization was rejected on the box's front panel.",
                }
            if verdict is TrackStatus.TIMEOUT:
                with rt.enroll_lock:
                    rt.pending_enrollments.pop(track_id, None)
                return {
                    "status": "timeout",
                    "note": (
                        "The box's prompt expired without a press. Start over with "
                        "fbx_auth_enroll and have the user stand by the box first."
                    ),
                }
            if time.monotonic() >= deadline:
                return {
                    "status": "pending",
                    "track_id": track_id,
                    "action_required": _PRESS_THE_BUTTON,
                    "note": "Still waiting — call fbx_auth_enroll_status again.",
                }
            time.sleep(_POLL_INTERVAL)


def _finish(rt: Any, track_id: int, pending: PendingEnrollment) -> dict:
    """Persist the earned credential and verify it opens a session."""
    cred = credentials.Credential(
        app_id=APP_ID,
        app_token=pending.app_token,
        box_uid=pending.box_uid,
        box_model=pending.box_model,
        api_domain=pending.api_domain,
        host=pending.host,
        https_port=pending.https_port,
    )
    credentials.save(cred, rt.profile)
    with rt.enroll_lock:
        rt.pending_enrollments.pop(track_id, None)
    # A previous (stale or absent) credential may back the cached box client;
    # drop it so the next tool call reconnects with the one just earned.
    rt.reset_client()

    result: dict = {
        "status": "granted",
        "profile": rt.profile,
        "box": _device_label(cred),
        "credential_stored": str(credentials.credentials_path()),
        "note": "Pairing complete — every other fbx tool is live now.",
    }
    try:
        client = core_client.FbxClient(
            pending.base_url,
            app_id=APP_ID,
            app_token=pending.app_token,
            verify=pending.verify,
        )
        with client:
            client.login()
            granted = {s for s, ok in client.permissions.items() if ok}
            missing = sorted(auth.SCOPES_USED - granted)
            if missing:
                result["permissions_missing"] = missing
                result["grant_hint"] = (
                    "The box only lets a human escalate scopes: grant these once "
                    "in Freebox OS (http://mafreebox.freebox.fr) → Paramètres → "
                    "Gestion des accès → Applications → the NEWEST fbx entry "
                    "(admin password required). `settings` unlocks the "
                    "router-config writes (Wi-Fi, DHCP, port forwarding…). "
                    "Note: each pairing creates a new entry there — older fbx "
                    "entries are dead tokens, safe to delete."
                )
            result["permissions_granted"] = sorted(
                s for s, ok in client.permissions.items() if ok
            )
    except FbxError as exc:
        # The token is saved either way; a session hiccup here is advisory.
        result["warning"] = f"credential stored, but the session check failed: {exc}"
    return result
