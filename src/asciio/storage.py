"""Versioned native documents and text/SVG export."""

from __future__ import annotations

import json
import os
import tempfile
from html import escape
from pathlib import Path

from .model import Diagram, Element
from .text import width


def atomic_write(path: str | Path, text: str) -> None:
    destination = Path(path).expanduser()
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            os.chmod(temporary, destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def save(diagram: Diagram, path: str | Path) -> None:
    if Path(path).suffix.lower() != ".pasciio":
        raise ValueError("Native diagrams and stencils must use the .pasciio extension")
    diagram.validate()
    atomic_write(path, json.dumps(diagram.to_dict(), ensure_ascii=False, indent=2) + "\n")


def load(path: str | Path) -> Diagram:
    raw = Path(path).expanduser().read_bytes()
    if raw.startswith((b"application/x-asciio", b"BZh", b"=\xf3rl", b"=srl")):
        raise ValueError(
            "This is a Perl/Sereal Asciio file. This application uses its own native "
            "format and does not support Perl Asciio files."
        )
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON document: {error}") from error
    return Diagram.from_dict(data)


def from_text(text: str, *, box: bool = False) -> Diagram:
    return Diagram([Element(kind="box" if box else "text", text=text.rstrip("\n"))])


def svg(diagram: Diagram) -> str:
    lines = diagram.render(crop=True).splitlines()
    w, h = max(map(width, lines), default=1), max(1, len(lines))
    body = "\n".join(
        f'<text x="8" y="{20 + i * 18}" xml:space="preserve">{escape(text)}</text>'
        for i, text in enumerate(lines)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * 10 + 16}" '
        f'height="{h * 18 + 16}" viewBox="0 0 {w * 10 + 16} {h * 18 + 16}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        '<g font-family="DejaVu Sans Mono,monospace" font-size="16" fill="#202020">\n'
        f"{body}\n</g>\n</svg>\n"
    )


def export(diagram: Diagram, path: str | Path, *, crop: bool = False) -> None:
    suffix = Path(path).suffix.lower()
    if suffix == ".svg":
        atomic_write(path, svg(diagram))
    elif suffix in (".txt", ".asc"):
        atomic_write(path, diagram.render(crop=crop))
    else:
        raise ValueError("Export requires a .txt, .asc, or .svg filename")
