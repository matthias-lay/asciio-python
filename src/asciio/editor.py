"""Shared editing actions, selection, clipboard, and transactional history."""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from . import storage
from .model import ARROWS, KINDS, Diagram, Element, new_id
from .text import Point


class Editor:
    def __init__(self, diagram: Diagram | None = None) -> None:
        self.diagram = diagram if diagram is not None else Diagram()
        self.selection: set[str] = set()
        self.cursor: Point = (2, 2)
        self.path: Path | None = None
        self._undo: list[tuple[dict[str, Any], set[str]]] = []
        self._redo: list[tuple[dict[str, Any], set[str]]] = []
        self._clipboard: Diagram | None = None
        self._saved = self.diagram.to_dict()

    @property
    def dirty(self) -> bool:
        return self.diagram.to_dict() != self._saved

    @property
    def selected(self) -> list[Element]:
        return [e for e in self.diagram.elements if e.id in self.selection]

    @contextmanager
    def change(self) -> Iterator[None]:
        before = self.diagram.to_dict()
        selection = self.selection.copy()
        try:
            yield
            self.diagram.validate()
        except Exception:
            self.diagram = Diagram.from_dict(before)
            self.selection = selection
            raise
        if before != self.diagram.to_dict():
            self._undo.append((before, selection))
            del self._undo[:-200]
            self._redo.clear()

    def undo(self) -> None:
        if self._undo:
            self._redo.append((self.diagram.to_dict(), self.selection.copy()))
            data, self.selection = self._undo.pop()
            self.diagram = Diagram.from_dict(data)

    def redo(self) -> None:
        if self._redo:
            self._undo.append((self.diagram.to_dict(), self.selection.copy()))
            data, self.selection = self._redo.pop()
            self.diagram = Diagram.from_dict(data)

    def select(self, ids: set[str], *, toggle: bool = False) -> None:
        for element_id in ids:
            self.diagram.get(element_id)
        groups = {self.diagram.get(i).group for i in ids} - {None}
        ids = ids | {e.id for e in self.diagram.elements if e.group in groups}
        if toggle:
            self.selection ^= ids
        else:
            self.selection = ids

    def cycle(self, step: int = 1) -> None:
        elements = self.diagram.elements
        if elements:
            indexes = [i for i, e in enumerate(elements) if e.id in self.selection]
            current = indexes[-1] if indexes else (-1 if step > 0 else 0)
            self.select({elements[(current + step) % len(elements)].id})

    def add(self, kind: str = "box", text: str = "", **kwargs: Any) -> Element:
        element = Element(kind=kind, x=self.cursor[0], y=self.cursor[1], text=text, **kwargs)
        with self.change():
            self.diagram.elements.append(element)
            self.selection = {element.id}
        return element

    def move(self, dx: int, dy: int) -> None:
        with self.change():
            # Freeze connected endpoint positions before detaching a moved arrow.
            for element in self.selected:
                if element.kind in ARROWS:
                    points = self.diagram.points(element)
                    element.points = [(x - element.x, y - element.y) for x, y in points]
            self.diagram.connections = [
                c
                for c in self.diagram.connections
                if c.arrow not in self.selection or c.target in self.selection
            ]
            for element in self.selected:
                element.x += dx
                element.y += dy

    def delete(self) -> None:
        with self.change():
            # Preserve endpoint positions on surviving arrows when deleting their targets.
            for element in self.diagram.elements:
                if element.kind in ARROWS and element.id not in self.selection:
                    points = self.diagram.points(element)
                    element.points = [(x - element.x, y - element.y) for x, y in points]
            self.diagram.elements = [e for e in self.diagram.elements if e.id not in self.selection]
            self.diagram.connections = [
                c
                for c in self.diagram.connections
                if c.arrow not in self.selection and c.target not in self.selection
            ]
            self.selection.clear()

    def resize(self, dw: int, dh: int) -> None:
        with self.change():
            for element in self.selected:
                if element.kind in ARROWS:
                    x, y = element.points[-1]
                    element.points[-1] = (x + dw, y + dh)
                else:
                    element.width = max(0, element.width + dw)
                    element.height = max(0, element.height + dh)
                    element.fit()

    def set(self, name: str, value: Any) -> None:
        if name not in {f.name for f in fields(Element)} - {"id", "group"}:
            raise ValueError(f"Unknown or protected property: {name}")
        with self.change():
            for element in self.selected:
                updated = asdict(element)
                updated[name] = value
                replacement = Element(**updated)
                self.diagram.elements[self.diagram.elements.index(element)] = replacement

    def group(self, *, ungroup: bool = False) -> None:
        group_id = None if ungroup else new_id()
        with self.change():
            for element in self.selected:
                element.group = group_id

    def order(self, *, front: bool) -> None:
        with self.change():
            chosen = self.selected
            rest = [e for e in self.diagram.elements if e.id not in self.selection]
            self.diagram.elements = rest + chosen if front else chosen + rest

    def align(self, mode: str) -> None:
        if mode not in ("left", "right", "top", "bottom", "horizontal", "vertical"):
            raise ValueError("Alignment: left, right, top, bottom, horizontal, vertical")
        if len(self.selected) < 2:
            return
        with self.change():
            left, top, right, bottom = self.diagram.bounds(self.selection)
            for element in self.selected:
                x1, y1, x2, y2 = self.diagram.bounds({element.id})
                dx = {
                    "left": left - x1,
                    "right": right - x2,
                    "vertical": (left + right - x1 - x2) // 2,
                }.get(mode, 0)
                dy = {
                    "top": top - y1,
                    "bottom": bottom - y2,
                    "horizontal": (top + bottom - y1 - y2) // 2,
                }.get(mode, 0)
                element.x += dx
                element.y += dy

    def distribute(self, axis: str) -> None:
        if axis not in ("horizontal", "vertical"):
            raise ValueError("Distribution: horizontal or vertical")
        coordinate = "x" if axis == "horizontal" else "y"
        dimension = "width" if axis == "horizontal" else "height"
        elements = sorted(self.selected, key=lambda e: getattr(e, coordinate))
        if len(elements) < 3:
            return
        with self.change():
            first, last = elements[0], elements[-1]
            available = getattr(last, coordinate) - getattr(first, coordinate)
            occupied = sum(getattr(e, dimension) for e in elements[:-1])
            gap = (available - occupied) / (len(elements) - 1)
            position = float(getattr(first, coordinate))
            for element in elements[1:-1]:
                previous = elements[elements.index(element) - 1]
                position += getattr(previous, dimension) + gap
                setattr(element, coordinate, round(position))

    def copy(self) -> None:
        elements = deepcopy(self.selected)
        for element in elements:
            if element.kind in ARROWS:
                element.points = [
                    (x - element.x, y - element.y) for x, y in self.diagram.points(element)
                ]
        connections = deepcopy(
            [
                c
                for c in self.diagram.connections
                if c.arrow in self.selection and c.target in self.selection
            ]
        )
        self._clipboard = Diagram(elements, connections, self.diagram.cross_mode)

    def paste(self, source: Diagram | None = None) -> None:
        source = source if source is not None else self._clipboard
        if source is None or not source.elements:
            raise ValueError("Clipboard is empty")
        copy = deepcopy(source)
        left, top, _, _ = copy.bounds()
        ids = {e.id: new_id() for e in copy.elements}
        groups = {e.group: new_id() for e in copy.elements if e.group is not None}
        for element in copy.elements:
            element.id = ids[element.id]
            element.group = groups.get(element.group) if element.group else None
            element.x += self.cursor[0] - left
            element.y += self.cursor[1] - top
        for connection in copy.connections:
            connection.arrow = ids[connection.arrow]
            connection.target = ids[connection.target]
        with self.change():
            self.diagram.elements.extend(copy.elements)
            self.diagram.connections.extend(copy.connections)
            self.selection = {e.id for e in copy.elements}

    def duplicate(self) -> None:
        if not self.selected:
            return
        self.copy()
        left, top, _, _ = self.diagram.bounds(self.selection)
        old_cursor = self.cursor
        self.cursor = (left + 2, top + 1)
        try:
            self.paste()
        finally:
            self.cursor = old_cursor

    def link(
        self, source: Element, target: Element, start: str = "right", end: str = "left"
    ) -> Element:
        arrow = Element(kind="arrow", x=source.x, y=source.y)
        with self.change():
            self.diagram.elements.append(arrow)
            self.diagram.connect(arrow, "start", source, start)
            self.diagram.connect(arrow, "end", target, end)
            self.selection = {arrow.id}
        return arrow

    def find(self, text: str) -> None:
        self.select({e.id for e in self.diagram.elements if text in e.text or text in e.title})

    def replace(self, old: str, new: str) -> None:
        if not old:
            raise ValueError("Search text cannot be empty")
        with self.change():
            for element in self.selected:
                updated = asdict(element)
                updated["text"] = element.text.replace(old, new)
                updated["title"] = element.title.replace(old, new)
                self.diagram.elements[self.diagram.elements.index(element)] = Element(**updated)

    def refresh_exec(self) -> None:
        targets = [e for e in self.selected if e.kind == "exec-box"]
        if not targets:
            raise ValueError("Select an exec-box first")
        results = []
        for element in targets:
            if not element.command:
                raise ValueError("Set command to a JSON array of executable and arguments first")
            result = subprocess.run(
                element.command,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            if len(result.stdout) > 1_000_000:
                raise ValueError("Command output exceeds 1 MB")
            results.append((element.id, result.stdout.rstrip("\n")))
        with self.change():
            for element_id, text in results:
                element = self.diagram.get(element_id)
                updated = asdict(element)
                updated["text"] = text
                self.diagram.elements[self.diagram.elements.index(element)] = Element(**updated)

    def open(self, path: str | Path) -> None:
        diagram = storage.load(path)
        self.diagram = diagram
        self.path = Path(path).expanduser()
        self._saved = diagram.to_dict()
        self.selection.clear()
        self._undo.clear()
        self._redo.clear()

    def save(self, path: str | Path | None = None) -> None:
        destination = Path(path).expanduser() if path is not None else self.path
        if destination is None:
            raise ValueError("Use save <filename> for a new diagram")
        storage.save(self.diagram, destination)
        self.path = destination
        self._saved = self.diagram.to_dict()

    def execute(self, command: str) -> str:
        args = shlex.split(command)
        if not args:
            return ""
        verb, *args = args
        counts = {
            "move": 2,
            "resize": 2,
            "set": 2,
            "align": 1,
            "distribute": 1,
            "find": 1,
            "replace": 2,
            "save": (0, 1),
            "export": 1,
            "open": 1,
            "group": 0,
            "ungroup": 0,
            "front": 0,
            "back": 0,
            "delete": 0,
            "undo": 0,
            "redo": 0,
            "copy": 0,
            "paste": 0,
            "duplicate": 0,
            "refresh": 0,
            "shrink": 0,
            "cross": 0,
            "select": (1, 100000),
            "link": (0, 2),
            "route": (2, 10000),
            "stencil-save": 1,
            "stencil-load": 1,
        }
        if verb in KINDS:
            self.add(verb, " ".join(args))
        elif verb in counts:
            limits = counts[verb]
            low, high = limits if isinstance(limits, tuple) else (limits, limits)
            if not low <= len(args) <= high:
                raise ValueError(
                    f"{verb} expects {low}" + (f"-{high}" if high != low else "") + " argument(s)"
                )
            if verb in ("move", "resize"):
                getattr(self, verb)(int(args[0]), int(args[1]))
            elif verb == "set":
                name, value = args
                if name in (
                    "width",
                    "height",
                    "x",
                    "y",
                    "points",
                    "command",
                    "transparent",
                    "vertical_first",
                    "diagonal",
                    "start_head",
                    "end_head",
                ):
                    value = json.loads(value)
                self.set(name, value)
            elif verb == "select":
                if args == ["all"]:
                    self.select({e.id for e in self.diagram.elements})
                elif args == ["none"]:
                    self.select(set())
                else:
                    self.select({self.resolve_id(arg) for arg in args})
            elif verb == "link":
                selected = [e for e in self.selected if e.kind not in ARROWS]
                if len(selected) != 2:
                    raise ValueError("Select exactly two non-arrow elements")
                if len(args) == 1:
                    raise ValueError("link takes zero or two anchor names")
                self.link(
                    selected[0],
                    selected[1],
                    args[0] if args else "right",
                    args[1] if args else "left",
                )
            elif verb == "route":
                try:
                    points = [tuple(map(int, arg.split(","))) for arg in args]
                except ValueError as error:
                    raise ValueError("route expects relative x,y pairs") from error
                self.set("points", points)
            elif verb == "open":
                if self.dirty:
                    raise ValueError("Unsaved changes: save before opening another diagram")
                self.open(args[0])
            elif verb == "save":
                self.save(args[0] if args else None)
            elif verb == "export":
                storage.export(self.diagram, args[0])
            elif verb == "group" or verb == "ungroup":
                self.group(ungroup=verb == "ungroup")
            elif verb in ("front", "back"):
                self.order(front=verb == "front")
            elif verb in ("align", "distribute", "find"):
                getattr(self, verb)(args[0])
            elif verb == "replace":
                self.replace(*args)
            elif verb == "shrink":
                with self.change():
                    for element in self.selected:
                        element.fit(shrink=True)
            elif verb == "refresh":
                self.refresh_exec()
            elif verb == "cross":
                with self.change():
                    self.diagram.cross_mode = not self.diagram.cross_mode
            elif verb == "stencil-save":
                if not self.selected:
                    raise ValueError("Select elements to save as a stencil")
                self.copy()
                assert self._clipboard is not None
                storage.save(self._clipboard, args[0])
            elif verb == "stencil-load":
                self.paste(storage.load(args[0]))
            else:
                getattr(self, verb)()
        else:
            raise ValueError(f"Unknown command: {verb}")
        return f"{verb}: {len(self.selection)} selected"

    def resolve_id(self, prefix: str) -> str:
        matches = [e.id for e in self.diagram.elements if e.id.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"Element ID {prefix!r} is missing or ambiguous")
        return matches[0]
