"""`fbx auth` — login, status, logout, permissions."""

from __future__ import annotations

import socket

import typer
from rich.table import Table

from ... import APP_ID, APP_NAME, __version__
from ...core import auth as core_auth
from ...core import client as core_client
from ...core import credentials
from ...core.errors import FbxError
from .. import ui

app = typer.Typer(help="Authorize this machine and inspect the session.", no_args_is_help=True)


def _box_label(cred: credentials.Credential | None) -> str:
    if cred and cred.box_model:
        return f"{cred.box_model} ({cred.host})"
    return cred.host if cred else "the box"


@app.command()
def login(ctx: typer.Context) -> None:
    """Authorize fbx with your Freebox (one-time — needs a button press)."""
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    device_name = socket.gethostname() or "fbx-cli"

    existing = credentials.load(state.profile)
    if existing is not None:
        ui.warn(
            f"profile '{state.profile}' is already authorized for {_box_label(existing)}; "
            "re-authorizing will replace it."
        )

    with handle_errors():
        ui.info("[bold]Discovering your Freebox…[/]", state)

        # The box shows a prompt on its front panel; the user must accept it.
        status = ui.err.status(
            "[bold]Go to your Freebox and press ▶ (the right arrow) on the front "
            "display to authorize[/]  ",
            spinner="dots",
        )
        with status:
            fbx = core_client.enroll(
                app_id=APP_ID,
                app_name=APP_NAME,
                app_version=__version__,
                device_name=device_name,
                profile=state.profile,
                host=state.host,
            )

        granted = sorted(s for s, ok in fbx.permissions.items() if ok)
        missing = sorted(core_auth.SCOPES_USED - set(granted))
        fbx.close()

    cred = credentials.load(state.profile)
    ui.success(f"Authorized. Connected to {_box_label(cred)}.")
    ui.info(
        f"Granted permissions: {', '.join(granted) if granted else '(none)'}", state
    )
    if missing:
        # Scope escalation is Freebox-OS-only by design; say so now instead of
        # letting the user discover it as a mysterious failure later.
        ui.warn(
            f"Not yet granted: {', '.join(missing)}. Tick them once in Freebox OS "
            "→ Paramètres → Gestion des accès → Applications (the newest fbx "
            "entry) — `settings` unlocks the router-config writes. Older fbx "
            "entries there are dead tokens from previous pairings; safe to delete."
        )


@app.command()
def status(ctx: typer.Context) -> None:
    """Show whether this machine is authorized, and for which box."""
    state: ui.CliState = ctx.obj
    cred = credentials.load(state.profile)

    if cred is None:
        payload = {"profile": state.profile, "authenticated": False}
        ui.info(
            f"Not authorized (profile '{state.profile}'). Run `fbx auth login`.", state
        )
        ui.emit(payload, state, table=lambda d: _status_table(d))
        return

    # Verify the stored token still opens a session.
    payload: dict = {
        "profile": state.profile,
        "authenticated": False,
        "host": cred.host,
        "box_model": cred.box_model,
        "box_uid": cred.box_uid,
    }
    try:
        fbx = core_client.connect(state.profile, host=state.host)
    except FbxError as exc:
        # A stale token, an unreachable box, or a transport blip — `status` is
        # informational, so report it as data rather than crashing.
        payload["reason"] = str(exc)
        ui.warn(str(exc))
        ui.emit(payload, state, table=_status_table)
        return

    with fbx:
        payload["authenticated"] = True
        payload["permissions"] = fbx.permissions
    ui.emit(payload, state, table=_status_table)


def _status_table(d: dict) -> Table:
    t = Table(show_header=False, box=None)
    t.add_column(style="bold")
    t.add_column()
    t.add_row("profile", str(d.get("profile", "")))
    t.add_row("authenticated", "[green]yes[/]" if d.get("authenticated") else "[red]no[/]")
    if d.get("box_model"):
        t.add_row("box", f"{d['box_model']} ({d.get('host', '')})")
    if d.get("permissions"):
        granted = sorted(s for s, ok in d["permissions"].items() if ok)
        t.add_row("permissions", ", ".join(granted) or "(none)")
    if d.get("reason"):
        t.add_row("reason", d["reason"])
    return t


@app.command()
def logout(ctx: typer.Context) -> None:
    """Forget the stored credentials for this profile (local only)."""
    state: ui.CliState = ctx.obj
    removed = credentials.delete(state.profile)
    if removed:
        ui.success(f"Removed credentials for profile '{state.profile}'.")
        ui.info(
            "To fully revoke access, also remove the app in Freebox OS → "
            "Paramètres → Gestion des accès → Applications.",
            state,
        )
    else:
        ui.info(f"No stored credentials for profile '{state.profile}'.", state)
    ui.emit({"profile": state.profile, "removed": removed}, state)


@app.command()
def permissions(ctx: typer.Context) -> None:
    """List the permission scopes granted to this app on the box."""
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host)
        with fbx:
            # Session gives {scope: bool}; /login/perms/ adds human descriptions.
            rich = core_auth.fetch_permissions(fbx._http, fbx.base_url)
            rows = []
            for scope in sorted(set(fbx.permissions) | set(rich)):
                entry = rich.get(scope) if isinstance(rich.get(scope), dict) else {}
                granted = bool(fbx.permissions.get(scope, entry.get("granted")))
                rows.append(
                    {"scope": scope, "granted": granted, "desc": entry.get("desc")}
                )
    ui.emit(rows, state, table=_permissions_table)


def _permissions_table(rows: list[dict]) -> Table:
    t = Table(title="Permissions")
    t.add_column("Scope", style="bold")
    t.add_column("Granted")
    t.add_column("Description", style="dim")
    for r in rows:
        mark = "[green]✓[/]" if r["granted"] else "[red]✗[/]"
        t.add_row(r["scope"], mark, r.get("desc") or "")
    return t
