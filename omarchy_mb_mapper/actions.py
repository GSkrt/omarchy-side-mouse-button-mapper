"""Curated list of Hyprland/Omarchy actions a mouse button can be bound to.

Each Action carries a ready-to-embed Lua expression (`dispatcher_lua`) that
becomes the third argument to `o.bind(keys, description, dispatcher)` in
~/.config/hypr/bindings.lua. Two shapes are used, both real Omarchy syntax
(confirmed against /usr/share/omarchy/default/hypr/bindings/*.lua):

- Native dispatcher calls, e.g. `hl.dsp.focus({ workspace = "e+1" })`
- Plain shell commands as a quoted Lua string, e.g. `"omarchy-launch-terminal"`
  -- o.bind() auto-wraps a bare string dispatcher with hl.dsp.exec_cmd().

The CUSTOM action is a sentinel: the app prompts for a shell command at
runtime and builds its dispatcher_lua on the fly (see custom_command()).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    id: str
    category: str
    label: str
    dispatcher_lua: str | None  # None only for the CUSTOM sentinel


def _lua_string(command: str) -> str:
    """Quote a shell command as a Lua single-quoted string literal."""
    escaped = command.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


CUSTOM_ACTION_ID = "custom"

ACTIONS: list[Action] = [
    # -- Workspace -----------------------------------------------------
    Action("workspace_next", "Workspace", "Next open workspace",
           'hl.dsp.focus({ workspace = "e+1" })'),
    Action("workspace_prev", "Workspace", "Previous open workspace",
           'hl.dsp.focus({ workspace = "e-1" })'),
    Action("workspace_former", "Workspace", "Former (last used) workspace",
           'hl.dsp.focus({ workspace = "previous" })'),
    Action("scratchpad_toggle", "Workspace", "Toggle scratchpad",
           'hl.dsp.workspace.toggle_special("scratchpad")'),

    # -- Window ----------------------------------------------------------
    Action("window_close", "Window", "Close window",
           'hl.dsp.window.close()'),
    Action("window_float", "Window", "Toggle floating",
           'hl.dsp.window.float({ action = "toggle" })'),
    Action("window_fullscreen", "Window", "Toggle fullscreen",
           'hl.dsp.window.fullscreen({ mode = "fullscreen" })'),
    Action("window_cycle_next", "Window", "Cycle to next window",
           'hl.dsp.window.cycle_next()'),
    Action("window_cycle_prev", "Window", "Cycle to previous window",
           'hl.dsp.window.cycle_next({ next = false })'),
    Action("window_to_top", "Window", "Bring active window to top",
           'hl.dsp.window.bring_to_top()'),

    # -- Focus / monitors --------------------------------------------------
    Action("monitor_next", "Focus", "Focus next monitor",
           'hl.dsp.focus({ monitor = "+1" })'),
    Action("monitor_prev", "Focus", "Focus previous monitor",
           'hl.dsp.focus({ monitor = "-1" })'),

    # -- Launch (real omarchy-launch-* binaries confirmed on PATH) --------
    Action("launch_terminal", "Launch", "Launch terminal",
           _lua_string("omarchy-launch-terminal")),
    Action("launch_browser", "Launch", "Launch browser",
           _lua_string("omarchy-launch-browser")),
    Action("launch_files", "Launch", "Launch file manager (Nautilus)",
           _lua_string("omarchy-launch-nautilus")),
    Action("launch_editor", "Launch", "Launch editor",
           _lua_string("omarchy-launch-editor")),
    Action("launch_shell", "Launch", "Launch shell",
           _lua_string("omarchy-launch-shell")),

    # -- Toggle (real omarchy-toggle-* binaries confirmed on PATH) --------
    Action("toggle_nightlight", "Toggle", "Toggle night light",
           _lua_string("omarchy-toggle-nightlight")),
    Action("toggle_bar", "Toggle", "Toggle bar visibility",
           _lua_string("omarchy-toggle-bar")),
    Action("toggle_touchpad", "Toggle", "Toggle touchpad",
           _lua_string("omarchy-toggle-touchpad")),
    Action("toggle_idle", "Toggle", "Toggle idle (stay awake / allow idle)",
           _lua_string("omarchy-toggle-idle")),

    # -- Capture (real omarchy-capture-* binaries confirmed on PATH) ------
    Action("screenshot_region", "Capture", "Screenshot region",
           _lua_string("omarchy-capture-screenshot region")),
    Action("screenshot_full", "Capture", "Screenshot fullscreen",
           _lua_string("omarchy-capture-screenshot fullscreen")),

    # -- Custom -------------------------------------------------------------
    Action(CUSTOM_ACTION_ID, "Custom", "Custom shell command...", None),
]


def by_id(action_id: str) -> Action:
    for action in ACTIONS:
        if action.id == action_id:
            return action
    raise KeyError(f"No such action id: {action_id!r}")


def custom_command(command: str) -> Action:
    """Build a one-off Action for a user-supplied shell command."""
    command = command.strip()
    if not command:
        raise ValueError("Custom command must not be empty")
    return Action(CUSTOM_ACTION_ID, "Custom", command, _lua_string(command))


def categories() -> list[str]:
    seen: list[str] = []
    for action in ACTIONS:
        if action.category not in seen:
            seen.append(action.category)
    return seen
