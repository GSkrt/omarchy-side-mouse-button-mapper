"""Mouse device discovery and raw button-press capture via python-evdev.

Reading /dev/input/eventX requires either root or membership in the `input`
group (`sudo usermod -aG input $USER`, then log out/in). We don't attempt to
sudo/pkexec our way around that here -- a persistent, unprivileged capability
is the right fix for a tool you'll reach for repeatedly, and PermissionError
is surfaced with that instruction instead of silently escalating.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

try:
    import evdev
    from evdev import ecodes
except ImportError as exc:  # pragma: no cover - exercised only without the dep
    evdev = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class CaptureUnavailable(RuntimeError):
    pass


class CaptureTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class MouseDevice:
    path: str
    name: str


@dataclass(frozen=True)
class ButtonEvent:
    code: int
    name: str


def _require_evdev() -> None:
    if evdev is None:
        raise CaptureUnavailable(
            "python-evdev is not installed. Install it with: "
            "sudo pacman -S python-evdev"
        ) from _IMPORT_ERROR


# BTN_MOUSE..BTN_TASK (0x110-0x117) is the standard mouse button range;
# BTN_TRIGGER_HAPPY* covers oddball extra buttons some mice expose.
_MOUSE_BUTTON_LOW = 0x110
_MOUSE_BUTTON_HIGH = 0x117


def _is_button_code(code: int) -> bool:
    return _MOUSE_BUTTON_LOW <= code <= _MOUSE_BUTTON_HIGH or 0x2C0 <= code <= 0x2CF


def list_mouse_devices() -> list[MouseDevice]:
    """Return input devices that look like a mouse (expose BTN_LEFT)."""
    _require_evdev()
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        caps = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.BTN_LEFT in caps and ecodes.REL_X in dev.capabilities().get(ecodes.EV_REL, []):
            devices.append(MouseDevice(path=path, name=dev.name))
        dev.close()
    return devices


def button_name(code: int) -> str:
    _require_evdev()
    name = ecodes.keys.get(code)
    if isinstance(name, list):
        name = name[0]
    return name or f"CODE_{code}"


async def capture_next_button(device_path: str, timeout: float = 15.0) -> ButtonEvent:
    """Block (async) until a mouse button is pressed on `device_path`.

    Reports the button on press (value == 1), ignoring release/repeat and
    non-button events (motion, scroll). Raises CaptureTimeout if nothing is
    pressed within `timeout` seconds, or PermissionError if the device node
    isn't readable by the current user.
    """
    _require_evdev()
    dev = evdev.InputDevice(device_path)
    try:
        async def _read():
            async for event in dev.async_read_loop():
                if event.type == ecodes.EV_KEY and event.value == 1 and _is_button_code(event.code):
                    return ButtonEvent(code=event.code, name=button_name(event.code))
            raise CaptureTimeout("Device closed before a button was pressed")

        try:
            return await asyncio.wait_for(_read(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise CaptureTimeout(
                f"No button press detected within {timeout:.0f}s"
            ) from exc
    finally:
        dev.close()
