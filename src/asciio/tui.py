"""Curses terminal editor; uses the same model and actions as GTK."""

from __future__ import annotations

import curses
import locale
import shlex
import subprocess

from .bindings import Bindings, special_action
from .editor import Editor
from .text import CONTINUATION, clusters


def terminal_key(key: str | int) -> str:
    special = {
        curses.KEY_LEFT: "Left",
        curses.KEY_RIGHT: "Right",
        curses.KEY_UP: "Up",
        curses.KEY_DOWN: "Down",
        curses.KEY_DC: "Delete",
        curses.KEY_BTAB: "Shift+Tab",
        curses.KEY_ENTER: "Return",
        "\n": "Return",
        "\r": "Return",
        "\t": "Tab",
        "\x1b": "Escape",
    }
    if key in special:
        return special[key]
    if isinstance(key, str):
        if len(key) == 1 and 0 < ord(key) < 27:
            return f"Ctrl+{chr(ord(key) + 96)}"
        return key
    return ""


class Terminal:
    def __init__(self, screen, editor: Editor) -> None:
        self.screen = screen
        self.editor = editor
        self.bindings = Bindings()
        self.offset = (0, 0)
        self.message = "b box | t text | Tab select | Enter edit | : command | ? help"
        self.running = True
        self.grid = False
        self.rulers = False
        curses.curs_set(0)
        curses.raw()
        curses.noecho()
        screen.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS)

    def write(self, y: int, x: int, text: str, attributes: int = 0) -> None:
        rows, columns = self.screen.getmaxyx()
        if not (0 <= y < rows and 0 <= x < columns):
            return
        visible = []
        size = 0
        for cluster, cell_width in clusters(text):
            if x + size + cell_width >= columns:
                break
            visible.append(cluster)
            size += cell_width
        if visible:
            self.screen.addstr(y, x, "".join(visible), attributes)

    def draw(self) -> None:
        self.screen.erase()
        rows, columns = self.screen.getmaxyx()
        left, top = self.offset
        if self.grid:
            for y in range(1, max(1, rows - 2)):
                self.write(y, 0, "." * max(0, columns - 1), curses.A_DIM)
        selected_cells: set[tuple[int, int]] = set()
        for element in self.editor.selected:
            selected_cells.update(self.editor.diagram.element_cells(element))
        for (x, y), char in sorted(
            self.editor.diagram.cells().items(), key=lambda item: item[0][1]
        ):
            if char != CONTINUATION and 0 <= x - left < columns - 1 and 0 <= y - top < rows - 3:
                attr = curses.A_REVERSE if (x, y) in selected_cells else curses.A_NORMAL
                self.write(y - top + 1, x - left, char, attr)
        if self.rulers:
            self.write(
                0,
                0,
                "".join(
                    str((left + x) // 10 % 10) if (left + x) % 10 == 0 else " "
                    for x in range(max(0, columns - 1))
                ),
                curses.A_DIM,
            )
        else:
            self.write(
                0, 0, "Asciio Python | " + str(self.editor.path or "Untitled"), curses.A_BOLD
            )
        chosen = ", ".join(f"{e.kind}:{e.id[:6]}" for e in self.editor.selected)
        marker = "*" if self.editor.dirty else ""
        self.write(
            rows - 2, 0, f"{marker} cursor {self.editor.cursor} | {chosen}", curses.A_REVERSE
        )
        self.write(rows - 1, 0, self.bindings.pending or self.message)
        self.screen.refresh()

    def prompt(self, label: str, initial: str = "") -> str | None:
        text = initial
        curses.curs_set(1)
        try:
            while True:
                rows, _ = self.screen.getmaxyx()
                self.screen.move(max(0, rows - 1), 0)
                self.screen.clrtoeol()
                self.write(rows - 1, 0, label + text)
                self.screen.refresh()
                key = self.screen.get_wch()
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return text
                if key == "\x1b":
                    return None
                if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    text = text[:-1]
                elif isinstance(key, str) and key.isprintable():
                    text += key
        finally:
            curses.curs_set(0)

    def confirm_discard(self) -> bool:
        if not self.editor.dirty:
            return True
        return self.prompt("Discard unsaved changes? Type yes: ") == "yes"

    def help(self) -> None:
        self.screen.erase()
        rows, _ = self.screen.getmaxyx()
        lines = [
            "ASCIIO PYTHON -- press any key to return",
            "b / t: insert box / text at cursor; Tab / Shift+Tab: cycle selection",
            "h j k l / arrows: move selected; 1 2 3 4: resize; Enter: edit text",
            "V: select all; Escape: deselect; d: delete; u: undo; Ctrl+r: redo",
            "yy / pp: copy / paste; Ctrl+d: duplicate; gg / gu: group / ungroup",
            "Mouse: click to select and place cursor; Ctrl+arrows may vary by terminal",
            ": starts a command; quote arguments containing spaces using 'single quotes'",
            "Examples:",
            "  ellipse 'database'       |  set title 'API'    |  set style unicode",
            "  select <id> <id>         |  link right left    |  route 0,0 6,0 6,5",
            "  save diagram.pasciio     |  export diagram.svg |  open diagram.pasciio",
            "  find 'old'               |  replace 'old' 'new'|  align top",
            "  stencil-save block.pasciio | stencil-load block.pasciio",
            "  set command '[\"date\"]'  |  refresh (exec-box; runs explicit commands)",
            "  cursor 20 10             |  pan 10 5           |  quit / quit!",
            "Full command reference is in README.md.",
        ]
        for i, text in enumerate(lines[: max(1, rows - 1)]):
            self.write(i, 0, text)
        self.screen.refresh()
        self.screen.get_wch()

    def command(self, command: str) -> None:
        args = shlex.split(command)
        if args and args[0] in ("quit", "q", "quit!", "q!"):
            if args[0].endswith("!") or self.confirm_discard():
                self.running = False
        elif args and args[0] in ("cursor", "pan"):
            if len(args) != 3:
                raise ValueError(f"{args[0]} requires x and y")
            point = (int(args[1]), int(args[2]))
            if args[0] == "cursor":
                self.editor.cursor = point
            else:
                self.offset = point
        else:
            self.message = self.editor.execute(command)

    def action(self, action: str) -> None:
        if special_action(self.editor, action):
            return
        if not action.startswith("@"):
            self.message = self.editor.execute(action)
        elif action == "@command":
            command = self.prompt(":")
            if command is not None:
                self.command(command)
        elif action == "@help":
            self.help()
        elif action in ("@box", "@text", "@arrow"):
            self.editor.add(action[1:])
        elif action == "@edit":
            if len(self.editor.selected) != 1:
                raise ValueError("Select exactly one element to edit")
            text = self.prompt(
                "Text (use \\n for line breaks): ",
                self.editor.selected[0].text.replace("\n", "\\n"),
            )
            if text is not None:
                self.editor.set("text", text.replace("\\n", "\n"))
        elif action == "@find":
            text = self.prompt("Find: ")
            if text is not None:
                self.editor.find(text)
        elif action == "@save":
            path = str(self.editor.path) if self.editor.path else self.prompt("Save as: ")
            if path:
                self.editor.save(path)
        elif action == "@open":
            if self.confirm_discard():
                path = self.prompt("Open: ")
                if path:
                    self.editor.open(path)
        elif action == "@new":
            if self.confirm_discard():
                self.editor = Editor()
        elif action == "@quit":
            if self.confirm_discard():
                self.running = False
        elif action == "@grid":
            self.grid = not self.grid
        elif action == "@rulers":
            self.rulers = not self.rulers
        elif action in ("@zoom-in", "@zoom-out"):
            self.message = "Terminal font size is controlled by your terminal emulator"
        else:
            raise ValueError(f"Unknown interface action: {action}")

    def run(self) -> None:
        while self.running:
            self.draw()
            key = self.screen.get_wch()
            try:
                if key == curses.KEY_RESIZE:
                    continue
                if key == curses.KEY_MOUSE:
                    _, x, y, _, state = curses.getmouse()
                    if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                        x, y = x + self.offset[0], y - 1 + self.offset[1]
                        self.editor.cursor = (x, y)
                        hit = self.editor.diagram.hit(x, y)
                        self.editor.select(
                            {hit.id} if hit else set(), toggle=bool(state & curses.BUTTON_CTRL)
                        )
                else:
                    action = self.bindings.feed(terminal_key(key))
                    if action is not None:
                        self.action(action)
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                self.message = f"Error: {error}"


def run(editor: Editor) -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(lambda screen: Terminal(screen, editor).run())
