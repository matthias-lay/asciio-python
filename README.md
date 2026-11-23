# Asciio Python

A Python reimplementation of [Asciio](https://github.com/nkh/P5-App-Asciio):
an ASCII/Unicode diagram engine shared by a GTK3 desktop editor, a curses
terminal editor, command-line converters, and Python scripts.

**Status: functional first implementation, not yet full upstream feature parity.**
The full port is the target; the limitations below are not claims of completed
features. No Perl runtime, Perl-file compatibility, or JSON export is provided.
Native diagrams and reusable stencils use **`.pasciio`**, not `.asciio`.

## Install

### Distro packages, without a virtual environment (recommended)

Use the distribution's Python **3.11 or newer**, its packaged dependencies, and
the source installer below. No `pip`, virtual environment, setuptools, compiler,
or `--break-system-packages` is needed. The application itself is not yet
published as a Debian/RPM/Arch repository package; these commands install its
**dependencies**, not Asciio Python.

**Debian 12/13 and Ubuntu 24.04 or newer:**

```sh
sudo apt-get install make python3 python3-wcwidth python3-regex
# Optional GTK3 GUI and PNG export:
sudo apt-get install python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-3.0 gir1.2-pango-1.0
```

Ubuntu 22.04's default Python 3.10 is too old for this application.

**Fedora (currently supported releases):**

```sh
sudo dnf install make python3 python3-wcwidth python3-regex
# Optional GTK3 GUI and PNG export:
sudo dnf install python3-gobject python3-cairo gtk3
```

**Arch Linux:**

```sh
sudo pacman -S --needed make python python-wcwidth python-regex
# Optional GTK3 GUI and PNG export:
sudo pacman -S --needed python-gobject python-cairo gtk3
```

**openSUSE Leap 16 / Tumbleweed, using Python 3.13:**

```sh
sudo zypper install make python313 python313-curses python313-wcwidth python313-regex
# Optional GTK3 GUI and PNG export:
sudo zypper install python313-gobject python313-gobject-Gdk \
  python313-gobject-cairo python313-cairo \
  typelib-1_0-Gtk-3_0 typelib-1_0-Pango-1_0
```

Python packages and interpreter versions must match; for this openSUSE example,
pass `PYTHON=/usr/bin/python3.13` to `make`. On rolling distributions, use the
equivalent complete package set for an available Python version if 3.13 has
been retired. GTK **3**, not GTK4, is required.

From the project checkout, install for your user:

```sh
make install PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
tasciio
asciio     # if the optional GTK dependencies are installed
```

For the openSUSE example:

```sh
make install PREFIX="$HOME/.local" PYTHON=/usr/bin/python3.13
```

The installer puts application code in `$PREFIX/share/asciio-python` and
launchers in `$PREFIX/bin`. Launchers use `/usr/bin/python3` by default, ignoring
unrelated Python installations earlier on `PATH`. They load this application's
code and the selected interpreter's distro packages, without writing into
system `site-packages`. An existing unrelated `asciio` or other command in the
destination is not overwritten; choose another prefix in that case.

For a machine-wide source installation, use
`sudo make install PREFIX=/usr/local`, adding `PYTHON=...` when needed.
`DESTDIR` supports staging for downstream packaging. Upgrade by repeating the
same installation command; uninstall using
`make uninstall PREFIX="$HOME/.local"` or
`sudo make uninstall PREFIX=/usr/local`, matching your installation prefix.

`regex` provides grapheme segmentation on stable distros; `wcwidth` 0.2.5 or
newer is sufficient. Emoji widths are normalized across the older and newer
`wcwidth` releases. Other Unicode character widths depend on the packaged
Unicode tables and terminal font.

To run directly from a checkout without installing the application:

```sh
PYTHONPATH="$PWD/src" /usr/bin/python3 -m asciio tui
PYTHONPATH="$PWD/src" /usr/bin/python3 -m asciio gui
```

Use `/usr/bin/python3.13` instead for the openSUSE example.

Package-name references: [PyGObject's distro installation guide](https://pygobject.gnome.org/getting_started.html)
(this application uses GTK3 instead of its GTK4 example),
[Debian wcwidth](https://packages.debian.org/trixie/python3-wcwidth),
[Fedora regex](https://packages.fedoraproject.org/pkgs/python-regex/python3-regex/),
and [Arch Python packages](https://archlinux.org/packages/extra/x86_64/python-regex/).
The native-package CI jobs are configured to exercise these distro installs,
including Ubuntu 24.04's older dependency versions.

### Optional pip/development installation

Virtual environments remain an option for development, not a runtime
requirement. After installing the GUI's distro dependencies if needed:

```sh
/usr/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e .
```

Alternatively, install your platform's GTK3/Cairo/introspection development
libraries, then `pip install -e '.[gui]'` inside a virtual environment. Do not
use `sudo pip install` or bypass an externally managed system Python.

## Use

```sh
asciio diagram.pasciio                 # GTK GUI; multiple filenames open tabs
tasciio diagram.pasciio                # terminal editor
asciio_to_text diagram.pasciio         # text on stdout
asciio-python render diagram.pasciio -o diagram.svg
asciio-python render diagram.pasciio -o diagram.png  # requires GUI dependencies
printf 'hello\nworld\n' | text_to_asciio -o greeting.pasciio --box
asciio-python run examples/architecture.py -o architecture.pasciio
asciio-python edit architecture.pasciio -c 'select all' \
  -c 'move 2 1' -o moved.pasciio
```

`python -m asciio` exposes the same subcommands as `asciio-python`.
Text and SVG exports work headlessly. PNG requires GTK/Pango/Cairo libraries,
but does not require an open graphical display. SVG embeds monospaced text;
it is not a tracing/vectorization of lines into paths. Text exports preserve
positive canvas margins and clip negative coordinates unless `--crop` is used.
SVG/PNG crop to the full diagram, including negative coordinates.

### Editing

Both interfaces share actions, history, shapes, connections and key sequences.
The GTK menus expose the commands, including multi-tab files, exports, stencils,
properties, alignment, grouping and clipboard text. Click to select/place the
insertion cursor, Ctrl-click for multi-selection, drag selected elements to move,
or drag empty canvas to select a rectangle. Double-click edits or adds a box.
Ctrl+mouse-wheel zooms.

| Keys | Action |
| --- | --- |
| `b`, `t`, `a a` | Insert box, text, arrow at cursor |
| `Tab`, `Shift+Tab` | Next/previous element |
| `h j k l`, arrow keys | Move selection |
| `Shift` + arrow keys | Move insertion cursor (GTK) |
| `1 2 3 4` | Narrower, taller, shorter, wider |
| `Enter` | Properties (GTK), text editing (terminal; `\n` makes a new line) |
| `V`, `Escape`, `d` | Select all, deselect, delete |
| `u`, `Ctrl+r` | Undo, redo |
| `y y`, `p p`, `Ctrl+d` | Copy, paste, duplicate |
| `g g`, `g u`, `g f`, `g b` | Group, ungroup, front, back |
| `A t/l/b/r/h/v` | Align top/left/bottom/right/horizontally/vertically |
| `a d`, `a f` | Toggle arrow bend orientation, swap arrowheads |
| `z x`, `z g`, `z r` | Cross mode, grid, ruler |
| `Ctrl+s`, `Ctrl+o`, `Ctrl+n`, `Ctrl+q` | Save, open, new, quit |
| `/`, `:`, `?` | Find, command entry, help |

Terminal mouse clicks place the cursor and select elements; terminal mouse
dragging and shifted cursor keys are not implemented. Use `:cursor 20 10` to
place the insertion point and `:pan 10 5` to change the terminal viewport.
GTK copy/paste elements is application-local; "Copy as text"/"Paste text" uses
the system clipboard. Each editor currently owns its own element clipboard.
Groups are flat: selecting any member selects the group.

### Commands

Enter commands with `:` in either UI or with `asciio-python edit -c`.
Arguments follow shell quoting rules; no shell is invoked by command parsing.
Element IDs appear in the status bar; unique ID prefixes are accepted by `select`.

```text
box 'body text'                    # also: text, ellipse, rhombus, if-box,
                                  # process-box, triangle-up/down, axis,
                                  # arrow, angled-arrow, exec-box
select <id-prefix> <id-prefix>     # or: select all / select none
set title 'Service'
set text 'new text'
set style unicode                 # dash, unicode, double, bold, dot, star
set foreground '#224466'
set background '#ffffff'
set transparent true
move 5 -2
resize 4 1
shrink
link right left                   # connects two selected non-arrow elements
                                  # anchors: top, bottom, left, right
route 0,0 8,0 8,6 20,6             # relative arrow waypoints
set vertical_first true
set diagonal true
set start_head true
set end_head false
group
ungroup
front
back
align top                         # left/right/top/bottom/horizontal/vertical
distribute horizontal             # or vertical
find 'old'
replace 'old' 'new'                # selected elements only
copy
paste
duplicate
delete
undo
redo
cross
save diagram.pasciio
open diagram.pasciio               # save unsaved changes first
export diagram.txt                # or .asc/.svg
stencil-save block.pasciio         # selected elements and internal connections
stencil-load block.pasciio         # inserts at cursor with fresh IDs
```

Connections bind arrow endpoints to an element's side center and follow moves,
resizes, and text edits. Moving a bound arrow by itself detaches its connections;
moving its target keeps the connection. Arrow endpoints can be bound separately
through `Diagram.connect` in Python. No obstacle-avoiding router is implemented.
Shapes grow to fit text; `shrink` explicitly resets to minimum content size.

### Exec boxes and scripts

Exec boxes run **only** after an explicit `refresh` command:

```text
exec-box
set command '["date", "+%Y-%m-%d"]'
refresh
```

Commands are argument arrays, run without a shell, with a ten-second timeout.
Failures are shown as errors without replacing the box content. Opening a
diagram, loading a stencil, exporting, and rendering never execute commands.
Only run exec commands and Python scripts that you trust. `asciio-python run`
executes ordinary Python with full process privileges; it is not a sandbox.
The script receives an `editor` object; see `examples/architecture.py`.

### Custom keys

Create `$XDG_CONFIG_HOME/asciio-python/bindings.json`, defaulting to
`~/.config/asciio-python/bindings.json`. This is configuration, not an export
format. Map space-separated key sequences to editor commands or built-in
interface actions; an empty string disables a binding:

```json
{"Ctrl+b": "box", "z x": "", "F2": "@save"}
```

Invalid configuration is reported rather than silently ignored.

## Native format

`.pasciio` is a versioned UTF-8 document with an internal JSON representation,
validated element records, stable IDs, connections, and cross-mode state.
It is the Python application's native format, **not an export option or a
compatibility bridge to Perl Asciio**. Saving is atomic. Native saving rejects
other extensions. Malformed files, unknown versions and invalid references
fail explicitly. No pickle, Perl evaluation, embedded bindings, or automatic
command execution is used.

## Coverage and remaining port work

Implemented: editable boxes/titles/text, six frame styles, ellipse, rhombus,
if/process boxes, triangles, axes, polylines/angled lines, arrowheads, explicit
side connections, Unicode cell-width layout, opaque/transparent elements,
line crossings, z-order, grouped multi-selection, copy/duplicate/stencils,
alignment/distribution, search/replace, transactional undo/redo, native
persistence, text/SVG/PNG output, scripting, GUI tabs and configurable keys.

Remaining for full feature parity: upstream's exact ellipse/angled-arrow
rasterization and full per-shape style catalog; automatic mouse connection
snapping and obstacle routing; custom connector definitions and connection to
interior arrow sections; nested groups; image boxes; bundled computer/people
stencil libraries; pen/eraser and inline editing modes; markup and SVG path
conversion; presentation/animation; Git integration; embedded web API;
binding completion; richer terminal mouse interactions and terminal tabs.
Perl file/stencil/script compatibility and JSON export are intentionally excluded.

## Development

```sh
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check .
mypy
pytest -q
PASCIIO_GUI_TESTS=1 xvfb-run -a pytest -q tests/test_gui.py  # GTK runtime required
```

The automated checks cover geometry, connections, editing/history, Unicode,
file round trips, commands, converter entry points, a real pseudo-terminal
session, and (with GTK available) the desktop canvas and exports.

## Attribution and license

Inspired by and developed with reference to `nkh/P5-App-Asciio`, by
Khemir Nadim ibn Hamouda and Qin Qing. Reference revision:
`6abb8c21ae16e55631ce6e450641ceb3f8debeee`.
This Python implementation is distributed under GPL-3.0-or-later; see `LICENSE`.
