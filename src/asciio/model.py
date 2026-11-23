"""Diagram data and geometry. No UI, filesystem, or command execution."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .text import Cells, Point, clean, pad, put, row, width

KINDS = (
    "box",
    "text",
    "ellipse",
    "rhombus",
    "if-box",
    "process-box",
    "triangle-up",
    "triangle-down",
    "arrow",
    "angled-arrow",
    "axis",
    "exec-box",
)
ARROWS = ("arrow", "angled-arrow")
STYLES = ("dash", "unicode", "double", "bold", "dot", "star")
ANCHORS = ("top", "bottom", "left", "right")
FRAMES = {
    "dash": (".", ".", "'", "'", "-", "|"),
    "unicode": ("\u256d", "\u256e", "\u2570", "\u256f", "\u2500", "\u2502"),
    "double": ("\u2554", "\u2557", "\u255a", "\u255d", "\u2550", "\u2551"),
    "bold": ("\u250f", "\u2513", "\u2517", "\u251b", "\u2501", "\u2503"),
    "dot": (".", ".", ".", ".", ".", "."),
    "star": ("*", "*", "*", "*", "*", "*"),
}
UNICODE_JOINS = {
    frozenset(("left", "right")): "\u2500",
    frozenset(("top", "bottom")): "\u2502",
    frozenset(("right", "bottom")): "\u256d",
    frozenset(("left", "bottom")): "\u256e",
    frozenset(("right", "top")): "\u2570",
    frozenset(("left", "top")): "\u256f",
    frozenset(("left", "right", "top")): "\u2534",
    frozenset(("left", "right", "bottom")): "\u252c",
    frozenset(("top", "bottom", "left")): "\u2524",
    frozenset(("top", "bottom", "right")): "\u251c",
    frozenset(ANCHORS): "\u253c",
}


def new_id() -> str:
    return uuid4().hex


def integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def direction(a: Point, b: Point) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx and dy:
        return "diagonal"
    return ("right" if dx > 0 else "left") if dx else ("bottom" if dy > 0 else "top")


def line(a: Point, b: Point) -> list[Point]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    count = max(abs(dx), abs(dy))
    if not count:
        return [a]
    return [(a[0] + round(dx * i / count), a[1] + round(dy * i / count)) for i in range(count + 1)]


def route(points: list[Point], vertical_first: bool, diagonal: bool) -> list[Point]:
    result = [points[0]]
    for target in points[1:]:
        start = result[-1]
        if diagonal or start[0] == target[0] or start[1] == target[1]:
            result.extend(line(start, target)[1:])
        else:
            corner = (start[0], target[1]) if vertical_first else (target[0], start[1])
            result.extend(line(start, corner)[1:])
            result.extend(line(corner, target)[1:])
    return result


def join_glyph(directions: set[str], style: str) -> str:
    if "diagonal" in directions:
        return "+"
    if style in ("unicode", "double", "bold"):
        if len(directions) == 1:
            return "\u2500" if directions & {"left", "right"} else "\u2502"
        return UNICODE_JOINS.get(frozenset(directions), "+")
    if style in ("dot", "star"):
        return "." if style == "dot" else "*"
    if len(directions) > 2:
        return "+"
    if not directions & {"top", "bottom"}:
        return "-"
    if not directions & {"left", "right"}:
        return "|"
    return "." if "bottom" in directions else "'"


@dataclass
class Element:
    kind: str = "box"
    x: int = 0
    y: int = 0
    text: str = ""
    title: str = ""
    width: int = 0
    height: int = 0
    style: str = "dash"
    id: str = field(default_factory=new_id)
    points: list[Point] = field(default_factory=lambda: [(0, 0), (8, 0)])
    vertical_first: bool = False
    diagonal: bool = False
    start_head: bool = False
    end_head: bool = True
    transparent: bool = False
    fill: str = " "
    foreground: str = "#202020"
    background: str = "#ffffff"
    group: str | None = None
    command: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Unknown element kind: {self.kind}")
        if self.style not in STYLES:
            raise ValueError(f"Unknown style: {self.style}")
        for name in ("id", "text", "title", "fill", "foreground", "background"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string")
        if not self.id:
            raise ValueError("Element ID cannot be empty")
        if self.group is not None and (not isinstance(self.group, str) or not self.group):
            raise ValueError("Group must be a nonempty string or null")
        for name in ("x", "y", "width", "height"):
            integer(getattr(self, name), name)
        if self.width < 0 or self.height < 0:
            raise ValueError("Dimensions cannot be negative")
        for name in (
            "vertical_first",
            "diagonal",
            "start_head",
            "end_head",
            "transparent",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        self.text, self.title = clean(self.text), clean(self.title)
        if width(self.fill) != 1 or len(self.fill) != 1 or self.fill.isspace() and self.fill != " ":
            raise ValueError("Fill must be a single display-cell character")
        for color in (self.foreground, self.background):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Colors must use #rrggbb notation")
        if not isinstance(self.points, (list, tuple)) or len(self.points) < 2:
            raise ValueError("An element must have at least two points")
        points = []
        for point in self.points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Each point must contain x and y")
            points.append((integer(point[0], "point x"), integer(point[1], "point y")))
        self.points = points
        if not isinstance(self.command, list) or not all(isinstance(s, str) for s in self.command):
            raise ValueError("Command must be an array of arguments")
        self.fit()

    def fit(self, *, shrink: bool = False) -> None:
        if self.kind in ARROWS:
            return
        body = self.text.split("\n")
        titles = self.title.split("\n") if self.title else []
        content_width = max(map(width, body + titles), default=0)
        content_height = len(body) + len(titles)
        if self.kind == "text":
            w, h = max(1, content_width), max(1, content_height)
        elif self.kind in ("box", "exec-box"):
            w = max(4, content_width + 4)
            h = max(3, content_height + 2 + bool(titles))
        elif self.kind == "rhombus":
            h = max(5, content_height * 2 + (content_width + 5) // 2)
            h += 1 - h % 2
            w = 2 * h - 1
        else:
            w, h = max(9, content_width + 8), max(5, content_height + 4)
            if self.kind.startswith("triangle"):
                h = max(h, (w + 1) // 2 + content_height)
                w = max(w, h * 2 - 1)
        self.width = w if shrink else max(w, self.width)
        self.height = h if shrink else max(h, self.height)
        if self.kind == "rhombus":
            self.height = max(self.height, (self.width + 2) // 2)
            self.height += 1 - self.height % 2
            self.width = 2 * self.height - 1
        elif self.kind in ("if-box", "process-box"):
            self.width = max(self.width, self.height + content_width + 4)
        elif self.kind.startswith("triangle"):
            self.width = max(self.width, self.height * 2 - 1)

    def anchor(self, side: str, offset: int = 0) -> Point:
        if side not in ANCHORS:
            raise ValueError(f"Unknown anchor: {side}")
        if side in ("left", "right"):
            return (
                self.x - 1 if side == "left" else self.x + self.width,
                self.y + max(0, min(self.height - 1, self.height // 2 + offset)),
            )
        return (
            self.x + max(0, min(self.width - 1, self.width // 2 + offset)),
            self.y - 1 if side == "top" else self.y + self.height,
        )

    def body_lines(self) -> list[str]:
        if self.kind == "text":
            lines = (self.title + "\n" if self.title else "").splitlines() + self.text.split("\n")
            return [pad(text, self.width) for text in lines] + [
                " " * self.width for _ in range(max(0, self.height - len(lines)))
            ]
        w, h = self.width, self.height
        tl, tr, bl, br, horizontal, vertical = FRAMES[self.style]
        body = self.text.split("\n")
        if self.kind in ("box", "exec-box"):
            result = [tl + horizontal * (w - 2) + tr]
            if self.title:
                for title in self.title.split("\n"):
                    result.append(
                        vertical + pad(title, w - 2, center=True, fill=self.fill) + vertical
                    )
                result.append(vertical + horizontal * (w - 2) + vertical)
            for text in body:
                result.append(vertical + " " + pad(text, w - 4, fill=self.fill) + " " + vertical)
            while len(result) < h - 1:
                result.append(vertical + " " + self.fill * (w - 4) + " " + vertical)
            return result + [bl + horizontal * (w - 2) + br]
        cells: Cells = {}
        center = (w - 1) / 2
        for y in range(h):
            if self.kind == "rhombus":
                half = (h - 1) // 2
                inset = abs(y - half) * 2
                left, right = inset, w - 1 - inset
                if y in (0, h - 1):
                    put(cells, max(0, left - 1), y, ",'," if y == 0 else "','")
                    continue
                if y == half:
                    a, b = ":", ":"
                elif y < half:
                    a, b = ",'", "',"
                else:
                    a, b = "',", ",'"
            elif self.kind.startswith("triangle"):
                level = y if self.kind == "triangle-up" else h - 1 - y
                inset = round(center * (1 - level / max(1, h - 1)))
                left, right = inset, w - 1 - inset
                a, b = ("/", "\\") if self.kind == "triangle-up" else ("\\", "/")
                if level == h - 1:
                    put(cells, 0, y, horizontal * w)
                    continue
            elif self.kind == "process-box":
                shift = min(y, h - 1 - y)
                left, right = shift, w - 1 - h // 2 + shift
                a, b = (")", ")") if y == h // 2 else (("\\", "\\") if y < h // 2 else ("/", "/"))
                if y in (0, h - 1):
                    put(cells, left, y, "_" * (right - left + 1))
                    continue
            elif self.kind == "if-box":
                inset = abs(y - h // 2)
                left, right = inset, w - 1 - inset
                a, b = ("(", ")") if y == h // 2 else (("/", "\\") if y < h // 2 else ("\\", "/"))
                if y in (0, h - 1):
                    a, b = (".", ".") if y == 0 else ("'", "'")
                    put(cells, left, y, a + horizontal * (right - left - 1) + b)
                    continue
            elif self.kind == "axis":
                put(cells, 0, y, "^" if y == 0 else "|")
                if y == h - 1:
                    put(cells, 0, y, "-" * (w - 1) + ">")
                continue
            else:
                ratio = (y - (h - 1) / 2) / max(1, (h - 1) / 2)
                extent = max(1, center * math.sqrt(max(0, 1 - ratio * ratio)))
                left = max(0, math.floor(center - extent))
                right = min(w - 1, math.ceil(center + extent))
                a, b = ("|", "|") if y == h // 2 else (("/", "\\") if y < h // 2 else ("\\", "/"))
                if y in (0, h - 1):
                    left, right = w // 4, w - 1 - w // 4
                    a, b = (".", ".") if y == 0 else ("'", "'")
                    put(cells, left, y, a + horizontal * max(0, right - left - 1) + b)
                    continue
            put(cells, left, y, a + self.fill * max(0, right - left - len(a)) + b)
        texts = (self.title.split("\n") if self.title else []) + body
        start = max(1, (h - len(texts)) // 2)
        if self.kind.startswith("triangle"):
            start = h - len(texts) - 2 if self.kind == "triangle-up" else 1
        for i, text in enumerate(texts):
            put(cells, max(1, (w - width(text)) // 2), start + i, text)
        return [row(cells, y, 0, w) for y in range(h)]


@dataclass
class Connection:
    arrow: str
    endpoint: str
    target: str
    anchor: str
    offset: int = 0

    def __post_init__(self) -> None:
        if not all(
            isinstance(v, str) for v in (self.arrow, self.endpoint, self.target, self.anchor)
        ):
            raise ValueError("Connection references must be strings")
        if self.endpoint not in ("start", "end") or self.anchor not in ANCHORS:
            raise ValueError("Invalid connection endpoint or anchor")
        integer(self.offset, "connection offset")


@dataclass
class Diagram:
    elements: list[Element] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    cross_mode: bool = True

    def get(self, element_id: str) -> Element:
        for element in self.elements:
            if element.id == element_id:
                return element
        raise ValueError(f"Unknown element: {element_id}")

    def validate(self) -> None:
        if type(self.cross_mode) is not bool:
            raise ValueError("cross_mode must be boolean")
        for element in self.elements:
            element.__post_init__()
        ids = [e.id for e in self.elements]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate element IDs")
        endpoints = set()
        for connection in self.connections:
            connection.__post_init__()
            arrow = self.get(connection.arrow)
            target = self.get(connection.target)
            if arrow.kind not in ARROWS or target.kind in ARROWS:
                raise ValueError("Connections must attach an arrow to a non-arrow element")
            key = (connection.arrow, connection.endpoint)
            if key in endpoints:
                raise ValueError("An arrow endpoint cannot have multiple connections")
            endpoints.add(key)

    def to_dict(self) -> dict[str, Any]:
        return {"format": "asciio-python", "version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data: Any) -> Diagram:
        if not isinstance(data, dict):
            raise ValueError("A diagram must be an object")
        if data.get("format") != "asciio-python" or type(data.get("version")) is not int:
            raise ValueError("Not an asciio-python document")
        if data["version"] != 1:
            raise ValueError(f"Unsupported document version: {data['version']}")
        if set(data) - {"format", "version", "elements", "connections", "cross_mode"}:
            raise ValueError("Unknown document fields")
        if not isinstance(data.get("elements"), list) or not isinstance(
            data.get("connections"), list
        ):
            raise ValueError("elements and connections must be arrays")
        try:
            result = cls(
                [Element(**e) for e in data["elements"]],
                [Connection(**c) for c in data["connections"]],
                data.get("cross_mode", True),
            )
        except TypeError as error:
            raise ValueError(f"Invalid document: {error}") from error
        result.validate()
        return result

    def points(self, element: Element) -> list[Point]:
        points = [(element.x + x, element.y + y) for x, y in element.points]
        for connection in self.connections:
            if connection.arrow == element.id:
                index = 0 if connection.endpoint == "start" else -1
                points[index] = self.get(connection.target).anchor(
                    connection.anchor, connection.offset
                )
        return points

    def arrow_cells(self, element: Element) -> tuple[Cells, dict[Point, set[str]]]:
        path = route(
            self.points(element),
            element.vertical_first,
            element.diagonal or element.kind == "angled-arrow",
        )
        directions: dict[Point, set[str]] = {}
        for a, b in zip(path, path[1:], strict=False):
            directions.setdefault(a, set()).add(direction(a, b))
            directions.setdefault(b, set()).add(direction(b, a))
        cells: Cells = {}
        for i, point in enumerate(path):
            dirs = directions.get(point, set())
            if "diagonal" in dirs:
                neighbor = path[i + 1] if i < len(path) - 1 else path[i - 1]
                dx, dy = neighbor[0] - point[0], neighbor[1] - point[1]
                cells[point] = "\\" if dx * dy > 0 else "/"
            else:
                cells[point] = join_glyph(dirs, element.style)
        if len(path) == 1:
            cells[path[0]] = "*"
        else:
            for index, neighbor_index, enabled in (
                (0, 1, element.start_head),
                (-1, -2, element.end_head),
            ):
                if enabled:
                    tip, neighbor = path[index], path[neighbor_index]
                    dx, dy = tip[0] - neighbor[0], tip[1] - neighbor[1]
                    cells[tip] = (
                        (">" if dx > 0 else "<") if dx and not dy else ("v" if dy > 0 else "^")
                    )
                    directions.pop(tip, None)
        return cells, directions

    def element_cells(self, element: Element) -> Cells:
        if element.kind in ARROWS:
            return self.arrow_cells(element)[0]
        cells: Cells = {}
        for y, text in enumerate(element.body_lines()):
            put(cells, element.x, element.y + y, text)
        if element.transparent:
            return {p: c for p, c in cells.items() if c != " "}
        return cells

    def cells(self, ids: set[str] | None = None) -> Cells:
        cells: Cells = {}
        arrow_dirs: dict[Point, set[str]] = {}
        for element in self.elements:
            if ids is not None and element.id not in ids:
                continue
            if element.kind in ARROWS:
                overlay, directions = self.arrow_cells(element)
            else:
                overlay, directions = self.element_cells(element), {}
            for (x, y), value in overlay.items():
                if self.cross_mode and (x, y) in arrow_dirs and (x, y) in directions:
                    dirs = arrow_dirs[x, y] | directions[x, y]
                    put(cells, x, y, join_glyph(dirs, element.style))
                    arrow_dirs[x, y] = dirs
                else:
                    if value == "\0":
                        continue
                    put(cells, x, y, value)
                    arrow_dirs.pop((x, y), None)
                    if (x, y) in directions:
                        arrow_dirs[x, y] = directions[x, y].copy()
        return cells

    def bounds(self, ids: set[str] | None = None) -> tuple[int, int, int, int]:
        cells = self.cells(ids)
        if not cells:
            return 0, 0, 1, 1
        xs, ys = zip(*cells, strict=True)
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def render(self, *, crop: bool = False, ids: set[str] | None = None) -> str:
        cells = self.cells(ids)
        if not cells:
            return ""
        left, top, right, bottom = self.bounds(ids)
        if not crop:
            left, top = 0, 0
        return "\n".join(row(cells, y, left, right).rstrip() for y in range(top, bottom)) + "\n"

    def hit(self, x: int, y: int) -> Element | None:
        for element in reversed(self.elements):
            if (x, y) in self.element_cells(element):
                return element
        return None

    def connect(self, arrow: Element, endpoint: str, target: Element, anchor: str) -> None:
        connection = Connection(arrow.id, endpoint, target.id, anchor)
        if arrow.kind not in ARROWS or target.kind in ARROWS:
            raise ValueError("Connections must attach an arrow to a non-arrow element")
        self.get(arrow.id)
        self.get(target.id)
        self.connections = [
            c for c in self.connections if (c.arrow, c.endpoint) != (arrow.id, endpoint)
        ] + [connection]
