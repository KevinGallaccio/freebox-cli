"""Shared widgets: the confirm gate, form and language modals, table helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from . import i18n
from .i18n import _


class ConfirmModal(ModalScreen[bool]):
    """The app-side `ui.confirm`: a y/N modal gating destructive actions.

    Push with `push_screen_wait` (from a worker); dismisses True only on an
    explicit yes. Escape and `n` both decline, mirroring the CLI's default-No.
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, message: str, *, confirm_label: str = "Confirm") -> None:
        super().__init__()
        i18n.translate_bindings(self)
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button(_("Cancel (n)"), id="cancel")
                # Callers pass their label pre-translated; only the default
                # "Confirm" still needs the catalog (a re-lookup of an
                # already-French label just misses and passes through).
                yield Button(
                    f"{_(self._confirm_label)} (y)", variant="error", id="confirm"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: str = ""
    placeholder: str = ""


class FormModal(ModalScreen["dict[str, str] | None"]):
    """A small labeled form; dismisses with `{key: value}` or None on cancel.

    Values come back as raw strings — the caller owns validation/coercion,
    exactly like a CLI command owns its option parsing.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, title: str, fields: list[Field], *, submit_label: str = "Save") -> None:
        super().__init__()
        i18n.translate_bindings(self)
        self._title = title
        self._fields = fields
        self._submit_label = submit_label

    def compose(self) -> ComposeResult:
        with Vertical(id="form-box"):
            yield Static(self._title, id="form-title")
            for f in self._fields:
                yield Label(f.label)
                yield Input(value=f.default, placeholder=f.placeholder, id=f"field-{f.key}")
            with Horizontal(id="form-buttons"):
                yield Button(_("Cancel (esc)"), id="cancel")
                yield Button(_(self._submit_label), variant="primary", id="submit")

    def _values(self) -> dict[str, str]:
        return {
            f.key: self.query_one(f"#field-{f.key}", Input).value.strip() for f in self._fields
        }

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._values() if event.button.id == "submit" else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(self._values())

    def action_cancel(self) -> None:
        self.dismiss(None)


class TextModal(ModalScreen[None]):
    """A dismissable pane of preformatted text (key reveal, tty output, …).

    The body is rendered without markup: it is verbatim box/guest output.
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        i18n.translate_bindings(self)
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        from textual.containers import VerticalScroll

        with Vertical(id="text-box"):
            yield Static(self._title, id="text-title")
            with VerticalScroll():
                text = Static(id="text-body")
                text.update(Text(self._body))
                yield text
            yield Static(f"[dim]{_('esc to close')}[/dim]")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class LanguageModal(ModalScreen["str | None"]):
    """Pick the app language; dismisses with an `i18n.LANGUAGES` code or None.

    Language names stay in their own language — the chooser must be readable
    by someone lost in the wrong one.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self) -> None:
        super().__init__()
        i18n.translate_bindings(self)

    def compose(self) -> ComposeResult:
        with Vertical(id="lang-box"):
            yield Static(_("Language"), id="lang-title")
            yield OptionList(
                *(
                    Option(
                        f"{'●' if code == i18n.lang() else '○'} {name}", id=code
                    )
                    for code, name in i18n.LANGUAGES.items()
                ),
                id="lang-list",
            )
            yield Static(f"[dim]{_('esc to close')}[/dim]")

    def on_mount(self) -> None:
        lang_list = self.query_one("#lang-list", OptionList)
        lang_list.highlighted = lang_list.get_option_index(i18n.lang())
        lang_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


def refill(table: DataTable, rows: Iterable[tuple], keys: Iterable[str] | None = None) -> None:
    """Rebuild a table's rows on refresh, keeping the cursor near its spot."""
    old_row = table.cursor_row
    table.clear()
    if keys is None:
        for row in rows:
            table.add_row(*row)
    else:
        for row, key in zip(rows, keys, strict=True):
            table.add_row(*row, key=key)
    if table.row_count:
        table.move_cursor(row=min(old_row, table.row_count - 1))


def cursor_key(table: DataTable) -> str | None:
    """The row key under the cursor (the object id refreshes preserve)."""
    if not table.row_count:
        return None
    cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
    value = cell_key.row_key.value
    return None if value is None else str(value)
