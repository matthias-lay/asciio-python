import json

import pytest

from asciio import Connection, Diagram, Element
from asciio.model import KINDS
from asciio.text import Cells, put, row, width


def test_titled_box_fits_unicode_and_combining_characters():
    element = Element(text="\u754c e\u0301", title="API", style="unicode")
    lines = element.body_lines()
    assert lines[0].startswith("\u256d")
    assert lines[-1].endswith("\u256f")
    assert "API" in lines[1]
    assert "\u754c e\u0301" in lines[3]
    assert len(lines) == element.height
    assert {width(line) for line in lines} == {element.width}


@pytest.mark.parametrize("kind", [k for k in KINDS if k not in ("arrow", "angled-arrow")])
def test_resized_shapes_contain_their_text_and_stay_within_bounds(kind):
    element = Element(kind=kind, text="hello\nworld", title="Title", width=33, height=13)
    lines = element.body_lines()
    assert "hello" in "\n".join(lines)
    assert "world" in "\n".join(lines)
    assert max(map(width, lines)) <= element.width
    assert len(lines) <= element.height


@pytest.mark.parametrize("size", [9, 10, 15, 16, 23, 24])
def test_ellipse_has_both_side_borders_for_odd_and_even_sizes(size):
    element = Element(kind="ellipse", text="sample", width=size)
    center = element.body_lines()[element.height // 2]
    assert center.startswith("|")
    assert center.endswith("|")
    assert "sample" in center
    assert width(center) == element.width


@pytest.mark.parametrize(
    ("points", "vertical", "expected"),
    [
        ([(0, 0), (4, 0)], False, "---->\n"),
        ([(4, 0), (0, 0)], False, "<----\n"),
        ([(0, 0), (3, 2)], False, "---.\n   |\n   v\n"),
        ([(0, 2), (3, 0)], True, ".-->\n|\n|\n"),
        ([(0, 0), (2, 0), (2, 2), (4, 2)], False, "--.\n  |\n  '->\n"),
    ],
)
def test_arrow_routing(points, vertical, expected):
    arrow = Element(kind="arrow", points=points, vertical_first=vertical)
    assert Diagram([arrow]).render(crop=True) == expected


def test_cross_mode_only_merges_visible_arrow_strokes():
    horizontal = Element(kind="arrow", points=[(0, 2), (4, 2)], end_head=False)
    vertical = Element(kind="arrow", points=[(2, 0), (2, 4)], end_head=False)
    diagram = Diagram([horizontal, vertical])
    assert diagram.cells()[2, 2] == "+"
    diagram.cross_mode = False
    assert diagram.cells()[2, 2] == "|"
    diagram.cross_mode = True
    diagram.elements.insert(1, Element(kind="text", x=2, y=2, text="X"))
    assert diagram.cells()[2, 2] == "|"


def test_wide_glyph_overwrites_erase_both_halves_and_crop_never_splits_a_glyph():
    cells: Cells = {}
    put(cells, 0, 0, "\u754cA")
    assert row(cells, 0, 0, 3) == "\u754cA"
    assert row(cells, 0, 1, 3) == " A"
    assert row(cells, 0, 0, 1) == " "
    put(cells, 1, 0, "x")
    assert row(cells, 0, 0, 3) == " xA"
    put(cells, 1, 0, "\u754c")
    assert row(cells, 0, 0, 3) == " \u754c"


def test_joined_emoji_uses_its_display_width_not_codepoint_count():
    text = "\U0001f469\u200d\U0001f4bb"
    element = Element(kind="text", text=text + "X")
    diagram = Diagram([element])
    assert diagram.render() == text + "X\n"
    assert diagram.bounds() == (0, 0, width(text) + 1, 1)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\U0001f469\u200d\U0001f4bb", 2),
        ("\U0001f44d\U0001f3fd", 2),
        ("\u2764\ufe0f", 2),
        ("1\ufe0f\u20e3", 2),
        ("\U0001f1eb\U0001f1f7", 2),
        ("\U0001f1eb", 2),
        ("e\u0301", 1),
        ("\u754c", 2),
    ],
)
def test_grapheme_widths_work_with_stable_distro_wcwidth(text, expected):
    diagram = Diagram([Element(kind="text", text=text + "X")])
    assert width(text) == expected
    assert diagram.bounds() == (0, 0, expected + 1, 1)
    assert diagram.render() == text + "X\n"


def test_transparent_text_and_negative_coordinate_export():
    background = Element(kind="text", x=-2, y=-1, text="ABCDE\nFGHIJ")
    foreground = Element(kind="text", x=-1, y=0, text=" x ", transparent=True)
    diagram = Diagram([background, foreground])
    assert diagram.render(crop=True) == "ABCDE\nFGxIJ\n"
    assert diagram.render() == "xIJ\n"
    assert diagram.hit(-1, 0) == background


@pytest.mark.parametrize(
    "values",
    [
        {"text": "\x1b[31m"},
        {"text": "\u0301"},
        {"width": -1},
        {"x": True},
        {"fill": "\t"},
        {"points": [[0, 0], ["x", 1]]},
        {"transparent": "yes"},
        {"foreground": "red"},
    ],
)
def test_invalid_elements_fail_explicitly(values):
    with pytest.raises(ValueError):
        Element(**values)


def test_native_round_trip_and_connection_validation():
    box = Element(text="target")
    arrow = Element(kind="arrow")
    diagram = Diagram([box, arrow])
    diagram.connect(arrow, "end", box, "left")
    restored = Diagram.from_dict(json.loads(json.dumps(diagram.to_dict())))
    assert restored.to_dict() == diagram.to_dict()
    restored.connections.append(Connection(arrow.id, "end", box.id, "top"))
    with pytest.raises(ValueError, match="multiple connections"):
        restored.validate()
    restored.connections = [Connection(arrow.id, "end", "missing", "left")]
    with pytest.raises(ValueError, match="Unknown element"):
        restored.validate()
