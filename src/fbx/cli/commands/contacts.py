"""`fbx contacts` — the box's address book."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import contacts as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Address book.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="contacts")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List contacts."""
    data = fetch(ctx, api.list_all)
    ui.emit(data, ctx.obj, table=_contacts_table)


# -- writes ----------------------------------------------------------------


@app.command()
def add(
    ctx: typer.Context,
    display_name: str = typer.Argument(..., help="Display name."),
    first: str | None = typer.Option(None, "--first", help="First name."),
    last: str | None = typer.Option(None, "--last", help="Last name."),
    company: str | None = typer.Option(None, "--company", help="Company."),
) -> None:
    """Create a contact."""
    fields: dict = {"display_name": display_name}
    if first is not None:
        fields["first_name"] = first
    if last is not None:
        fields["last_name"] = last
    if company is not None:
        fields["company"] = company
    data = fetch(ctx, api.create, fields)
    ui.emit_write(data, ctx.obj, message=f"created contact {display_name!r}")


@app.command()
def edit(
    ctx: typer.Context,
    contact_id: int = typer.Argument(..., help="Contact id (see `fbx contacts list`)."),
    display_name: str | None = typer.Option(None, "--display-name", help="Display name."),
    first: str | None = typer.Option(None, "--first", help="First name."),
    last: str | None = typer.Option(None, "--last", help="Last name."),
    company: str | None = typer.Option(None, "--company", help="Company."),
    notes: str | None = typer.Option(None, "--notes", help="Notes."),
) -> None:
    """Edit a contact."""
    fields: dict = {}
    for key, value in (
        ("display_name", display_name),
        ("first_name", first),
        ("last_name", last),
        ("company", company),
        ("notes", notes),
    ):
        if value is not None:
            fields[key] = value
    if not fields:
        ui.error("nothing to change: pass at least one option (see --help).")
        raise typer.Exit(1)
    data = fetch(ctx, api.update, contact_id, fields)
    ui.emit_write(data, ctx.obj, message=f"updated contact {contact_id}")


@app.command()
def rm(
    ctx: typer.Context,
    contact_id: int = typer.Argument(..., help="Contact id (see `fbx contacts list`)."),
) -> None:
    """Delete a contact."""
    data = fetch(ctx, api.delete, contact_id)
    ui.emit_write(data, ctx.obj, message=f"deleted contact {contact_id}")


def _contacts_table(items: list) -> Table:
    t = Table(box=None, title=f"Contacts — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Company")
    t.add_column("Numbers")
    for c in sorted(items, key=lambda c: str(c.get("display_name") or "").lower()):
        numbers = c.get("numbers") or []
        shown = ", ".join(str(n.get("number")) for n in numbers if n.get("number"))
        name = c.get("display_name") or " ".join(
            str(x) for x in [c.get("first_name"), c.get("last_name")] if x
        )
        t.add_row(
            str(c.get("id", "")),
            fmt.safe(name),
            fmt.safe(c.get("company")),
            fmt.safe(shown),
        )
    return t
