"""Shared widgets: the confirm gate and small display helpers."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


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
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel (n)", id="cancel")
                yield Button(f"{self._confirm_label} (y)", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
