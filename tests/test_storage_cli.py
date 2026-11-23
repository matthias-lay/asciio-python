import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from asciio import Diagram, Element, storage
from asciio.bindings import Bindings


def test_native_extension_and_failed_save_preserve_existing_content(monkeypatch, tmp_path):
    path = tmp_path / "diagram.pasciio"
    diagram = Diagram([Element(text="old")])
    storage.save(diagram, path)
    previous = path.read_bytes()
    diagram.elements[0].text = "new"

    def fail(source, destination):
        raise OSError("replacement failed")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError, match="replacement failed"):
        storage.save(diagram, path)
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]
    with pytest.raises(ValueError, match=".pasciio"):
        storage.save(diagram, tmp_path / "diagram.asciio")
    with pytest.raises(ValueError, match=".pasciio"):
        storage.save(diagram, tmp_path / "diagram.json")


def test_malformed_and_perl_files_fail_without_execution(tmp_path):
    path = tmp_path / "bad.pasciio"
    for content in (
        b"application/x-asciioBZhfake",
        b"not a document",
        b'{"format":"asciio-python","version":999,"elements":[],"connections":[]}',
        b'{"format":"asciio-python","version":1,"elements":[{}],"connections":[{}]}',
    ):
        path.write_bytes(content)
        with pytest.raises(ValueError):
            storage.load(path)


def test_text_and_svg_exports_escape_xml_and_do_not_offer_json(tmp_path):
    diagram = storage.from_text("<hello>&\nworld")
    storage.export(diagram, tmp_path / "out.txt")
    assert (tmp_path / "out.txt").read_text() == "<hello>&\nworld\n"
    storage.export(diagram, tmp_path / "out.svg")
    svg = ET.fromstring((tmp_path / "out.svg").read_text())
    assert svg.tag.endswith("svg")
    assert "<hello>&" in "".join(svg.itertext())
    with pytest.raises(ValueError, match="Export requires"):
        storage.export(diagram, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_key_sequences_overrides_and_invalid_configuration(tmp_path):
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps({"Ctrl+b": "box", "z x": ""}))
    bindings = Bindings(path)
    assert bindings.feed("y") is None
    assert bindings.feed("y") == "copy"
    assert bindings.feed("Ctrl+b") == "box"
    assert bindings.feed("z") is None
    assert bindings.feed("Escape") == "select none"
    assert bindings.pending == ""
    assert "z x" not in bindings.mapping
    path.write_text("[]")
    with pytest.raises(ValueError):
        Bindings(path)


def run_cli(*args, input=None):
    return subprocess.run(
        [sys.executable, "-m", "asciio", *args],
        input=input,
        text=True,
        capture_output=True,
        timeout=15,
    )


def test_cli_import_edit_render_and_errors(tmp_path):
    path = tmp_path / "new.pasciio"
    result = run_cli("import-text", "-o", str(path), input="hello\nworld\n")
    assert result.returncode == 0, result.stderr
    assert run_cli("render", str(path)).stdout == "hello\nworld\n"
    edited = tmp_path / "edited.pasciio"
    result = run_cli(
        "edit",
        str(path),
        "-c",
        "select all",
        "-c",
        "move 3 2",
        "-o",
        str(edited),
    )
    assert result.returncode == 0, result.stderr
    assert run_cli("render", str(edited), "--crop").stdout == "hello\nworld\n"
    assert run_cli("render", str(edited)).stdout == "\n\n   hello\n   world\n"
    assert run_cli("render", str(tmp_path / "missing.pasciio")).returncode == 2
    result = run_cli("tui", str(path), input="")
    assert result.returncode == 2
    assert "interactive terminal" in result.stderr


def test_real_console_converters_and_python_scripting(tmp_path):
    interpreter_dir = Path(os.environ.get("PASCIIO_BIN_DIR", Path(sys.executable).parent))
    path = tmp_path / "converted.pasciio"
    result = subprocess.run(
        [str(interpreter_dir / "text_to_asciio"), "-o", str(path)],
        input="console test",
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [str(interpreter_dir / "asciio_to_text"), str(path)],
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "console test\n"
    example = Path(__file__).parents[1] / "examples" / "architecture.py"
    generated = tmp_path / "architecture.pasciio"
    result = run_cli("run", str(example), "-o", str(generated))
    assert result.returncode == 0, result.stderr
    diagram = storage.load(generated)
    assert len(diagram.elements) == 7
    assert len(diagram.connections) == 6
    assert "Browser" in diagram.render()
