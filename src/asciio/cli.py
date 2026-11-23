"""Console entry points; graphical dependencies are loaded only when needed."""

from __future__ import annotations

import argparse
import runpy
import subprocess
import sys
from pathlib import Path

from . import __version__, storage
from .editor import Editor


def graphical():
    try:
        from . import gui
    except (ImportError, ValueError) as error:
        raise ValueError(
            "GTK3 support is unavailable. Install the system PyGObject, Cairo, and GTK3 "
            "introspection packages (see README.md), or use tasciio. "
            f"Details: {error}"
        ) from error
    return gui


def editor_for(path: str | None) -> Editor:
    editor = Editor()
    if path:
        editor.open(path)
    return editor


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="asciio-python",
        description="ASCII/Unicode diagram editor in Python",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="action", required=True)
    gui = commands.add_parser("gui", help="Open the GTK3 desktop editor")
    gui.add_argument("files", nargs="*")
    tui = commands.add_parser("tui", help="Open the terminal editor")
    tui.add_argument("file", nargs="?")
    render = commands.add_parser("render", help="Convert a .pasciio diagram to text, SVG, or PNG")
    render.add_argument("file")
    render.add_argument("-o", "--output", help="Output .txt/.asc/.svg/.png; defaults to stdout")
    render.add_argument("--crop", action="store_true", help="Remove empty canvas margins")
    importer = commands.add_parser("import-text", help="Create a .pasciio diagram from UTF-8 text")
    importer.add_argument("file", nargs="?", default="-", help="Input text file, or - for stdin")
    importer.add_argument("-o", "--output", required=True, help="Destination .pasciio file")
    importer.add_argument("--box", action="store_true", help="Wrap text in an editable box")
    batch = commands.add_parser("edit", help="Apply shared editor commands without a UI")
    batch.add_argument("file", nargs="?")
    batch.add_argument("-c", "--command", action="append", required=True)
    batch.add_argument("-o", "--output", required=True, help="Destination .pasciio file")
    script = commands.add_parser("run", help="Execute a trusted Python diagram-generation script")
    script.add_argument("script")
    script.add_argument("-i", "--input", help="Initial .pasciio diagram")
    script.add_argument("-o", "--output", required=True, help="Destination .pasciio file")
    return result


def dispatch(argv: list[str] | None = None) -> None:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        if args.action == "gui":
            graphical().run([editor_for(path) for path in args.files])
        elif args.action == "tui":
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError("The terminal editor requires an interactive terminal")
            from .tui import run

            run(editor_for(args.file))
        elif args.action == "render":
            diagram = storage.load(args.file)
            if args.output:
                if Path(args.output).suffix.lower() == ".png":
                    graphical().export_png(diagram, args.output)
                else:
                    storage.export(diagram, args.output, crop=args.crop)
            else:
                sys.stdout.write(diagram.render(crop=args.crop))
        elif args.action == "import-text":
            text = (
                sys.stdin.read()
                if args.file == "-"
                else Path(args.file).read_text(encoding="utf-8")
            )
            storage.save(storage.from_text(text, box=args.box), args.output)
        elif args.action == "edit":
            editor = editor_for(args.file)
            for command in args.command:
                editor.execute(command)
            editor.save(args.output)
        elif args.action == "run":
            editor = editor_for(args.input)
            runpy.run_path(args.script, init_globals={"editor": editor}, run_name="__main__")
            editor.save(args.output)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        arguments.exit(2, f"{arguments.prog}: error: {error}\n")
    except KeyboardInterrupt:
        arguments.exit(130, "Interrupted\n")


def main() -> None:
    dispatch()


def gui_main() -> None:
    dispatch(["gui", *sys.argv[1:]])


def tui_main() -> None:
    dispatch(["tui", *sys.argv[1:]])


def to_text_main() -> None:
    dispatch(["render", *sys.argv[1:]])


def from_text_main() -> None:
    dispatch(["import-text", *sys.argv[1:]])
