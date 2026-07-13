"""`fbx api` — a raw authenticated call to any endpoint.

The escape hatch: it makes `fbx` useful wherever a typed command doesn't exist
yet, and it's how you explore undocumented endpoints during development. Ships
in v0.1 on purpose.
"""

from __future__ import annotations

import json
import re

import typer

from ...core import client as core_client
from .. import ui

# Strip a pasted `/api/v16/…` or `/api/latest/…` prefix so doc paths work as-is.
_PREFIX_RE = re.compile(r"^/?api/(?:v\d+|latest)/", re.IGNORECASE)


def register(root: typer.Typer) -> None:
    root.command("api")(api)


def api(
    ctx: typer.Context,
    method: str = typer.Argument(..., help="HTTP method: GET, POST, PUT, DELETE."),
    path: str = typer.Argument(..., help="Endpoint path, e.g. 'system/' or 'vm/{id}'."),
    data: str | None = typer.Option(
        None, "--data", "-d", help="JSON request body."
    ),
) -> None:
    """Make a raw authenticated API call and print the JSON result.

    Examples:
      fbx api GET system/
      fbx api GET connection/
      fbx api POST vm/1/start
      fbx api PUT wifi/config/ --data '{"enabled": true}'
    """
    from ..main import handle_errors

    state: ui.CliState = ctx.obj

    body = None
    if data is not None:
        try:
            body = json.loads(data)
        except json.JSONDecodeError as exc:
            ui.error(f"--data is not valid JSON: {exc}")
            raise typer.Exit(1) from exc

    rel = _PREFIX_RE.sub("", path).lstrip("/")

    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host)
        with fbx:
            result = fbx.request(method, rel, data=body)
    # A raw call returns arbitrary data with no table; always emit JSON.
    ui.emit_json(result)
