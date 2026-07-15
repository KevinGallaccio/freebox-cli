"""`fbx app` — open the interactive application."""

from __future__ import annotations

import sys

import typer

from .. import ui


def register(app: typer.Typer) -> None:
    @app.command("app")
    def app_(ctx: typer.Context) -> None:
        """Open the interactive app: dashboard, domain screens, live views."""
        launch(ctx.obj)


def launch(state: ui.CliState) -> None:
    """Start the app (shared by `fbx app` and bare `fbx`)."""
    if not (sys.stdout.isatty() and sys.stdin.isatty()):
        ui.error("the interactive app needs a terminal (see `fbx --help` for commands)")
        raise typer.Exit(1)
    # Deferred so plain CLI commands never pay the textual import.
    from ...tui import run_app

    run_app(profile=state.profile, host=state.host)
