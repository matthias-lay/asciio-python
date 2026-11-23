"""Display-cell aware text operations."""

from collections.abc import Iterator

from wcwidth import iter_graphemes, wcswidth, wcwidth

Point = tuple[int, int]
Cells = dict[Point, str]
CONTINUATION = "\0"


def clean(text: str) -> str:
    text = text.expandtabs(4)
    if any(wcwidth(c) < 0 and c != "\n" for c in text):
        raise ValueError("Text contains a control character")
    for line in text.split("\n"):
        for _ in clusters(line):
            pass
    return text


def width(text: str) -> int:
    return wcswidth(text)


def clusters(text: str) -> Iterator[tuple[str, int]]:
    for cluster in iter_graphemes(text):
        size = wcswidth(cluster)
        if size <= 0:
            raise ValueError("A combining character must follow a base character")
        yield cluster, size


def put(cells: Cells, x: int, y: int, text: str) -> None:
    for cluster, size in clusters(text):
        # Erase the entire previous wide glyph, not just its overwritten half.
        if cells.get((x, y)) == CONTINUATION:
            cells.pop((x - 1, y), None)
        if cells.get((x + size, y)) == CONTINUATION:
            cells.pop((x + size, y), None)
        cells[x, y] = cluster
        for offset in range(1, size):
            cells[x + offset, y] = CONTINUATION
        x += size


def pad(text: str, size: int, *, center: bool = False, fill: str = " ") -> str:
    extra = max(0, size - width(text))
    left = extra // 2 if center else 0
    return fill * left + text + fill * (extra - left)


def row(cells: Cells, y: int, left: int, right: int) -> str:
    result = []
    for x in range(left, right):
        value = cells.get((x, y), " ")
        if value == CONTINUATION:
            if x == left:
                result.append(" ")
        elif width(value) > 1 and x + width(value) > right:
            result.append(" ")
        else:
            result.append(value)
    return "".join(result)
