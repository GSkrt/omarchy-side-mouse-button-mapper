"""Textual TUI: detect a mouse button, name it, pick an Omarchy action.

Flow: choose a mouse -> press "Detect" -> physically click the button on
the mouse -> name it and pick an action from the curated list (or type a
custom shell command) -> Save writes it into ~/.config/hypr/bindings.lua
via bindings_writer and reloads Hyprland. No background process is left
running afterward -- Hyprland owns the binding from then on.
"""

from __future__ import annotations

import asyncio

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

from . import actions as action_catalog
from . import bindings_writer
from . import capture


class CaptureScreen(ModalScreen[capture.ButtonEvent | None]):
    """Waits for the next button press on the chosen device."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, device: capture.MouseDevice) -> None:
        super().__init__()
        self.device = device
        self._task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="capture-dialog"):
            yield Label(f"Press a button on: {self.device.name}")
            yield Label("(Esc to cancel)")
            yield Static("Waiting for a button press...", id="capture-status")

    def on_mount(self) -> None:
        self._task = asyncio.create_task(self._wait_for_button())

    async def _wait_for_button(self) -> None:
        status = self.query_one("#capture-status", Static)
        try:
            event = await capture.capture_next_button(self.device.path, timeout=30.0)
        except capture.CaptureTimeout:
            status.update("Timed out waiting for a button press. Closing...")
            await asyncio.sleep(1.5)
            self.dismiss(None)
            return
        except PermissionError:
            status.update(
                "Permission denied reading the device.\n"
                "Run: sudo usermod -aG input $USER\nthen log out and back in."
            )
            await asyncio.sleep(4)
            self.dismiss(None)
            return
        except capture.CaptureUnavailable as exc:
            status.update(str(exc))
            await asyncio.sleep(4)
            self.dismiss(None)
            return
        self.dismiss(event)

    def action_cancel(self) -> None:
        if self._task:
            self._task.cancel()
        self.dismiss(None)


class MappingFormScreen(ModalScreen[tuple[str, str] | None]):
    """Name the detected button and pick an action for it."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, event: capture.ButtonEvent, existing_label: str = "") -> None:
        super().__init__()
        self.event = event
        self.existing_label = existing_label

    def compose(self) -> ComposeResult:
        with Vertical(id="form-dialog"):
            yield Label(f"Button: {self.event.name} (code {self.event.code})")
            yield Label("Label")
            yield Input(value=self.existing_label or self.event.name, id="label-input")
            yield Label("Action")
            yield Select(
                [(f"{a.category}: {a.label}", a.id) for a in action_catalog.ACTIONS],
                id="action-select",
                allow_blank=False,
                value=action_catalog.ACTIONS[0].id,
            )
            yield Input(
                placeholder="Shell command, e.g. omarchy-launch-terminal",
                id="command-input",
                disabled=True,
            )
            with Horizontal():
                yield Button("Save", id="save-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    @on(Select.Changed, "#action-select")
    def _action_changed(self, message: Select.Changed) -> None:
        self.query_one("#command-input", Input).disabled = (
            message.value != action_catalog.CUSTOM_ACTION_ID
        )

    @on(Button.Pressed, "#save-btn")
    def _save(self) -> None:
        label = self.query_one("#label-input", Input).value.strip() or self.event.name
        action_id = self.query_one("#action-select", Select).value
        if action_id == action_catalog.CUSTOM_ACTION_ID:
            command = self.query_one("#command-input", Input).value.strip()
            if not command:
                self.notify("Enter a shell command for the custom action.", severity="warning")
                return
            action = action_catalog.custom_command(command)
        else:
            action = action_catalog.by_id(action_id)
        self.dismiss((label, action.dispatcher_lua))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class MapperApp(App):
    """Omarchy Mouse Button Mapper."""

    TITLE = "Omarchy Mouse Button Mapper"
    CSS = """
    #capture-dialog, #form-dialog {
        width: 64;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $panel;
    }
    #device-warning {
        color: $warning;
        padding: 1 2;
    }
    """
    BINDINGS = [
        ("n", "detect", "Detect button"),
        ("d", "delete_selected", "Delete mapping"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._device_error: str | None = None
        try:
            self.devices = capture.list_mouse_devices()
        except capture.CaptureUnavailable as exc:
            self.devices = []
            self._device_error = str(exc)
        self._mappings: list[bindings_writer.Mapping] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            if self.devices:
                yield Select(
                    [(d.name, d.path) for d in self.devices],
                    id="device-select",
                    allow_blank=False,
                    value=self.devices[0].path,
                )
            else:
                yield Static(
                    self._device_error
                    or "No mouse-like input devices found. Is python-evdev installed, "
                    "and are you in the 'input' group?",
                    id="device-warning",
                )
            yield DataTable(id="mappings-table")
            with Horizontal():
                yield Button(
                    "Detect button (n)", id="detect-btn", variant="primary",
                    disabled=not self.devices,
                )
                yield Button("Delete selected (d)", id="delete-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Button", "Code", "Label", "Dispatcher")
        table.cursor_type = "row"
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        try:
            self._mappings = bindings_writer.parse_managed_mappings()
        except bindings_writer.BindingsError as exc:
            self._mappings = []
            self.notify(str(exc), severity="error", timeout=10)
            return
        for m in self._mappings:
            table.add_row(capture.button_name(m.code), str(m.code), m.label, m.dispatcher_lua)

    @property
    def selected_device(self) -> capture.MouseDevice | None:
        if not self.devices:
            return None
        select = self.query_one("#device-select", Select)
        for device in self.devices:
            if device.path == select.value:
                return device
        return self.devices[0]

    @on(Button.Pressed, "#detect-btn")
    def _detect_pressed(self) -> None:
        self.action_detect()

    def action_detect(self) -> None:
        device = self.selected_device
        if device is None:
            self.notify("No mouse device available to detect from.", severity="warning")
            return
        self.push_screen(CaptureScreen(device), self._on_captured)

    def _on_captured(self, event: capture.ButtonEvent | None) -> None:
        if event is None:
            return
        existing = next((m.label for m in self._mappings if m.code == event.code), "")
        self.push_screen(
            MappingFormScreen(event, existing_label=existing),
            lambda result: self._on_form_result(event, result),
        )

    def _on_form_result(self, event: capture.ButtonEvent, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        label, dispatcher_lua = result
        try:
            backup_path, unbind_added = bindings_writer.upsert_mapping(
                event.code, label, dispatcher_lua
            )
        except bindings_writer.BindingsError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return

        ok, output = bindings_writer.reload_and_validate()
        message = f"Saved mouse:{event.code} -> {label}. Backup: {backup_path.name}."
        if unbind_added:
            message += f" (mouse:{event.code} was already bound elsewhere; added hl.unbind.)"
        self.notify(message, severity="information" if ok else "warning", timeout=8)
        if not ok:
            self.notify(f"hyprctl reported: {output}", severity="error", timeout=12)
        self.refresh_table()

    @on(Button.Pressed, "#delete-btn")
    def _delete_pressed(self) -> None:
        self.action_delete_selected()

    def action_delete_selected(self) -> None:
        table = self.query_one(DataTable)
        if not self._mappings or table.cursor_row is None or table.cursor_row >= len(self._mappings):
            self.notify("No mapping selected.", severity="warning")
            return
        code = self._mappings[table.cursor_row].code
        backup_path = bindings_writer.remove_mapping(code)
        ok, output = bindings_writer.reload_and_validate()
        self.notify(f"Removed mouse:{code}. Backup: {backup_path.name}.", timeout=6)
        if not ok:
            self.notify(f"hyprctl reported: {output}", severity="error", timeout=12)
        self.refresh_table()


def run() -> None:
    MapperApp().run()


if __name__ == "__main__":
    run()
