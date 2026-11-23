"""Shared vim-like key sequences with JSON overrides."""

import json
import os
from pathlib import Path

from .editor import Editor

DEFAULTS = {
    "h": "move -1 0",
    "j": "move 0 1",
    "k": "move 0 -1",
    "l": "move 1 0",
    "Left": "move -1 0",
    "Right": "move 1 0",
    "Up": "move 0 -1",
    "Down": "move 0 1",
    "Shift+Left": "@cursor-left",
    "Shift+Right": "@cursor-right",
    "Shift+Up": "@cursor-up",
    "Shift+Down": "@cursor-down",
    "1": "resize -1 0",
    "2": "resize 0 1",
    "3": "resize 0 -1",
    "4": "resize 1 0",
    "Tab": "@next",
    "Shift+Tab": "@previous",
    "Escape": "select none",
    "V": "select all",
    "d": "delete",
    "Delete": "delete",
    "u": "undo",
    "Ctrl+r": "redo",
    "Ctrl+z": "undo",
    "Ctrl+y": "redo",
    "Return": "@edit",
    ":": "@command",
    "?": "@help",
    "b": "@box",
    "t": "@text",
    "a a": "@arrow",
    "a d": "@direction",
    "a f": "@reverse",
    "y y": "copy",
    "p p": "paste",
    "Ctrl+c": "copy",
    "Ctrl+v": "paste",
    "Ctrl+d": "duplicate",
    "g g": "group",
    "g u": "ungroup",
    "g f": "front",
    "g b": "back",
    "A t": "align top",
    "A l": "align left",
    "A b": "align bottom",
    "A r": "align right",
    "A h": "align horizontal",
    "A v": "align vertical",
    "z x": "cross",
    "z g": "@grid",
    "z r": "@rulers",
    "Ctrl+s": "@save",
    "Ctrl+o": "@open",
    "Ctrl+n": "@new",
    "Ctrl+q": "@quit",
    "/": "@find",
    "+": "@zoom-in",
    "-": "@zoom-out",
}


class Bindings:
    def __init__(self, path: Path | None = None) -> None:
        self.mapping = DEFAULTS.copy()
        if path is None:
            path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            path = path / "asciio-python" / "bindings.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not all(
                isinstance(k, str) and k and isinstance(v, str) for k, v in data.items()
            ):
                raise ValueError("bindings.json must map key sequences to command strings")
            for key, command in data.items():
                if command:
                    self.mapping[key] = command
                else:
                    self.mapping.pop(key, None)
        self.pending = ""

    def feed(self, key: str) -> str | None:
        if key == "Escape":
            self.pending = ""
        sequence = f"{self.pending} {key}".strip()
        if sequence in self.mapping:
            self.pending = ""
            return self.mapping[sequence]
        if any(binding.startswith(sequence + " ") for binding in self.mapping):
            self.pending = sequence
        else:
            self.pending = ""
        return None


def special_action(editor: Editor, action: str) -> bool:
    if action in ("@next", "@previous"):
        editor.cycle(1 if action == "@next" else -1)
    elif action.startswith("@cursor-"):
        dx, dy = {
            "@cursor-left": (-1, 0),
            "@cursor-right": (1, 0),
            "@cursor-up": (0, -1),
            "@cursor-down": (0, 1),
        }[action]
        editor.cursor = (editor.cursor[0] + dx, editor.cursor[1] + dy)
    elif action == "@direction":
        with editor.change():
            for element in editor.selected:
                element.vertical_first = not element.vertical_first
    elif action == "@reverse":
        with editor.change():
            for element in editor.selected:
                if element.kind in ("arrow", "angled-arrow"):
                    element.start_head, element.end_head = element.end_head, element.start_head
    else:
        return False
    return True
