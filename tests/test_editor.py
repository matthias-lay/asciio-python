import subprocess
import sys

import pytest

from asciio import Diagram, Element
from asciio.editor import Editor


def linked():
    a = Element(x=2, y=3, text="A")
    b = Element(x=30, y=3, text="B")
    editor = Editor(Diagram([a, b]))
    arrow = editor.link(a, b)
    return editor, a.id, b.id, arrow.id


def test_connections_follow_moves_resizes_and_text_edits():
    editor, a, b, arrow = linked()
    editor.select({b})
    editor.move(4, 5)
    assert editor.diagram.points(editor.diagram.get(arrow))[-1] == editor.diagram.get(b).anchor(
        "left"
    )
    editor.set("text", "a substantially wider title")
    editor.resize(0, 5)
    assert editor.diagram.points(editor.diagram.get(arrow))[-1] == editor.diagram.get(b).anchor(
        "left"
    )
    editor.select({a, b, arrow})
    before = editor.diagram.points(editor.diagram.get(arrow))
    editor.move(-3, -2)
    assert editor.diagram.points(editor.diagram.get(arrow)) == [(x - 3, y - 2) for x, y in before]
    assert len(editor.diagram.connections) == 2


def test_moving_a_bound_arrow_detaches_without_jumping():
    editor, _, _, arrow = linked()
    before = editor.diagram.points(editor.diagram.get(arrow))
    editor.move(3, -2)
    assert not editor.diagram.connections
    assert editor.diagram.points(editor.diagram.get(arrow)) == [(x + 3, y - 2) for x, y in before]


def test_resize_from_top_left_clamps_to_content_and_preserves_opposite_corner():
    editor = Editor()
    element = editor.add(text="minimum", width=25, height=10)
    right, bottom = element.x + element.width, element.y + element.height
    before = editor.diagram.to_dict()
    editor.resize_element(element.id, "nw", 100, 100)
    assert element.width == len("minimum") + 4
    assert element.height == 3
    assert (element.x + element.width, element.y + element.height) == (right, bottom)
    editor.undo()
    assert editor.diagram.to_dict() == before


def test_invalid_endpoint_target_rolls_back_both_connections_and_geometry():
    editor, _, _, arrow = linked()
    before = editor.diagram.to_dict()
    with pytest.raises(ValueError, match="non-arrow"):
        editor.set_endpoint(arrow, "end", (100, 100), editor.diagram.get(arrow), "top")
    assert editor.diagram.to_dict() == before


def test_target_deletion_freezes_surviving_arrow_and_is_undoable():
    editor, a, _, arrow = linked()
    before = editor.diagram.points(editor.diagram.get(arrow))
    editor.select({a})
    editor.delete()
    assert editor.diagram.points(editor.diagram.get(arrow)) == before
    assert len(editor.diagram.connections) == 1
    editor.undo()
    assert editor.diagram.get(a)
    assert len(editor.diagram.connections) == 2


def test_copy_paste_remaps_ids_groups_and_internal_connections():
    editor, a, b, arrow = linked()
    editor.select({a, b, arrow})
    editor.group()
    original_group = editor.diagram.get(a).group
    editor.copy()
    editor.cursor = (50, 20)
    editor.paste()
    assert len(editor.diagram.elements) == 6
    assert len(editor.diagram.connections) == 4
    assert not {a, b, arrow} & editor.selection
    assert len({e.group for e in editor.selected}) == 1
    assert editor.selected[0].group != original_group
    editor.diagram.validate()
    editor.undo()
    assert len(editor.diagram.elements) == 3
    editor.redo()
    assert len(editor.diagram.elements) == 6


def test_copying_only_a_connected_arrow_preserves_its_visible_geometry():
    editor, _, _, arrow = linked()
    before = editor.diagram.points(editor.diagram.get(arrow))
    left = min(x for x, _ in before)
    top = min(y for _, y in before)
    editor.copy()
    editor.cursor = (50, 20)
    editor.paste()
    assert editor.diagram.points(editor.selected[0]) == [
        (x - left + 50, y - top + 20) for x, y in before
    ]
    assert len(editor.diagram.connections) == 2


def test_failed_change_rolls_back_document_selection_and_history():
    editor = Editor()
    element = editor.add(text="before")
    before = editor.diagram.to_dict()
    with pytest.raises(ValueError):
        with editor.change():
            editor.diagram.elements.append(Element(id=element.id))
            editor.selection.clear()
    assert editor.diagram.to_dict() == before
    assert editor.selection == {element.id}
    editor.undo()
    assert not editor.diagram.elements


def test_dirty_state_follows_save_undo_redo_and_branching(tmp_path):
    editor = Editor()
    editor.add(text="A")
    editor.save(tmp_path / "diagram.pasciio")
    assert not editor.dirty
    editor.move(1, 0)
    assert editor.dirty
    editor.undo()
    assert not editor.dirty
    editor.redo()
    assert editor.dirty
    editor.undo()
    editor.set("text", "B")
    editor.redo()
    assert editor.selected[0].text == "B"
    editor.open(tmp_path / "diagram.pasciio")
    editor.undo()
    assert len(editor.diagram.elements) == 1
    assert not editor.dirty


def test_group_selection_alignment_and_distribution():
    elements = [Element(x=x, y=y, text="X") for x, y in [(0, 0), (9, 2), (30, 4)]]
    editor = Editor(Diagram(elements))
    editor.select({e.id for e in elements})
    editor.align("top")
    assert {e.y for e in editor.selected} == {0}
    editor.distribute("horizontal")
    assert [e.x for e in editor.selected] == [0, 15, 30]
    editor.group()
    editor.select({elements[0].id})
    assert len(editor.selection) == 3
    editor.group(ungroup=True)
    editor.select({elements[0].id})
    assert len(editor.selection) == 1


def test_commands_validate_input_and_stencil_round_trip(tmp_path):
    editor = Editor()
    editor.execute("box 'hello world'")
    editor.execute("set style unicode")
    editor.execute("set title Service")
    editor.execute("replace world Python")
    assert editor.selected[0].text == "hello Python"
    path = tmp_path / "stencil.pasciio"
    editor.execute(f"stencil-save '{path}'")
    editor.execute(f"stencil-load '{path}'")
    assert len(editor.diagram.elements) == 2
    for command in ("move 1", "set id nope", "set width true", "bogus", "route 0,0 bad"):
        before = editor.diagram.to_dict()
        with pytest.raises(ValueError):
            editor.execute(command)
        assert editor.diagram.to_dict() == before


def test_exec_boxes_run_only_on_request_and_fail_transactionally(monkeypatch, tmp_path):
    editor = Editor()
    marker = tmp_path / "executed"
    editor.add(
        "exec-box",
        "old",
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch(); print('new')",
        ],
    )
    editor.save(tmp_path / "exec.pasciio")
    editor.open(tmp_path / "exec.pasciio")
    editor.diagram.render()
    assert not marker.exists()
    editor.execute("select all")
    editor.refresh_exec()
    assert marker.exists()
    assert editor.selected[0].text == "new"
    editor.set("command", [sys.executable, "-c", "raise SystemExit(1)"])
    with pytest.raises(subprocess.CalledProcessError):
        editor.refresh_exec()
    assert editor.selected[0].text == "new"
    editor.set("command", [sys.executable, "-c", "print('not a shell | command')"])
    editor.refresh_exec()
    assert editor.selected[0].text == "not a shell | command"
