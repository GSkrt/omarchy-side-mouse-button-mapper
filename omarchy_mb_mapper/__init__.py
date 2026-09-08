"""omarchy_mb_mapper - map mouse buttons to Hyprland/Omarchy actions.

A small TUI tool: pick a mouse, press a button to identify it, name it,
choose an action from a curated Hyprland/Omarchy list (or a custom shell
command), and it writes a real `o.bind("mouse:<code>", ...)` binding into
~/.config/hypr/bindings.lua, then reloads Hyprland.
"""

__version__ = "0.1.0"
