"""Safely read/write mouse-button bindings in ~/.config/hypr/bindings.lua.

Everything this tool writes lives inside one clearly marked, machine-managed
block so it never touches bindings the user wrote by hand elsewhere in the
file. Each managed line is tagged with a trailing `-- omarchy_mb_mapper`
comment, which is what parsing keys off -- the block markers alone are not
enough because Lua has no concept of "read this region only".

Per the Omarchy skill's re-binding rule: if a bare `mouse:<code>` key is
already bound *outside* our managed block (e.g. hand-written by the user),
we must add `hl.unbind("mouse:<code>")` before our own `o.bind(...)`, or
Hyprland will keep both bindings active. We do that automatically and report
it back to the caller so the UI can tell the user.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

BINDINGS_PATH = Path.home() / ".config" / "hypr" / "bindings.lua"

START_MARKER = "-- === omarchy_mb_mapper: managed mouse bindings (edit via the app, not by hand) ==="
END_MARKER = "-- === end omarchy_mb_mapper ==="
LINE_TAG = "-- omarchy_mb_mapper"

_MANAGED_LINE_RE = re.compile(
    r'^o\.bind\("mouse:(?P<code>\d+)",\s*"(?P<label>(?:[^"\\]|\\.)*)",\s*'
    r"(?P<dispatcher>.+?)\)\s*-- omarchy_mb_mapper\s*$"
)
_UNBIND_LINE_RE = re.compile(r'^hl\.unbind\("mouse:(?P<code>\d+)"\)\s*-- omarchy_mb_mapper\s*$')
_BARE_MOUSE_KEY_RE_TMPL = r'"mouse:{code}"'


class BindingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mapping:
    code: int
    label: str
    dispatcher_lua: str


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _escape_label(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')


def read_text() -> str:
    if not BINDINGS_PATH.exists():
        raise BindingsError(
            f"{BINDINGS_PATH} does not exist. Is this an Omarchy system with "
            "Hyprland config initialized?"
        )
    return BINDINGS_PATH.read_text()


def backup() -> Path:
    ts = int(time.time())
    backup_path = BINDINGS_PATH.with_name(f"{BINDINGS_PATH.name}.bak.{ts}")
    shutil.copy2(BINDINGS_PATH, backup_path)
    return backup_path


def _split_managed_block(text: str) -> tuple[str, list[str], str]:
    """Return (before, managed_lines, after). managed_lines is [] if absent."""
    lines = text.splitlines()
    try:
        start = lines.index(START_MARKER)
        end = lines.index(END_MARKER, start + 1)
    except ValueError:
        return text, [], ""

    before = "\n".join(lines[:start])
    managed = lines[start + 1:end]
    after = "\n".join(lines[end + 1:])
    return before, managed, after


def parse_managed_mappings(text: str | None = None) -> list[Mapping]:
    text = text if text is not None else read_text()
    _, managed_lines, _ = _split_managed_block(text)
    mappings = []
    for line in managed_lines:
        m = _MANAGED_LINE_RE.match(line.strip())
        if m:
            mappings.append(
                Mapping(
                    code=int(m.group("code")),
                    label=_unescape(m.group("label")),
                    dispatcher_lua=m.group("dispatcher"),
                )
            )
    return mappings


def _has_bare_conflict_outside_managed(before: str, after: str, code: int) -> bool:
    pattern = re.compile(_BARE_MOUSE_KEY_RE_TMPL.format(code=code))
    return bool(pattern.search(before) or pattern.search(after))


def _render_managed_block(mappings: list[Mapping], unbind_codes: set[int]) -> list[str]:
    if not mappings:
        return []
    lines = [START_MARKER]
    for code in sorted(unbind_codes):
        lines.append(f'hl.unbind("mouse:{code}") {LINE_TAG}')
    for m in mappings:
        lines.append(
            f'o.bind("mouse:{m.code}", "{_escape_label(m.label)}", {m.dispatcher_lua}) {LINE_TAG}'
        )
    lines.append(END_MARKER)
    return lines


def upsert_mapping(code: int, label: str, dispatcher_lua: str) -> tuple[Path, bool]:
    """Add or replace the mapping for `code`. Returns (backup_path, unbind_added)."""
    text = read_text()
    before, managed_lines, after = _split_managed_block(text)

    existing = parse_managed_mappings(text)
    existing_unbinds = {
        int(_UNBIND_LINE_RE.match(l.strip()).group("code"))
        for l in managed_lines
        if _UNBIND_LINE_RE.match(l.strip())
    }

    conflict = _has_bare_conflict_outside_managed(before, after, code)
    unbind_codes = set(existing_unbinds)
    if conflict:
        unbind_codes.add(code)

    new_mappings = [m for m in existing if m.code != code]
    new_mappings.append(Mapping(code=code, label=label, dispatcher_lua=dispatcher_lua))
    new_mappings.sort(key=lambda m: m.code)

    backup_path = backup()
    new_block = _render_managed_block(new_mappings, unbind_codes)
    _write_with_block(before, new_block, after)
    return backup_path, conflict


def remove_mapping(code: int) -> Path:
    text = read_text()
    before, managed_lines, after = _split_managed_block(text)
    existing = parse_managed_mappings(text)
    existing_unbinds = {
        int(_UNBIND_LINE_RE.match(l.strip()).group("code"))
        for l in managed_lines
        if _UNBIND_LINE_RE.match(l.strip())
    }

    new_mappings = [m for m in existing if m.code != code]
    new_unbinds = existing_unbinds - {code} if code not in {m.code for m in new_mappings} else existing_unbinds

    backup_path = backup()
    new_block = _render_managed_block(new_mappings, new_unbinds)
    _write_with_block(before, new_block, after)
    return backup_path


def _write_with_block(before: str, block_lines: list[str], after: str) -> None:
    parts = [p for p in (before.rstrip("\n"), ) if p]
    if block_lines:
        if parts:
            parts.append("")  # blank line before our block
        parts.append("\n".join(block_lines))
    tail = after.strip("\n")
    if tail:
        parts.append("")
        parts.append(tail)
    new_text = "\n".join(parts).rstrip("\n") + "\n"
    BINDINGS_PATH.write_text(new_text)


def reload_and_validate(timeout: float = 5.0) -> tuple[bool, str]:
    """Run `hyprctl reload` then `hyprctl configerrors`. Returns (ok, output)."""
    try:
        reload_proc = subprocess.run(
            ["hyprctl", "reload"], capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"Could not run hyprctl reload: {exc}"

    try:
        errors_proc = subprocess.run(
            ["hyprctl", "configerrors"], capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"Could not run hyprctl configerrors: {exc}"

    output = (reload_proc.stdout + reload_proc.stderr + errors_proc.stdout + errors_proc.stderr).strip()
    ok = errors_proc.returncode == 0 and (not output or "error" not in output.lower())
    return ok, output or "OK"
