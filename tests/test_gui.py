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
    px = (element.x - canvas.origin[0]) * canvas.cell_width + 1
    py = (element.y - canvas.origin[1]) * canvas.cell_height + 1
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
