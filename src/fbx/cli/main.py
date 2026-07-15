"""The `fbx` Typer application: global options, error mapping, command wiring."""

from __future__ import annotations

import logging
from contextlib import contextmanager

import typer

from .. import __version__
from ..core import redaction
from ..core.errors import (
    FbxAuthError,
    FbxDiscoveryError,
    FbxError,
    FbxHTTPError,
    FbxNotAuthenticated,
    FbxPermissionError,
)
from . import ui
from .commands import api as api_cmd
from .commands import auth as auth_cmd
from .commands import calls as calls_cmd
from .commands import connection as connection_cmd
from .commands import contacts as contacts_cmd
from .commands import dhcp as dhcp_cmd
from .commands import downloads as downloads_cmd
from .commands import fs as fs_cmd
from .commands import fw as fw_cmd
from .commands import lan as lan_cmd
from .commands import mcp as mcp_cmd
from .commands import storage as storage_cmd
from .commands import system as system_cmd
from .commands import vm as vm_cmd
from .commands import wifi as wifi_cmd

app = typer.Typer(
    name="fbx",
    help="Freebox Ultra CLI — manage your box, your network, and your VMs.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


# Exit codes: distinct per failure class so scripts can branch on them.
EXIT_GENERIC = 1
EXIT_AUTH = 2
EXIT_NOT_AUTHENTICATED = 3
EXIT_PERMISSION = 4
EXIT_UNREACHABLE = 5


@contextmanager
def handle_errors():
    """Map core errors to a stderr message + a meaningful exit code."""
    try:
        yield
    except FbxNotAuthenticated as exc:
        ui.error(str(exc))
        raise typer.Exit(EXIT_NOT_AUTHENTICATED) from exc
    except FbxPermissionError as exc:
        ui.error(
            f"{exc}. Grant it in Freebox OS → Paramètres → Gestion des accès "
            "→ Applications → fbx."
        )
        raise typer.Exit(EXIT_PERMISSION) from exc
    except FbxAuthError as exc:
        ui.error(str(exc))
        raise typer.Exit(EXIT_AUTH) from exc
    except (FbxDiscoveryError, FbxHTTPError) as exc:
        # Discovery failure or a transport error mid-session — both "can't reach".
        ui.error(f"can't reach the box: {exc}")
        raise typer.Exit(EXIT_UNREACHABLE) from exc
    except FbxError as exc:
        ui.error(str(exc))
        raise typer.Exit(EXIT_GENERIC) from exc


def _version_callback(value: bool) -> None:
    if value:
        # A version string is data, but --version is a UI affordance; stderr
        # keeps stdout clean. Print plainly.
        ui.err.print(f"fbx {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default", "--profile", "-p", help="Named box profile.", show_default=False
    ),
    output: ui.OutputFormat = typer.Option(
        ui.OutputFormat.TABLE, "--output", "-o", help="Output format for data."
    ),
    json_: bool = typer.Option(
        False, "--json", help="Shorthand for --output json (whole result object)."
    ),
    host: str | None = typer.Option(
        None, "--host", help="Override the box hostname/IP.", show_default=False
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress status messages."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging (stderr)."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
    _version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    """Global options, applied before any subcommand."""
    state = ui.CliState(
        profile=profile,
        output=output,
        json=json_,
        quiet=quiet,
        verbose=verbose,
        host=host,
    )
    ctx.obj = state

    if no_color:
        ui.out.no_color = True
        ui.err.no_color = True

    # Logging goes to stderr and is redacted from the first line. Quiet still
    # allows warnings; verbose drops to DEBUG.
    level = logging.DEBUG if verbose else logging.WARNING
    handler = logging.StreamHandler()  # stderr
    # Redact on the HANDLER: handler filters run for records propagated from
    # child loggers (fbx.auth, fbx.client, …); a logger filter would not.
    redaction.install(handler)
    root = logging.getLogger("fbx")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


app.add_typer(auth_cmd.app, name="auth")
system_cmd.register(app)
api_cmd.register(app)
calls_cmd.register(app)
connection_cmd.register(app)
contacts_cmd.register(app)
dhcp_cmd.register(app)
downloads_cmd.register(app)
fs_cmd.register(app)
fw_cmd.register(app)
lan_cmd.register(app)
mcp_cmd.register(app)
storage_cmd.register(app)
vm_cmd.register(app)
wifi_cmd.register(app)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
