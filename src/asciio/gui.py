"""GTK3 canvas and tabbed desktop editor."""

from __future__ import annotations

import json
import math
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo  # noqa: E402

from . import storage  # noqa: E402
from .bindings import Bindings, special_action  # noqa: E402
from .editor import Editor  # noqa: E402
from .model import KINDS, STYLES, Element  # noqa: E402
from .text import CONTINUATION, width  # noqa: E402


def color(context, value: str, alpha: float = 1.0) -> None:
    rgb = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    context.set_source_rgba(*rgb, alpha)


def gtk_key(event) -> str:
    key = Gdk.keyval_name(event.keyval) or ""
    if key == "ISO_Left_Tab":
        return "Shift+Tab"
    if key in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
        return ""
    unicode_key = Gdk.keyval_to_unicode(event.keyval)
    if unicode_key and chr(unicode_key).isprintable():
        key = chr(unicode_key)
    if event.state & Gdk.ModifierType.CONTROL_MASK:
        key = "Ctrl+" + key.lower()
    elif event.state & Gdk.ModifierType.SHIFT_MASK and len(key) > 1:
        key = "Shift+" + key
    return key


class Canvas(Gtk.DrawingArea):
    def __init__(self, window, editor: Editor) -> None:
        super().__init__()
        self.window = window
        self.editor = editor
        self.bindings = Bindings()
        self.zoom = 12
        self.grid = True
        self.rulers = True
        self.cell_width = 10
        self.cell_height = 20
        self.origin = (0, 0)
        self.drag_start: tuple[int, int] | None = None
        self.drag_end: tuple[int, int] | None = None
        self.drag_move = False
        self.set_can_focus(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.connect("draw", self.draw)
        self.connect("button-press-event", self.press)
        self.connect("button-release-event", self.release)
        self.connect("motion-notify-event", self.motion)
        self.connect("key-press-event", self.key)
        self.connect("scroll-event", self.scroll)
        self.refresh()

    def refresh(self) -> None:
        layout = self.create_pango_layout("M")
        layout.set_font_description(Pango.FontDescription(f"DejaVu Sans Mono {self.zoom}"))
        self.cell_width, self.cell_height = layout.get_pixel_size()
        left, top, right, bottom = self.editor.diagram.bounds()
        self.origin = (min(-2, left - 2), min(-2, top - 2))
        self.set_size_request(
            max(1000, (right - self.origin[0] + 30) * self.cell_width),
            max(700, (bottom - self.origin[1] + 20) * self.cell_height),
        )
        self.queue_draw()

    def point(self, event) -> tuple[int, int]:
        return (
            math.floor(event.x / self.cell_width) + self.origin[0],
            math.floor(event.y / self.cell_height) + self.origin[1],
        )

    def draw(self, widget, context) -> bool:
        context.set_source_rgb(0.98, 0.98, 0.98)
        context.paint()
        cw, ch = self.cell_width, self.cell_height
        ox, oy = self.origin
        x1, y1, x2, y2 = context.clip_extents()
        if self.grid:
            context.set_source_rgb(0.80, 0.82, 0.84)
            for y in range(int(y1 // ch), int(y2 // ch) + 1):
                for x in range(int(x1 // cw), int(x2 // cw) + 1):
                    context.rectangle(x * cw + cw / 2, y * ch + ch / 2, 1, 1)
            context.fill()
        owners = {}
        for element in self.editor.diagram.elements:
            owners.update({p: element for p in self.editor.diagram.element_cells(element)})
        layout = self.create_pango_layout("")
        layout.set_font_description(Pango.FontDescription(f"DejaVu Sans Mono {self.zoom}"))
        for (x, y), char in self.editor.diagram.cells().items():
            px, py = (x - ox) * cw, (y - oy) * ch
            if char == CONTINUATION or px < x1 - cw * 2 or px > x2 or py < y1 - ch or py > y2:
                continue
            owner = owners.get((x, y))
            if owner is not None:
                color(context, owner.background)
                context.rectangle(px, py, max(1, width(char)) * cw, ch)
                context.fill()
                color(context, owner.foreground)
            else:
                color(context, "#202020")
            layout.set_text(char, -1)
            context.move_to(px, py)
            PangoCairo.show_layout(context, layout)
        color(context, "#2674c9", 0.20)
        for element in self.editor.selected:
            left, top, right, bottom = self.editor.diagram.bounds({element.id})
            context.rectangle(
                (left - ox) * cw, (top - oy) * ch, (right - left) * cw, (bottom - top) * ch
            )
            context.fill()
        if self.drag_start is not None and self.drag_end is not None:
            a, b = self.drag_start, self.drag_end
            color(context, "#2674c9", 0.8)
            context.set_line_width(1)
            context.rectangle(
                (min(a[0], b[0]) - ox) * cw,
                (min(a[1], b[1]) - oy) * ch,
                (abs(a[0] - b[0]) + 1) * cw,
                (abs(a[1] - b[1]) + 1) * ch,
            )
            context.stroke()
        cx, cy = self.editor.cursor
        color(context, "#d25128")
        context.rectangle((cx - ox) * cw, (cy - oy) * ch, cw, ch)
        context.stroke()
        if self.rulers:
            color(context, "#777777")
            for x in range(math.floor(x1 / cw / 10) * 10, int(x2 / cw) + 1, 10):
                layout.set_text(str(x + ox), -1)
                context.move_to(x * cw, y1)
                PangoCairo.show_layout(context, layout)
        return False

    def press(self, widget, event) -> bool:
        self.grab_focus()
        point = self.point(event)
        self.editor.cursor = point
        if event.button == 3:
            self.window.context_menu(event)
            return True
        if event.button != 1:
            return False
        hit = self.editor.diagram.hit(*point)
        toggle = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if hit is None:
            if not toggle:
                self.editor.select(set())
        elif hit.id not in self.editor.selection or toggle:
            self.editor.select({hit.id}, toggle=toggle)
        self.drag_start = point
        self.drag_move = hit is not None
        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            if hit is not None:
                self.window.perform("@edit")
            else:
                self.window.perform("@box")
        self.window.refresh()
        return True

    def motion(self, widget, event) -> bool:
        if self.drag_start is not None:
            self.drag_end = self.point(event)
            self.queue_draw()
        return True

    def release(self, widget, event) -> bool:
        if event.button != 1 or self.drag_start is None:
            return False
        a, b = self.drag_start, self.point(event)
        if a != b:
            if self.drag_move:
                self.editor.move(b[0] - a[0], b[1] - a[1])
            else:
                left, right = sorted((a[0], b[0]))
                top, bottom = sorted((a[1], b[1]))
                ids = set()
                for element in self.editor.diagram.elements:
                    x1, y1, x2, y2 = self.editor.diagram.bounds({element.id})
                    if x1 >= left and y1 >= top and x2 <= right + 1 and y2 <= bottom + 1:
                        ids.add(element.id)
                self.editor.select(ids)
        self.drag_start = self.drag_end = None
        self.window.refresh()
        return True

    def key(self, widget, event) -> bool:
        action = self.bindings.feed(gtk_key(event))
        if action is not None:
            self.window.perform(action)
        elif self.bindings.pending:
            self.window.status.set_text(self.bindings.pending + " ...")
        return True

    def scroll(self, widget, event) -> bool:
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            self.zoom = max(
                6, min(32, self.zoom + (1 if event.direction == Gdk.ScrollDirection.UP else -1))
            )
            self.refresh()
            return True
        return False


class Window(Gtk.Window):
    def __init__(self, editors: list[Editor]) -> None:
        super().__init__(title="Asciio Python")
        self.set_default_size(1100, 760)
        self.connect("delete-event", self.close_window)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        root.pack_start(self.menus(), False, False, 0)
        toolbar = Gtk.Box(spacing=4)
        for label, action in (
            ("Box", "@box"),
            ("Text", "@text"),
            ("Arrow", "@arrow"),
            ("Connect", "link"),
            ("Undo", "undo"),
            ("Redo", "redo"),
            ("Save", "@save"),
            ("Properties", "@edit"),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _, a=action: self.perform(a))
            toolbar.pack_start(button, False, False, 0)
        root.pack_start(toolbar, False, False, 4)
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", lambda *_: self.refresh())
        root.pack_start(self.notebook, True, True, 0)
        self.command = Gtk.Entry()
        self.command.set_placeholder_text(
            "Command, e.g. set style unicode | select all | align top | export diagram.svg"
        )
        self.command.connect("activate", self.execute_command)
        self.command.connect("key-press-event", self.command_key)
        root.pack_start(self.command, False, False, 2)
        self.status = Gtk.Label(xalign=0)
        root.pack_start(self.status, False, False, 4)
        for editor in editors or [Editor()]:
            self.add_tab(editor)
        self.show_all()

    @property
    def canvas(self) -> Canvas:
        page = self.notebook.get_nth_page(self.notebook.get_current_page())
        return page.canvas

    @property
    def editor(self) -> Editor:
        return self.canvas.editor

    def add_tab(self, editor: Editor) -> None:
        scroller = Gtk.ScrolledWindow()
        scroller.canvas = Canvas(self, editor)
        scroller.add(scroller.canvas)
        label = Gtk.Box(spacing=4)
        label.pack_start(
            Gtk.Label(label=str(editor.path.name if editor.path else "Untitled")), True, True, 0
        )
        button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", lambda _: self.close_tab(scroller))
        label.pack_start(button, False, False, 0)
        index = self.notebook.append_page(scroller, label)
        scroller.show_all()
        label.show_all()
        self.notebook.set_current_page(index)
        self.canvas.grab_focus()
        self.refresh()

    def refresh(self) -> None:
        if not hasattr(self, "status") or self.notebook.get_n_pages() == 0:
            return
        self.canvas.refresh()
        path = self.editor.path.name if self.editor.path else "Untitled"
        title = path + (" *" if self.editor.dirty else "")
        self.set_title(f"{title} - Asciio Python")
        page = self.notebook.get_nth_page(self.notebook.get_current_page())
        self.notebook.get_tab_label(page).get_children()[0].set_text(title)
        chosen = ", ".join(f"{e.kind}:{e.id[:6]}" for e in self.editor.selected)
        self.status.set_text(
            f"Cursor {self.editor.cursor} | {chosen or 'No selection'} | "
            "b box, t text, Tab select, Enter edit, : command, ? help"
        )

    def menus(self):
        bar = Gtk.MenuBar()
        sections = {
            "File": [
                ("New tab", "@new"),
                ("Open...", "@open"),
                ("Save", "@save"),
                ("Save as...", "@save-as"),
                ("Export text...", "@export-txt"),
                ("Export SVG...", "@export-svg"),
                ("Export PNG...", "@export-png"),
                ("Close tab", "@close-tab"),
                ("Quit", "@quit"),
            ],
            "Edit": [
                ("Undo", "undo"),
                ("Redo", "redo"),
                ("Copy elements", "copy"),
                ("Paste elements", "paste"),
                ("Duplicate", "duplicate"),
                ("Delete", "delete"),
                ("Select all", "select all"),
                ("Deselect", "select none"),
                ("Properties", "@edit"),
                ("Find...", "@find"),
                ("Replace...", "@replace"),
                ("Copy as text", "@copy-text"),
                ("Paste text", "@paste-text"),
            ],
            "Add": [(kind, f"@add:{kind}") for kind in KINDS],
            "Arrange": [
                ("Connect selected", "link"),
                ("Group", "group"),
                ("Ungroup", "ungroup"),
                ("Bring to front", "front"),
                ("Send to back", "back"),
                *[
                    (f"Align {mode}", f"align {mode}")
                    for mode in (
                        "left",
                        "right",
                        "top",
                        "bottom",
                        "horizontal",
                        "vertical",
                    )
                ],
                ("Distribute horizontally", "distribute horizontal"),
                ("Distribute vertically", "distribute vertical"),
                ("Shrink to text", "shrink"),
            ],
            "Stencils": [("Save selection...", "@stencil-save"), ("Insert...", "@stencil-load")],
            "View": [
                ("Grid", "@grid"),
                ("Rulers", "@rulers"),
                ("Cross mode", "cross"),
                ("Zoom in", "@zoom-in"),
                ("Zoom out", "@zoom-out"),
            ],
            "Help": [("Keyboard shortcuts", "@help")],
        }
        for title, items in sections.items():
            item = Gtk.MenuItem(label=title)
            menu = Gtk.Menu()
            for text, action in items:
                entry = Gtk.MenuItem(label=text)
                entry.connect("activate", lambda _, a=action: self.perform(a))
                menu.append(entry)
            item.set_submenu(menu)
            bar.append(item)
        return bar

    def context_menu(self, event) -> None:
        menu = Gtk.Menu()
        for label, action in (
            ("Box", "@box"),
            ("Text", "@text"),
            ("Arrow", "@arrow"),
            ("Properties", "@edit"),
            ("Connect selected", "link"),
            ("Duplicate", "duplicate"),
            ("Delete", "delete"),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _, a=action: self.perform(a))
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def message(self, title: str, text: str, *, error: bool = False) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

    def prompt(self, title: str, initial: str = "") -> str | None:
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=initial)
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        result = entry.get_text() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        return result

    def file_dialog(self, title: str, *, saving: bool = False, suffix: str = ".pasciio"):
        dialog = Gtk.FileChooserDialog(
            title=title,
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE if saving else Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Save" if saving else "Open", Gtk.ResponseType.OK
        )
        if saving:
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_name("diagram" + suffix)
        selected = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        return selected

    def properties(self) -> None:
        if len(self.editor.selected) != 1:
            raise ValueError("Select exactly one element to edit")
        element = self.editor.selected[0]
        dialog = Gtk.Dialog(title=f"{element.kind} properties", transient_for=self, modal=True)
        dialog.set_default_size(580, 600)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Apply", Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, margin=12)
        scroller = Gtk.ScrolledWindow()
        scroller.add(grid)
        dialog.get_content_area().pack_start(scroller, True, True, 0)
        controls = {}
        names = [
            "text",
            "title",
            "kind",
            "style",
            "width",
            "height",
            "foreground",
            "background",
            "fill",
            "transparent",
            "points",
            "vertical_first",
            "diagonal",
            "start_head",
            "end_head",
            "command",
        ]
        for index, name in enumerate(names):
            grid.attach(Gtk.Label(label=name.replace("_", " "), xalign=0), 0, index, 1, 1)
            value = getattr(element, name)
            if name in ("text", "title"):
                control = Gtk.TextView()
                control.set_monospace(True)
                control.get_buffer().set_text(value)
                control.set_size_request(350, 80 if name == "text" else 45)
            elif name in ("kind", "style"):
                control = Gtk.ComboBoxText()
                choices = KINDS if name == "kind" else STYLES
                for choice in choices:
                    control.append_text(choice)
                control.set_active(choices.index(value))
            elif isinstance(value, bool):
                control = Gtk.CheckButton()
                control.set_active(value)
            else:
                control = Gtk.Entry(
                    text=json.dumps(value) if isinstance(value, list) else str(value)
                )
            controls[name] = control
            grid.attach(control, 1, index, 1, 1)
        dialog.show_all()
        try:
            while dialog.run() == Gtk.ResponseType.OK:
                try:
                    values = asdict(element)
                    for name, control in controls.items():
                        if name in ("text", "title"):
                            buffer = control.get_buffer()
                            values[name] = buffer.get_text(
                                buffer.get_start_iter(),
                                buffer.get_end_iter(),
                                True,
                            )
                        elif name in ("kind", "style"):
                            values[name] = control.get_active_text()
                        elif isinstance(control, Gtk.CheckButton):
                            values[name] = control.get_active()
                        else:
                            value = control.get_text()
                            values[name] = (
                                json.loads(value)
                                if name
                                in (
                                    "width",
                                    "height",
                                    "points",
                                    "command",
                                )
                                else value
                            )
                    replacement = Element(**values)
                    with self.editor.change():
                        index = self.editor.diagram.elements.index(element)
                        self.editor.diagram.elements[index] = replacement
                    break
                except (ValueError, TypeError) as error:
                    self.message("Invalid properties", str(error), error=True)
        finally:
            dialog.destroy()

    def execute_command(self, entry) -> None:
        self.perform(entry.get_text())
        entry.set_text("")
        self.canvas.grab_focus()

    def command_key(self, widget, event) -> bool:
        if Gdk.keyval_name(event.keyval) == "Escape":
            self.command.set_text("")
            self.canvas.grab_focus()
            return True
        return False

    def perform(self, action: str) -> None:
        try:
            if special_action(self.editor, action):
                pass
            elif not action.startswith("@"):
                self.editor.execute(action)
            elif action == "@command":
                self.command.grab_focus()
            elif action == "@edit":
                self.properties()
            elif action in ("@box", "@text", "@arrow") or action.startswith("@add:"):
                self.editor.add(action.split(":", 1)[1] if ":" in action else action[1:])
            elif action == "@new":
                self.add_tab(Editor())
            elif action == "@open":
                path = self.file_dialog("Open diagram")
                if path:
                    editor = Editor()
                    editor.open(path)
                    self.add_tab(editor)
            elif action in ("@save", "@save-as"):
                path = self.editor.path if action == "@save" else None
                if path is None:
                    path = self.file_dialog("Save diagram", saving=True)
                if path:
                    self.editor.save(path)
            elif action.startswith("@export-"):
                suffix = "." + action.rsplit("-", 1)[1]
                path = self.file_dialog("Export diagram", saving=True, suffix=suffix)
                if path:
                    if suffix == ".png":
                        export_png(self.editor.diagram, path)
                    else:
                        storage.export(self.editor.diagram, path)
            elif action in ("@find", "@replace"):
                text = self.prompt("Find text")
                if text is not None:
                    self.editor.find(text)
                    if action == "@replace":
                        replacement = self.prompt("Replace with")
                        if replacement is not None:
                            self.editor.replace(text, replacement)
            elif action == "@copy-text":
                text = self.editor.diagram.render(crop=True, ids=self.editor.selection or None)
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
            elif action == "@paste-text":
                text = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
                if text:
                    self.editor.add("text", text)
            elif action == "@stencil-save":
                path = self.file_dialog("Save stencil", saving=True)
                if path:
                    self.editor.execute(f"stencil-save {shlex.quote(path)}")
            elif action == "@stencil-load":
                path = self.file_dialog("Insert stencil")
                if path:
                    self.editor.execute(f"stencil-load {shlex.quote(path)}")
            elif action == "@grid":
                self.canvas.grid = not self.canvas.grid
            elif action == "@rulers":
                self.canvas.rulers = not self.canvas.rulers
            elif action in ("@zoom-in", "@zoom-out"):
                self.canvas.zoom = max(
                    6, min(32, self.canvas.zoom + (1 if action == "@zoom-in" else -1))
                )
            elif action == "@close-tab":
                self.close_tab(self.notebook.get_nth_page(self.notebook.get_current_page()))
            elif action == "@quit":
                self.close()
            elif action == "@help":
                self.message(
                    "Keyboard shortcuts",
                    "\n".join(
                        f"{key} : {command}"
                        for key, command in self.canvas.bindings.mapping.items()
                    ),
                )
            else:
                raise ValueError(f"Unknown interface action: {action}")
            self.refresh()
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.message("Action failed", str(error), error=True)

    def allow_close(self, editor: Editor) -> bool:
        if not editor.dirty:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Save changes to {editor.path.name if editor.path else 'Untitled'}?",
        )
        dialog.add_buttons(
            "Cancel",
            Gtk.ResponseType.CANCEL,
            "Discard",
            Gtk.ResponseType.NO,
            "Save",
            Gtk.ResponseType.YES,
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            path = editor.path or self.file_dialog("Save diagram", saving=True)
            if not path:
                return False
            try:
                editor.save(path)
            except (ValueError, OSError) as error:
                self.message("Save failed", str(error), error=True)
                return False
            return True
        return response == Gtk.ResponseType.NO

    def close_tab(self, page) -> None:
        if self.allow_close(page.canvas.editor):
            self.notebook.remove_page(self.notebook.page_num(page))
            if self.notebook.get_n_pages() == 0:
                self.add_tab(Editor())
            self.refresh()

    def close_window(self, widget, event) -> bool:
        for index in range(self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(index)
            if not self.allow_close(page.canvas.editor):
                return True
        Gtk.main_quit()
        return False


def export_png(diagram, path: str | Path) -> None:
    import cairo

    lines = diagram.render(crop=True).splitlines()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)
    layout.set_font_description(Pango.FontDescription("DejaVu Sans Mono 12"))
    layout.set_text("M", -1)
    cw, ch = layout.get_pixel_size()
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32,
        max(map(width, lines), default=1) * cw + 16,
        max(1, len(lines)) * ch + 16,
    )
    context = cairo.Context(surface)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    context.set_source_rgb(0.1, 0.1, 0.1)
    layout = PangoCairo.create_layout(context)
    layout.set_font_description(Pango.FontDescription("DejaVu Sans Mono 12"))
    for y, text in enumerate(lines):
        layout.set_text(text, -1)
        context.move_to(8, 8 + y * ch)
        PangoCairo.show_layout(context, layout)
    surface.write_to_png(str(path))


def run(editors: list[Editor]) -> None:
    if not Gtk.init_check()[0]:
        raise ValueError("Cannot open a graphical display. Use tasciio for the terminal editor.")
    window = Window(editors)
    window.show_all()
    Gtk.main()
