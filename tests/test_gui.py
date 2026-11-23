import os
from types import SimpleNamespace

import pytest

from asciio import Diagram, Element, storage
from asciio.editor import Editor

pytestmark = pytest.mark.skipif(
    os.environ.get("PASCIIO_GUI_TESTS") != "1",
    reason="Set PASCIIO_GUI_TESTS=1 under Xvfb",
)


@pytest.fixture
def desktop():
    from asciio import gui

    assert gui.Gtk.init_check()[0], "A display (or xvfb-run) is required"
    window = gui.Window([Editor()])
    errors = []
    window.message = lambda title, text, **kwargs: errors.append((title, text))
    yield gui, window, errors
    window.destroy()
    while gui.Gtk.events_pending():
        gui.Gtk.main_iteration_do(False)


def flush(gui):
    while gui.Gtk.events_pending():
        gui.Gtk.main_iteration_do(False)


def test_real_gtk_canvas_keyboard_drag_save_and_tabs(desktop, tmp_path):
    gui, window, errors = desktop
    window.perform("@box")
    window.perform("set text 'GTK test'")
    canvas = window.canvas
    event = SimpleNamespace(keyval=gui.Gdk.KEY_l, state=0)
    canvas.key(canvas, event)
    assert window.editor.selected[0].x == 3
    element = window.editor.selected[0]
    px = (element.x + 1 - canvas.origin[0]) * canvas.cell_width + 1
    py = (element.y + 1 - canvas.origin[1]) * canvas.cell_height + 1
    press = SimpleNamespace(
        x=px,
        y=py,
        button=1,
        state=0,
        type=gui.Gdk.EventType.BUTTON_PRESS,
    )
    canvas.press(canvas, press)
    canvas.release(
        canvas,
        SimpleNamespace(
            x=px + 3 * canvas.cell_width,
            y=py + 2 * canvas.cell_height,
            button=1,
        ),
    )
    assert (element.x, element.y) == (6, 4)
    window.perform("undo")
    assert window.editor.selected[0].x == 3
    window.perform(f"save '{tmp_path / 'gui.pasciio'}'")
    window.perform("@new")
    assert window.notebook.get_n_pages() == 2
    window.notebook.set_current_page(0)
    flush(gui)
    assert window.editor.selected[0].text == "GTK test"
    assert storage.load(tmp_path / "gui.pasciio").elements[0].text == "GTK test"
    assert not errors


def mouse_event(gui, canvas, point, *, state=0):
    return SimpleNamespace(
        x=(point[0] - canvas.origin[0] + 0.5) * canvas.cell_width,
        y=(point[1] - canvas.origin[1] + 0.5) * canvas.cell_height,
        button=1,
        state=state,
        type=gui.Gdk.EventType.BUTTON_PRESS,
    )


def drag(gui, canvas, start, end):
    canvas.press(canvas, mouse_event(gui, canvas, start))
    canvas.motion(canvas, mouse_event(gui, canvas, end))
    flush(gui)
    canvas.release(canvas, mouse_event(gui, canvas, end))


@pytest.mark.parametrize("handle", ["n", "s", "w", "e", "nw", "ne", "sw", "se"])
def test_mouse_resize_handles_keep_opposite_edges_and_undo_once(desktop, handle):
    gui, window, errors = desktop
    element = window.editor.add(text="resize me", width=20, height=8)
    window.refresh()
    canvas = window.canvas
    start = canvas.resize_handles(element)[handle]
    dx, dy = (-3 if "w" in handle else 3), (-2 if "n" in handle else 2)
    before = window.editor.diagram.to_dict()
    old_right, old_bottom = element.x + element.width, element.y + element.height
    drag(gui, canvas, start, (start[0] + dx, start[1] + dy))
    assert element.width == 20 + (3 if "w" in handle or "e" in handle else 0)
    assert element.height == 8 + (2 if "n" in handle or "s" in handle else 0)
    if "w" in handle:
        assert element.x + element.width == old_right
    if "n" in handle:
        assert element.y + element.height == old_bottom
    assert canvas.drag_start is None
    window.editor.undo()
    assert window.editor.diagram.to_dict() == before
    window.editor.redo()
    assert window.editor.diagram.to_dict() != before
    assert not errors


def test_mouse_connect_resize_move_and_native_round_trip(desktop, tmp_path):
    gui, window, errors = desktop
    source = window.editor.add(text="source", width=16, height=7)
    window.editor.cursor = (36, 12)
    target = window.editor.add(text="target", width=16, height=7)
    window.editor.select({source.id})
    window.refresh()
    canvas = window.canvas
    drag(gui, canvas, source.anchor("right"), target.anchor("left"))
    diagram = window.editor.diagram
    arrow = window.editor.selected[0]
    assert arrow.kind == "arrow"
    assert len(diagram.connections) == 2
    assert diagram.points(arrow) == [source.anchor("right"), target.anchor("left")]
    window.editor.select({target.id})
    window.refresh()
    start = canvas.resize_handles(target)["se"]
    drag(gui, canvas, start, (start[0] + 3, start[1] + 4))
    assert diagram.points(arrow)[-1] == target.anchor("left")
    start = (target.x + 1, target.y + 1)
    drag(gui, canvas, start, (start[0] + 5, start[1] + 2))
    assert diagram.points(arrow)[-1] == target.anchor("left")
    path = tmp_path / "mouse.pasciio"
    window.editor.save(path)
    restored = storage.load(path)
    assert restored.points(restored.get(arrow.id)) == diagram.points(arrow)
    assert not errors


def test_mouse_reconnects_arrow_endpoint_and_detaches_only_dragged_end(desktop):
    gui, window, errors = desktop
    source = window.editor.add(text="source")
    window.editor.cursor = (30, 2)
    target = window.editor.add(text="target")
    window.editor.cursor = (30, 15)
    other = window.editor.add(text="other")
    arrow = window.editor.link(source, target)
    window.refresh()
    canvas = window.canvas
    before = window.editor.diagram.to_dict()
    drag(gui, canvas, target.anchor("left"), (other.x, other.y + 1))
    assert window.editor.diagram.points(arrow)[-1] == other.anchor("left")
    assert len(window.editor.diagram.connections) == 2
    window.editor.undo()
    assert window.editor.diagram.to_dict() == before
    window.editor.redo()
    arrow = window.editor.diagram.get(arrow.id)
    drag(gui, canvas, window.editor.diagram.points(arrow)[-1], (65, 20))
    assert window.editor.diagram.points(arrow)[-1] == (65, 20)
    assert [(c.endpoint, c.target) for c in window.editor.diagram.connections] == [
        ("start", source.id),
    ]
    assert not errors


def test_mouse_escape_and_invalid_connection_drop_leave_document_unchanged(desktop):
    gui, window, errors = desktop
    source = window.editor.add(text="source")
    window.refresh()
    canvas = window.canvas
    before = window.editor.diagram.to_dict()
    start = canvas.resize_handles(source)["se"]
    canvas.press(canvas, mouse_event(gui, canvas, start))
    canvas.motion(canvas, mouse_event(gui, canvas, (20, 20)))
    canvas.key(canvas, SimpleNamespace(keyval=gui.Gdk.KEY_Escape, state=0))
    assert canvas.drag_start is None
    assert not canvas.release(canvas, mouse_event(gui, canvas, (20, 20)))
    drag(gui, canvas, source.anchor("right"), (50, 30))
    assert window.editor.diagram.to_dict() == before
    assert window.editor.selection == {source.id}
    assert not errors


def test_mouse_negative_resize_keeps_coordinates_stable_until_release(desktop):
    gui, window, errors = desktop
    element = window.editor.add(text="resize", width=20, height=8)
    window.refresh()
    canvas = window.canvas
    origin = canvas.origin
    start = canvas.resize_handles(element)["nw"]
    canvas.press(canvas, mouse_event(gui, canvas, start))
    canvas.motion(canvas, mouse_event(gui, canvas, (-10, -5)))
    window.refresh()
    flush(gui)
    assert canvas.origin == origin
    assert element.x == 2  # Preview must not mutate the diagram.
    canvas.release(canvas, mouse_event(gui, canvas, (-10, -5)))
    assert (element.x, element.y) == (-10, -5)
    assert canvas.origin == (-12, -7)
    assert not errors


def test_mouse_control_toggle_and_rectangle_selection_still_work(desktop):
    gui, window, errors = desktop
    source = window.editor.add(text="one", width=16, height=6)
    window.editor.cursor = (24, 10)
    target = window.editor.add(text="two", width=16, height=6)
    window.editor.select({source.id})
    window.refresh()
    canvas = window.canvas
    event = mouse_event(
        gui, canvas, (target.x + 1, target.y + 1), state=gui.Gdk.ModifierType.CONTROL_MASK
    )
    canvas.press(canvas, event)
    canvas.release(canvas, event)
    assert window.editor.selection == {source.id, target.id}
    drag(gui, canvas, (0, 0), (42, 18))
    assert window.editor.selection == {source.id, target.id}
    assert not errors


def test_canvas_draws_unicode_and_exports_real_png(desktop, tmp_path):
    gui, window, errors = desktop
    window.editor.diagram = Diagram(
        [
            Element(text="\u754c e\u0301", title="Unicode", style="unicode"),
        ]
    )
    window.refresh()
    flush(gui)
    path = tmp_path / "diagram.png"
    gui.export_png(window.editor.diagram, path)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(path.read_bytes()) > 100
    assert not errors


def test_closing_dirty_tab_can_cancel_or_save(desktop, monkeypatch, tmp_path):
    gui, window, errors = desktop
    window.perform("@box")
    page = window.notebook.get_nth_page(0)
    monkeypatch.setattr(gui.Gtk.MessageDialog, "run", lambda _: gui.Gtk.ResponseType.CANCEL)
    window.close_tab(page)
    assert window.notebook.get_nth_page(0) == page
    destination = tmp_path / "saved.pasciio"
    monkeypatch.setattr(gui.Gtk.MessageDialog, "run", lambda _: gui.Gtk.ResponseType.YES)
    monkeypatch.setattr(window, "file_dialog", lambda *args, **kwargs: str(destination))
    window.close_tab(page)
    assert destination.exists()
    assert not window.editor.dirty
    assert not errors
