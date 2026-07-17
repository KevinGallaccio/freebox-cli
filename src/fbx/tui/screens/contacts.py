"""Contacts: the box's address book."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from ...core.api import contacts
from ..i18n import _
from ..support import BoxCallError
from ..widgets import Field, FormModal, cursor_key, refill
from ._base import BoxScreen


def _form_fields() -> list[Field]:
    # Built per call, not at import: labels must speak the active language.
    return [
        Field("display_name", _("Display name")),
        Field("first_name", _("First name")),
        Field("last_name", _("Last name")),
        Field("company", _("Company")),
    ]


class ContactsScreen(BoxScreen):
    POLL_INTERVAL = 30.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="contacts", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#contacts", DataTable).add_columns(
            _("Name"), _("First"), _("Last"), _("Company")
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        entries = await self.box(contacts.list_all)
        self._by_id = {str(c.get("id")): c for c in entries}
        refill(
            self.query_one("#contacts", DataTable),
            [
                (
                    str(c.get("display_name") or ""),
                    str(c.get("first_name") or ""),
                    str(c.get("last_name") or ""),
                    str(c.get("company") or ""),
                )
                for c in entries
            ],
            list(self._by_id),
        )

    @staticmethod
    def _fields_from(values: dict[str, str]) -> dict:
        # display_name is required; the rest only when non-empty (same shape
        # as `fbx contacts add`).
        fields: dict = {"display_name": values["display_name"]}
        for key in ("first_name", "last_name", "company"):
            if values.get(key):
                fields[key] = values[key]
        return fields

    @work
    async def action_add(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(_("New contact"), _form_fields(), submit_label=_("Create"))
        )
        if not values or not values["display_name"]:
            return
        try:
            await self.box(contacts.create, self._fields_from(values))
        except BoxCallError:
            return
        self.notify(_("Created contact {name!r}.").format(name=values["display_name"]))
        self.run_refresh()

    @work
    async def action_edit(self) -> None:
        contact_id = cursor_key(self.query_one("#contacts", DataTable))
        if contact_id is None:
            return
        current = self._by_id.get(contact_id, {})
        values = await self.app.push_screen_wait(
            FormModal(
                _("Edit contact"),
                [
                    Field(f.key, f.label, default=str(current.get(f.key) or ""))
                    for f in _form_fields()
                ],
            )
        )
        if not values or not values["display_name"]:
            return
        try:
            await self.box(contacts.update, int(contact_id), self._fields_from(values))
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_delete(self) -> None:
        contact_id = cursor_key(self.query_one("#contacts", DataTable))
        if contact_id is None:
            return
        name = self._by_id.get(contact_id, {}).get("display_name", _("this contact"))
        if not await self.confirm(
            _("Delete contact {name!r}?").format(name=name), confirm_label=_("Delete")
        ):
            return
        try:
            await self.box(contacts.delete, int(contact_id))
        except BoxCallError:
            return
        self.run_refresh()
